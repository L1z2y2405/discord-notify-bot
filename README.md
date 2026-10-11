# tarkov-discord-notifier

Polls X accounts listed in a shared Google Doc and forwards new posts to Discord via webhook.

## Features

- Reads source profile links from a Google Doc (one URL per line).
- Team can add or remove accounts by editing the Doc — no code change.
- Stores the last seen post ID per account.
- Prefers the official X page locally; on GitHub Actions uses the public X mirror.
- Discord embed is link + image only (no title or tweet text).
- Fully modular and testable.

## Requirements

- Python 3.12+
- `uv`
- Node.js 18+ (only needed to deploy the Cloudflare cron Worker)

## Installation

```bash
uv sync
playwright install
cp .env.example .env
```

Set `DISCORD_WEBHOOK_URL` in `.env` before running. Keep the Google Doc shared as **Anyone with the link → Viewer**.

## Run

```bash
python app.py
```

## Source list (Google Doc)

The notifier exports:

`https://docs.google.com/document/d/<GOOGLE_DOC_ID>/export?format=txt`

Each non-empty line should be an X profile URL, for example:

```text
https://x.com/tarkov
https://x.com/tarkovarena
https://x.com/Paimon2theMoon
```

Order in the Doc is the send order when several accounts post in the same crawl window. A newly added account is baselined (current latest ID is saved, no Discord ping) so old posts are not dumped.

## Automation

GitHub's own `schedule` cron is not used. A Cloudflare Worker in `cloudflare-cron/` fires every 10 minutes and calls `workflow_dispatch` on `.github/workflows/tarkov-discord-notifier.yml`.

```text
Cloudflare Cron (*/10 * * * *)
        │
        ▼
  workflow_dispatch
        │
        ▼
GitHub Actions (read Google Doc + fetch each account)
        │
        ▼
   Discord webhook
```

### GitHub Actions

Workflow: `.github/workflows/tarkov-discord-notifier.yml`

- Trigger: `workflow_dispatch` only (from Cloudflare, or Run workflow in the Actions tab)
- Checks out the default branch
- Runs the notifier once and exits
- Uses `DISCORD_WEBHOOK_URL` from GitHub Secrets
- Persists `data/last_post.json` back to the repository after a successful notification or baseline

Enable the workflow:

1. Push this repository to GitHub.
2. `Settings` → `Secrets and variables` → `Actions` → add `DISCORD_WEBHOOK_URL`.
3. Enable Actions for the repository.
4. Keep the Google Doc world-readable (Viewer).
5. The workflow needs `contents: write` so it can push the updated post state.

### Cloudflare Worker

Source: `cloudflare-cron/`

Needs Node.js 18+ (`npx wrangler`). One-time setup:

1. Create a fine-grained GitHub PAT for this repo with **Actions: Read and write**.
2. From `cloudflare-cron/`:

```bash
npx wrangler login
npx wrangler secret put GITHUB_DISPATCH_TOKEN
npx wrangler deploy
```

`secret put` asks for a value: paste the PAT there. The argument is the secret **name** (`GITHUB_DISPATCH_TOKEN`), not the token itself.

3. Confirm deploy output includes `schedule: */10 * * * *`.
4. Check the Actions tab within 10 minutes for a `Tarkov Discord Notifier` run triggered by `workflow_dispatch`.

Worker env (in `wrangler.toml`):

- `GITHUB_OWNER`: `L1z2y2405`
- `GITHUB_REPO`: `tarkov-bot`
- `GITHUB_WORKFLOW`: `tarkov-discord-notifier.yml`
- `GITHUB_REF`: `main`

Secret (Cloudflare only, never commit it):

- `GITHUB_DISPATCH_TOKEN`: GitHub PAT used to call the workflow dispatch API

Rotate the PAT: revoke the old token on GitHub, create a new one, then run `npx wrangler secret put GITHUB_DISPATCH_TOKEN` again. Redeploy is not required after updating a secret.

If a cron tick fails, check Worker logs. GitHub should return HTTP `204`. `401` / `403` usually means the PAT is wrong or expired; `404` usually means the owner, repo, or workflow filename is wrong.

## Configuration

- `DISCORD_WEBHOOK_URL`: Discord webhook target
- `GOOGLE_DOC_ID` or `GOOGLE_DOC_URL`: Google Doc that lists X profile links
- `CHECK_INTERVAL_SECONDS`: Local polling interval in seconds, default `600`
- `TWITTER_USERNAME`: Fallback default handle for the X client
- `HEADLESS`: `true` or `false`
- `RETRY_ATTEMPTS`: retry count for transient failures, default `3`
- `RUN_ONCE`: when `true`, run a single check and exit

## Folder Structure

- `app.py`: application entrypoint and dependency wiring
- `config.py`: environment parsing and settings
- `models.py`: data models
- `sources.py`: Google Doc export and handle parsing
- `storage.py`: JSON persistence for last post IDs
- `twitter.py`: X scraping logic and fallback retrieval
- `discord_webhook.py`: Discord webhook client
- `scheduler.py`: polling loop and delivery orchestration
- `utils.py`: shared retry helper
- `data/last_post.json`: persisted processing state
- `cloudflare-cron/`: Cloudflare Worker that dispatches the GitHub Actions workflow
- `.github/workflows/tarkov-discord-notifier.yml`: one-shot notifier job

## Architecture

```text
Google Doc (source list)
        │
        v
Cloudflare Cron
        │
        v
GitHub Actions workflow
        │
        v
┌──────────────┐
│   app.py     │
└──────┬───────┘
       │
       v
┌────────────────────┐
│ NotifierScheduler  │
└───┬─────────┬──────┘
    │         │
    v         v
┌────────┐   ┌───────────────┐
│Storage │   │TwitterClient   │
└────────┘   └──────┬────────┘
                    │
        ┌───────────┴───────────┐
        v                       v
┌──────────────────┐   ┌────────────────────┐
│ Official X page  │   │ Public fallback     │
│ Playwright scrape│   │ mirror scrape       │
└──────────────────┘   └────────────────────┘
                    │
                    v
           ┌────────────────┐
           │ DiscordClient   │
           └────────────────┘
```

## Storage Format

`data/last_post.json`

```json
{
    "last_post_ids": {
        "tarkov": "1234567890",
        "tarkovarena": "1234567891"
    }
}
```

## Notes

- On GitHub Actions, the client uses the public X mirror only.
- Locally, the official X page is attempted first, then the public mirror.
- Duplicate notifications are prevented per account by comparing the latest post ID with the stored ID for that handle.
- If several accounts post in the same 10-minute window, every new post is sent, in Google Doc order.
