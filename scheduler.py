from __future__ import annotations

import asyncio
import logging
import os
import subprocess
from pathlib import Path

from discord_webhook import DiscordClient
from sources import SourcesError, fetch_handles
from storage import Storage
from twitter import TwitterClient
from utils import retry_async


class NotifierScheduler:
    def __init__(
        self,
        twitter_client: TwitterClient,
        discord_client: DiscordClient,
        storage: Storage,
        check_interval_seconds: int,
        google_doc_id: str,
        logger: logging.Logger,
    ) -> None:
        self._twitter_client = twitter_client
        self._discord_client = discord_client
        self._storage = storage
        self._check_interval_seconds = check_interval_seconds
        self._google_doc_id = google_doc_id
        self._logger = logger
        self._repo_root = Path(__file__).resolve().parent

    async def run(self) -> None:
        while True:
            await self.check_once()
            await asyncio.sleep(self._check_interval_seconds)

    async def check_once(self) -> None:
        try:
            handles = fetch_handles(self._google_doc_id)
        except SourcesError as exc:
            self._logger.error("Failed to load sources: %s", exc)
            return

        self._logger.info("Loaded %s source(s): %s", len(handles), ", ".join(handles))
        state = self._storage.load()
        updated = False

        for handle in handles:
            try:
                post = await self._twitter_client.fetch_latest_post(handle)
            except Exception as exc:  # noqa: BLE001
                self._logger.error("Failed to fetch latest post for @%s: %s", handle, exc)
                continue

            last_id = state.last_id_for(handle)
            if last_id is None:
                self._logger.info("Baselining @%s at %s", handle, post.post_id)
                state = state.with_last_id(handle, post.post_id)
                self._storage.save(state)
                updated = True
                continue

            if last_id == post.post_id:
                self._logger.info("No new post for @%s.", handle)
                continue

            self._logger.info("New post detected for @%s: %s", handle, post.post_id)
            try:
                await retry_async(
                    lambda current=post: asyncio.to_thread(
                        self._discord_client.send_post, current, self._logger
                    ),
                    3,
                    self._logger,
                )
                state = state.with_last_id(handle, post.post_id)
                self._storage.save(state)
                updated = True
            except Exception as exc:  # noqa: BLE001
                self._logger.error(
                    "Failed to process new post for @%s: %s", handle, exc
                )

        if updated:
            self._logger.info("Updated last_post.json")
            await self._persist_state_to_git()

    async def _persist_state_to_git(self) -> None:
        if not self._is_git_repo():
            self._logger.info("Git repository not available; skipping state push")
            return

        await asyncio.to_thread(self._git_commit_and_push)

    def _is_git_repo(self) -> bool:
        return (self._repo_root / ".git").exists()

    def _git_commit_and_push(self) -> None:
        branch = self._current_branch()
        if not branch:
            raise RuntimeError("Unable to determine current git branch")

        status = subprocess.run(
            ["git", "status", "--porcelain", "--", "data/last_post.json"],
            cwd=self._repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if not status.stdout.strip():
            self._logger.info("No git changes to persist")
            return

        subprocess.run(
            ["git", "add", "data/last_post.json"],
            cwd=self._repo_root,
            check=True,
        )
        commit = subprocess.run(
            ["git", "commit", "-m", "Update last processed post"],
            cwd=self._repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if commit.returncode != 0:
            if "nothing to commit" in commit.stderr.lower():
                self._logger.info("No git commit needed")
                return
            raise RuntimeError(commit.stderr.strip() or "git commit failed")

        push = subprocess.run(
            ["git", "push", "origin", f"HEAD:{branch}"],
            cwd=self._repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if push.returncode != 0:
            raise RuntimeError(push.stderr.strip() or "git push failed")
        self._logger.info("Persisted last_post.json to git")

    def _current_branch(self) -> str | None:
        github_ref_name = os.getenv("GITHUB_REF_NAME", "").strip()
        if github_ref_name:
            return github_ref_name

        github_ref = os.getenv("GITHUB_REF", "").strip()
        if github_ref.startswith("refs/heads/"):
            return github_ref.removeprefix("refs/heads/")

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=self._repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if branch.returncode != 0:
            return None

        value = branch.stdout.strip()
        if not value or value == "HEAD":
            return None
        return value
