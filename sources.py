from __future__ import annotations

import re
from urllib import error, request

DOC_ID_RE = re.compile(r"/document/d/([A-Za-z0-9_-]+)")
HANDLE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:x\.com|twitter\.com)/@?([A-Za-z0-9_]+)",
    re.IGNORECASE,
)


class SourcesError(RuntimeError):
    pass


def parse_doc_id(value: str) -> str:
    raw = value.strip()
    match = DOC_ID_RE.search(raw)
    if match:
        return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]+", raw):
        return raw
    raise SourcesError("GOOGLE_DOC_ID / GOOGLE_DOC_URL is not a Google Doc")


def parse_handles(text: str) -> list[str]:
    handles: list[str] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue

        match = HANDLE_RE.search(line)
        handle = match.group(1) if match else line.lstrip("@")
        handle = handle.split("/", 1)[0].split("?", 1)[0].strip()
        if not handle or not re.fullmatch(r"[A-Za-z0-9_]+", handle):
            continue

        key = handle.lower()
        if key in seen:
            continue
        seen.add(key)
        handles.append(handle)
    return handles


def fetch_handles(doc_id_or_url: str) -> list[str]:
    doc_id = parse_doc_id(doc_id_or_url)
    url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    req = request.Request(
        url,
        headers={
            "Accept": "text/plain",
            "User-Agent": "tarkov-discord-notifier/0.1.0",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8-sig")
    except error.HTTPError as exc:
        raise SourcesError(f"Google Doc export HTTP {exc.code}") from exc
    except (error.URLError, TimeoutError, OSError) as exc:
        raise SourcesError(f"Google Doc export failed: {exc}") from exc

    handles = parse_handles(body)
    if not handles:
        raise SourcesError("Google Doc did not contain any X profile links")
    return handles
