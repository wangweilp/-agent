"""Bilibili Sync Connector — sync Bilibili videos, favorites, and watch history.

Connector type: "bilibili"
Data sources:
  - User uploaded videos (space/arc/search)
  - Favorite folders and their contents
  - Watch history

Credentials (in self.config):
  - uid: Bilibili user ID (mid)
  - cookie: full cookie string for authenticated requests
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource


class BilibiliConnector(BaseSyncConnector):
    """Sync connector for Bilibili — videos, favorites, watch history."""

    connector_type: str = "bilibili"

    BASE_URL = "https://api.bilibili.com"
    TIMEOUT = 15  # seconds for HTTP requests

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger(f"sync.connector.{self.connector_type}")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.bilibili.com",
            }
        )
        cookie = self.config.get("cookie", "")
        if cookie:
            self._set_cookie(cookie)

    # ── helpers ──────────────────────────────────────────────────────────

    def _set_cookie(self, cookie: str) -> None:
        """Parse and set a Netscape-style cookie string on the session."""
        for part in cookie.split(";"):
            part = part.strip()
            if "=" not in part:
                continue
            key, _, value = part.partition("=")
            self.session.cookies.set(key.strip(), value.strip())

    def _get(self, path: str, params: dict | None = None) -> dict:
        """GET a Bilibili API endpoint; return parsed JSON or empty dict on failure."""
        url = f"{self.BASE_URL}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=self.TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                self.logger.warning(
                    "Bilibili API returned error code=%s message=%s",
                    data.get("code"),
                    data.get("message"),
                )
                return {}
            return data.get("data", {})
        except requests.RequestException as e:
            self.logger.warning("HTTP request failed for %s: %s", path, str(e))
            return {}

    def _uid(self) -> str:
        """Return the configured uid (mid), or empty string."""
        return str(self.config.get("uid", ""))

    # ── public methods ───────────────────────────────────────────────────

    def test_connection(self) -> SyncConnectionResult:
        """Validate credentials by fetching the user's basic space info."""
        uid = self._uid()
        if not uid:
            return SyncConnectionResult(
                success=False,
                message="Missing uid in connector config",
                resources_count=0,
            )

        data = self._get("/x/space/acc/info", params={"mid": uid})
        if not data:
            return SyncConnectionResult(
                success=False,
                message="Failed to connect to Bilibili API — check network or credentials.",
                resources_count=0,
            )

        name = data.get("name", "unknown")
        # Do a lightweight count of user videos
        video_data = self._get(
            "/x/space/wbi/arc/search", params={"mid": uid, "ps": 1, "pn": 1}
        )
        vlist = video_data.get("list", {}) if video_data else {}
        count = vlist.get("vlist", {}).get("total", 0) if isinstance(vlist, dict) else 0

        return SyncConnectionResult(
            success=True,
            message=f"Connected to Bilibili as '{name}' — ~{count} videos found.",
            resources_count=count,
        )

    def list_resources(self) -> list[SyncResource]:
        """List user videos, favorite folders, and watch history."""
        resources: list[SyncResource] = []

        uid = self._uid()
        if not uid:
            return resources

        resources.extend(self._list_user_videos(uid))
        resources.extend(self._list_favorites(uid))
        resources.extend(self._list_history())

        return resources

    def fetch_changes(self, since: datetime | None = None) -> list[dict]:
        """Return lightweight change descriptors for resources changed since *since*.

        Returns a list of dicts:
            {"resource_id": str, "resource_type": str, "updated_at": datetime, "aid": int, "bvid": str}
        """
        changes: list[dict] = []
        uid = self._uid()
        if not uid:
            return changes

        # Videos
        page = 1
        while True:
            data = self._get(
                "/x/space/wbi/arc/search",
                params={"mid": uid, "ps": 30, "pn": page},
            )
            if not data:
                break
            vlist = data.get("list", {})
            videos = vlist.get("vlist") if isinstance(vlist, dict) else None
            if not videos:
                break
            for v in videos:
                pubdate = self._parse_timestamp(v.get("pubdate", 0))
                if since and pubdate <= since:
                    continue
                aid = v.get("aid", 0)
                changes.append(
                    {
                        "resource_id": f"video_{aid}",
                        "resource_type": "video",
                        "updated_at": pubdate,
                        "aid": aid,
                        "bvid": v.get("bvid", ""),
                    }
                )
            page += 1
            if page > 50:  # safety cap
                break

        # History entries
        history_items = self._fetch_history_raw()
        for item in history_items:
            aid = item.get("aid", 0)
            pubdate = self._parse_timestamp(item.get("view_at", 0))
            if since and pubdate <= since:
                continue
            changes.append(
                {
                    "resource_id": f"hist_{aid}",
                    "resource_type": "history_entry",
                    "updated_at": pubdate,
                    "aid": aid,
                    "bvid": item.get("bvid", ""),
                }
            )

        return changes

    def fetch_content(self, resource_id: str) -> dict:
        """Fetch content for a single resource.

        Returns {"content": str, "content_type": str, "metadata": dict}
        """
        parts = resource_id.split("_", 1)
        if len(parts) != 2:
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": f"Invalid resource_id: {resource_id}"},
            }

        prefix, identifier = parts

        if prefix == "video":
            return self._fetch_video_content(identifier)
        elif prefix == "fav":
            return self._fetch_favorite_folder_content(identifier)
        elif prefix == "hist":
            return self._fetch_history_content(identifier)
        else:
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": f"Unknown resource prefix: {prefix}"},
            }

    # ── private: list sub-methods ────────────────────────────────────────

    def _list_user_videos(self, uid: str) -> list[SyncResource]:
        resources: list[SyncResource] = []
        page = 1
        while True:
            data = self._get(
                "/x/space/wbi/arc/search",
                params={"mid": uid, "ps": 50, "pn": page},
            )
            if not data:
                break
            vlist = data.get("list", {})
            videos = vlist.get("vlist") if isinstance(vlist, dict) else None
            if not videos:
                break
            for v in videos:
                aid = v.get("aid", 0)
                resources.append(
                    SyncResource(
                        resource_id=f"video_{aid}",
                        name=v.get("title", "Untitled"),
                        resource_type="video",
                        updated_at=self._parse_timestamp(v.get("pubdate", 0)),
                        size_bytes=v.get("length", 0),  # duration as rough size proxy
                        metadata={
                            "aid": aid,
                            "bvid": v.get("bvid", ""),
                            "author": v.get("author", ""),
                            "description": v.get("description", ""),
                            "play": v.get("play", 0),
                            "danmaku": v.get("video_review", 0),
                            "comment": v.get("comment", 0),
                        },
                    )
                )
            page += 1
            if page > 50:
                break
        return resources

    def _list_favorites(self, uid: str) -> list[SyncResource]:
        """List the user's favorite folders as resources."""
        resources: list[SyncResource] = []
        data = self._get("/x/v3/fav/folder/created/list", params={"up_mid": uid})
        if not data:
            return resources
        folders = data.get("list", [])
        for folder in folders:
            ml_id = folder.get("id", 0)
            resources.append(
                SyncResource(
                    resource_id=f"fav_{ml_id}",
                    name=folder.get("title", "Favorite Folder"),
                    resource_type="favorite_folder",
                    updated_at=self._parse_timestamp(folder.get("mtime", 0)),
                    size_bytes=folder.get("media_count", 0),
                    metadata={
                        "media_id": ml_id,
                        "media_count": folder.get("media_count", 0),
                        "intro": folder.get("intro", ""),
                    },
                )
            )
        return resources

    def _list_history(self) -> list[SyncResource]:
        """List recently watched videos from history as resources."""
        resources: list[SyncResource] = []
        items = self._fetch_history_raw()
        for item in items:
            title = item.get("title", "Untitled")
            aid = item.get("aid", 0)
            bvid = item.get("bvid", "")
            resources.append(
                SyncResource(
                    resource_id=f"hist_{aid}",
                    name=title,
                    resource_type="history_entry",
                    updated_at=self._parse_timestamp(item.get("view_at", 0)),
                    size_bytes=item.get("duration", 0),
                    metadata={
                        "aid": aid,
                        "bvid": bvid,
                        "author_name": item.get("author_name", ""),
                        "progress": item.get("progress", 0),
                        "duration": item.get("duration", 0),
                        "cover": item.get("cover", ""),
                    },
                )
            )
        return resources

    def _fetch_history_raw(self) -> list[dict]:
        """Fetch raw history entries (up to ~100 items)."""
        entries: list[dict] = []
        max_id = 0
        for _ in range(5):  # up to ~100 entries
            data = self._get(
                "/x/web-interface/history/cursor",
                params={"max": max_id, "view_at": 0, "ps": 20},
            )
            if not data:
                break
            batch = data.get("list", [])
            if not batch:
                break
            entries.extend(batch)
            cursor = data.get("cursor", {})
            max_id = cursor.get("max", 0)
            if not max_id or max_id == 0:
                break
        return entries

    # ── private: fetch_content sub-methods ───────────────────────────────

    def _fetch_video_content(self, aid_str: str) -> dict:
        """Fetch full video metadata."""
        try:
            aid = int(aid_str)
        except ValueError:
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": f"Invalid aid: {aid_str}"},
            }

        data = self._get("/x/web-interface/view", params={"aid": aid})
        if not data:
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": f"Failed to fetch video aid={aid}"},
            }

        # Build a structured text representation
        title = data.get("title", "")
        desc = data.get("desc", "")
        owner = data.get("owner", {})
        stat = data.get("stat", {})
        author = owner.get("name", "")
        bvid = data.get("bvid", "")
        pubdate_ts = data.get("pubdate", 0)
        pubdate = (
            datetime.fromtimestamp(pubdate_ts, tz=timezone.utc).isoformat()
            if pubdate_ts
            else ""
        )

        # Try to fetch subtitles via the player API (cid from first page)
        subtitle_text = self._fetch_subtitles(aid, data.get("cid", 0))

        parts = [
            f"Title: {title}",
            f"Author: {author}",
            f"Published: {pubdate}",
            f"BV: {bvid}",
            f"AID: {aid}",
            "",
            f"Description: {desc}",
        ]
        if subtitle_text:
            parts.extend(["", "=== Subtitles ===", subtitle_text])

        content = "\n".join(parts)
        content_hash = self.compute_hash(content)

        return {
            "content": content,
            "content_type": "text",
            "metadata": {
                "aid": aid,
                "bvid": bvid,
                "title": title,
                "author": author,
                "pubdate": pubdate,
                "duration": data.get("duration", 0),
                "view": stat.get("view", 0),
                "danmaku": stat.get("danmaku", 0),
                "reply": stat.get("reply", 0),
                "favorite": stat.get("favorite", 0),
                "coin": stat.get("coin", 0),
                "share": stat.get("share", 0),
                "like": stat.get("like", 0),
                "content_hash": content_hash,
                "tags": [t.get("tag_name", "") for t in data.get("tname", [])]
                if isinstance(data.get("tname"), list)
                else [],
            },
        }

    def _fetch_favorite_folder_content(self, ml_id_str: str) -> dict:
        """Fetch the contents of a favorite folder."""
        try:
            ml_id = int(ml_id_str)
        except ValueError:
            return {
                "content": "",
                "content_type": "text",
                "metadata": {"error": f"Invalid media_id: {ml_id_str}"},
            }

        # Get folder info
        uid = self._uid()
        folder_info = self._get("/x/v3/fav/folder/created/list", params={"up_mid": uid})
        folder_name = ""
        folder_count = 0
        if folder_info:
            for f in folder_info.get("list", []):
                if f.get("id") == ml_id:
                    folder_name = f.get("title", "")
                    folder_count = f.get("media_count", 0)
                    break

        # Get folder items
        items: list[dict] = []
        page = 1
        while True:
            data = self._get(
                "/x/v3/fav/resource/list",
                params={"media_id": ml_id, "pn": page, "ps": 20},
            )
            if not data:
                break
            medias = data.get("medias") or []
            if not medias:
                break
            items.extend(medias)
            if not data.get("has_more", False):
                break
            page += 1
            if page > 50:
                break

        content_lines = [
            f"Favorite Folder: {folder_name}",
            f"Items: {len(items)} / {folder_count}",
            "",
        ]
        for item in items:
            content_lines.append(
                f"- [{item.get('title', 'N/A')}] "
                f"by {item.get('upper', {}).get('name', 'N/A')}"
            )

        content = "\n".join(content_lines)

        return {
            "content": content,
            "content_type": "text",
            "metadata": {
                "media_id": ml_id,
                "folder_name": folder_name,
                "item_count": len(items),
                "total_count": folder_count,
                "content_hash": self.compute_hash(content),
            },
        }

    def _fetch_history_content(self, aid_str: str) -> dict:
        """Fetch a history entry — delegates to video content lookup."""
        # History entries are videos; reuse video fetch
        return self._fetch_video_content(aid_str)

    def _fetch_subtitles(self, aid: int, cid: int) -> str:
        """Attempt to fetch subtitles/CC for a video via the player API."""
        if not cid:
            return ""

        data = self._get(
            "/x/player/wbi/v2", params={"aid": aid, "cid": cid}
        )
        if not data:
            return ""

        subtitle_data = data.get("subtitle", {})
        subtitles_list = subtitle_data.get("subtitles", [])
        if not subtitles_list:
            return ""

        # Pick the first available subtitle URL (prefer Chinese)
        chosen = subtitles_list[0]
        for sub in subtitles_list:
            if sub.get("lan_doc", "").startswith("中文"):
                chosen = sub
                break

        sub_url = chosen.get("subtitle_url", "")
        if not sub_url:
            return ""

        # Bilibili subtitle URLs may be relative
        if sub_url.startswith("//"):
            sub_url = "https:" + sub_url

        try:
            resp = self.session.get(sub_url, timeout=self.TIMEOUT)
            resp.raise_for_status()
            sub_json = resp.json()
            body = sub_json.get("body", [])
            lines = []
            for entry in body:
                text = entry.get("content", "")
                if text:
                    lines.append(text)
            return "\n".join(lines)
        except (requests.RequestException, ValueError) as e:
            self.logger.warning(
                "Failed to fetch subtitles for aid=%s cid=%s: %s", aid, cid, str(e)
            )
            return ""

    # ── private: utilities ───────────────────────────────────────────────

    @staticmethod
    def _parse_timestamp(ts: int | float) -> datetime:
        """Parse a Unix timestamp into a timezone-aware UTC datetime."""
        if not ts or ts <= 0:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)


# ── Registration ────────────────────────────────────────────────────────────

from src.sync import _register  # noqa: E402

_register("bilibili", BilibiliConnector)
