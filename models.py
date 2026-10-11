from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Post:
    post_id: str
    post_url: str
    text: str
    published_at: datetime | None
    author: str
    images: tuple[str, ...] = field(default_factory=tuple)
    has_video: bool = False


@dataclass(frozen=True, slots=True)
class StoredState:
    last_post_ids: dict[str, str] = field(default_factory=dict)

    def last_id_for(self, handle: str) -> str | None:
        return self.last_post_ids.get(handle.lstrip("@").lower())

    def with_last_id(self, handle: str, post_id: str) -> "StoredState":
        updated = dict(self.last_post_ids)
        updated[handle.lstrip("@").lower()] = post_id
        return StoredState(last_post_ids=updated)
