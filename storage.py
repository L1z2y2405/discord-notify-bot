from __future__ import annotations

import json
from pathlib import Path

from models import StoredState


class Storage:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> StoredState:
        if not self._path.exists():
            return StoredState()

        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return StoredState()

        if not isinstance(payload, dict):
            return StoredState()

        last_post_ids: dict[str, str] = {}
        raw_ids = payload.get("last_post_ids")
        if isinstance(raw_ids, dict):
            for handle, post_id in raw_ids.items():
                if isinstance(handle, str) and isinstance(post_id, str) and post_id:
                    last_post_ids[handle.lstrip("@").lower()] = post_id

        legacy_id = payload.get("last_post_id")
        if isinstance(legacy_id, str) and legacy_id and "tarkov" not in last_post_ids:
            last_post_ids["tarkov"] = legacy_id

        return StoredState(last_post_ids=last_post_ids)

    def save(self, state: StoredState) -> None:
        payload = {"last_post_ids": dict(state.last_post_ids)}
        temp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        temp_path.write_text(
            json.dumps(payload, indent=4, ensure_ascii=True), encoding="utf-8"
        )
        temp_path.replace(self._path)
