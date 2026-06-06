"""WeChat Official Account (微信公众号) sync connector.

Connects to the WeChat Official Account API to sync published articles
into the Cognitive OS (AI Second Brain).

Uses the WeChat MP API:
  - /cgi-bin/token — OAuth2 client_credential for access_token
  - /cgi-bin/freepublish/batchget — list published articles
  - /cgi-bin/freepublish/getarticle — fetch full article content

Credentials in self.config:
  - app_id: WeChat Official Account AppID
  - app_secret: WeChat Official Account AppSecret
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

from src.sync.connector_base import BaseSyncConnector
from src.sync.models import SyncConnectionResult, SyncResource


# ── API constants ──

WECHAT_API_BASE = "https://api.weixin.qq.com"
TOKEN_URL = f"{WECHAT_API_BASE}/cgi-bin/token"
FREEPUBLISH_BATCHGET_URL = f"{WECHAT_API_BASE}/cgi-bin/freepublish/batchget"
FREEPUBLISH_GETARTICLE_URL = f"{WECHAT_API_BASE}/cgi-bin/freepublish/getarticle"
MATERIAL_BATCHGET_URL = f"{WECHAT_API_BASE}/cgi-bin/material/batchget_material"

DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_PAGE_SIZE = 20
TOKEN_EXPIRY_MARGIN = 120  # refresh 2 minutes before actual expiry


class WechatMpConnector(BaseSyncConnector):
    """Sync connector for WeChat Official Account (微信公众号).

    Fetches published articles from a WeChat Official Account using the
    official WeChat MP API with app_id and app_secret credentials.
    """

    connector_type: str = "wechat_mp"

    def __init__(self, config: dict | None = None) -> None:
        super().__init__(config)
        self.logger = logging.getLogger("sync.connector.wechat_mp")
        # Token cache: (access_token, expires_at_epoch)
        self._token_cache: tuple[str, float] | None = None
        self._timeout: float = float(config.get("timeout", DEFAULT_TIMEOUT)) if config else DEFAULT_TIMEOUT

    # ── Public API ──

    def test_connection(self) -> SyncConnectionResult:
        """Validate credentials and connectivity to WeChat MP API.

        Tries to obtain an access_token, then counts published articles.
        """
        app_id = self._app_id
        app_secret = self._app_secret

        if not app_id or not app_secret:
            return SyncConnectionResult(
                success=False,
                message="Missing credentials: app_id and app_secret are required",
                resources_count=0,
            )

        token, token_error = self._get_access_token()
        if token_error:
            self.logger.warning("wechat_mp_test_connection_token_failed", extra={"error": token_error})
            return SyncConnectionResult(
                success=False,
                message=f"Failed to obtain access token: {token_error}",
                resources_count=0,
            )

        # Try to count published articles
        count = 0
        try:
            articles = self._fetch_published_articles(token)
            count = len(articles)
        except Exception as exc:
            self.logger.warning("wechat_mp_test_connection_list_failed", extra={"error": str(exc)})
            # Token is valid even if listing fails — still report partial success
            return SyncConnectionResult(
                success=True,
                message=f"Authenticated but could not list articles: {exc}",
                resources_count=0,
            )

        return SyncConnectionResult(
            success=True,
            message=f"Connected successfully. {count} published articles found.",
            resources_count=count,
        )

    def list_resources(self) -> list[SyncResource]:
        """List all published articles from the WeChat Official Account.

        Paginates through the freepublish/batchget endpoint to collect
        every published article.
        """
        token, token_error = self._get_access_token()
        if token_error:
            self.logger.error("wechat_mp_list_resources_token_failed", extra={"error": token_error})
            return []

        try:
            raw_articles = self._fetch_published_articles(token)
        except Exception:
            self.logger.exception("wechat_mp_list_resources_failed")
            return []

        resources: list[SyncResource] = []
        for article in raw_articles:
            article_id = article.get("article_id", "")
            content_node = article.get("content", {}).get("news_item", [{}])
            if not content_node:
                continue
            news = content_node[0] if isinstance(content_node, list) else content_node
            title = news.get("title", article_id)
            update_time = article.get("update_time", 0)
            updated_at = (
                datetime.fromtimestamp(update_time, tz=timezone.utc)
                if update_time
                else None
            )

            # Compute approximate size from title + digest
            digest = news.get("digest", "")
            size_bytes = len(title.encode("utf-8")) + len(digest.encode("utf-8"))

            resources.append(SyncResource(
                resource_id=article_id,
                name=title,
                resource_type="article",
                updated_at=updated_at,
                size_bytes=size_bytes,
                metadata={
                    "title": title,
                    "digest": digest,
                    "url": news.get("url", ""),
                    "update_time": update_time,
                    "author": news.get("author", ""),
                    "thumb_media_id": news.get("thumb_media_id", ""),
                    "need_open_comment": news.get("need_open_comment", 0),
                    "only_fans_can_comment": news.get("only_fans_can_comment", 0),
                },
            ))

        self.logger.info("wechat_mp_list_resources_done", extra={"count": len(resources)})
        return resources

    def fetch_changes(self, since: datetime | None) -> list[dict[str, Any]]:
        """Return change descriptors for articles updated since *since*.

        Returns a list of lightweight dicts each containing:
          - resource_id, name, resource_type, updated_at
          - change_type ("new" | "updated" | "deleted")
          - metadata

        When *since* is None, all published articles are returned as "new".
        """
        resources = self.list_resources()
        if not resources:
            return []

        since_dt = since  # timezone-aware or None
        changes: list[dict[str, Any]] = []

        for res in resources:
            if since_dt is not None and res.updated_at is not None and res.updated_at <= since_dt:
                continue

            raw_update = res.metadata.get("update_time", 0)
            changes.append({
                "resource_id": res.resource_id,
                "name": res.name,
                "resource_type": res.resource_type,
                "updated_at": res.updated_at,
                "change_type": "new" if since_dt is None else "updated",
                "metadata": {
                    "title": res.name,
                    "digest": res.metadata.get("digest", ""),
                    "url": res.metadata.get("url", ""),
                    "update_time": raw_update,
                    "author": res.metadata.get("author", ""),
                },
            })

        self.logger.info(
            "wechat_mp_fetch_changes_done",
            extra={"count": len(changes), "since": str(since)},
        )
        return changes

    def fetch_content(self, resource_id: str) -> dict[str, Any]:
        """Fetch full article content by article_id.

        Returns:
            {"content": str, "content_type": str, "metadata": dict}

        The content is retrieved from the WeChat MP API as HTML and
        includes the article title, author, publish time, and body.
        """
        token, token_error = self._get_access_token()
        if token_error:
            self.logger.error("wechat_mp_fetch_content_token_failed", extra={"error": token_error})
            return {
                "content": "",
                "content_type": "html",
                "metadata": {"error": token_error},
            }

        try:
            resp = requests.post(
                FREEPUBLISH_GETARTICLE_URL,
                params={"access_token": token},
                json={"article_id": resource_id},
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.Timeout:
            msg = f"Request timed out fetching article {resource_id}"
            self.logger.warning("wechat_mp_fetch_content_timeout", extra={"resource_id": resource_id})
            return {
                "content": "",
                "content_type": "html",
                "metadata": {"error": msg, "resource_id": resource_id},
            }
        except requests.RequestException as exc:
            self.logger.warning(
                "wechat_mp_fetch_content_request_failed",
                extra={"resource_id": resource_id, "error": str(exc)},
            )
            return {
                "content": "",
                "content_type": "html",
                "metadata": {"error": str(exc), "resource_id": resource_id},
            }

        data = resp.json()

        # Check for WeChat API-level errors
        wechat_err = self._check_wechat_error(data)
        if wechat_err:
            self.logger.warning(
                "wechat_mp_fetch_content_api_error",
                extra={"resource_id": resource_id, "error": wechat_err},
            )
            return {
                "content": "",
                "content_type": "html",
                "metadata": {"error": wechat_err, "resource_id": resource_id},
            }

        # Extract article content
        news_item = data.get("news_item") or data.get("content", {}).get("news_item", [])
        if isinstance(news_item, list) and news_item:
            article = news_item[0]
        elif isinstance(news_item, dict):
            article = news_item
        else:
            article = data

        title = article.get("title", "")
        author = article.get("author", "")
        digest = article.get("digest", "")
        url = article.get("url", "")
        html_content = article.get("content", "")
        need_open_comment = article.get("need_open_comment", 0)
        only_fans_can_comment = article.get("only_fans_can_comment", 0)

        # Build rich content: markdown-styled title + HTML body
        parts: list[str] = []
        if title:
            # Escape HTML-ish title characters for safety
            safe_title = title.replace("<", "&lt;").replace(">", "&gt;")
            parts.append(f'<h1 class="wechat-article-title">{safe_title}</h1>')
        if author:
            parts.append(f'<p class="wechat-article-author">作者: {author}</p>')
        if digest:
            parts.append(f'<p class="wechat-article-digest">{digest}</p>')
        if html_content:
            parts.append(f'<div class="wechat-article-body">{html_content}</div>')

        content = "\n".join(parts) if parts else ""

        # Compute content hash via parent helper
        content_hash = self.compute_hash(content) if content else ""

        return {
            "content": content,
            "content_type": "html",
            "metadata": {
                "title": title,
                "author": author,
                "digest": digest,
                "url": url,
                "content_hash": content_hash,
                "need_open_comment": need_open_comment,
                "only_fans_can_comment": only_fans_can_comment,
                "source": "wechat_mp_api",
                "resource_id": resource_id,
            },
        }

    # ── Internal helpers ──

    @property
    def _app_id(self) -> str:
        return self.config.get("app_id", "")

    @property
    def _app_secret(self) -> str:
        return self.config.get("app_secret", "")

    def _get_access_token(self) -> tuple[str, str]:
        """Obtain a WeChat MP access_token, with caching.

        Returns:
            (access_token, "") on success, or ("", error_message) on failure.
        """
        # Return cached token if still valid
        now = time.time()
        if self._token_cache is not None:
            cached_token, expires_at = self._token_cache
            if now < expires_at:
                return cached_token, ""
            self._token_cache = None  # expired

        app_id = self._app_id
        app_secret = self._app_secret
        if not app_id or not app_secret:
            return "", "app_id and app_secret are not set in config"

        try:
            resp = requests.get(
                TOKEN_URL,
                params={
                    "grant_type": "client_credential",
                    "appid": app_id,
                    "secret": app_secret,
                },
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.Timeout:
            return "", "Token request timed out"
        except requests.RequestException as exc:
            return "", f"Token request failed: {exc}"

        data = resp.json()
        access_token = data.get("access_token", "")
        if not access_token:
            errcode = data.get("errcode", -1)
            errmsg = data.get("errmsg", "Unknown error")
            return "", f"[{errcode}] {errmsg}"

        expires_in = data.get("expires_in", 7200)
        expires_at = now + expires_in - TOKEN_EXPIRY_MARGIN
        self._token_cache = (access_token, max(expires_at, now + 1))
        return access_token, ""

    @staticmethod
    def _check_wechat_error(data: dict[str, Any]) -> str:
        """Check if a WeChat API response contains an error.

        Returns an empty string if the response is OK, or an error message.
        """
        errcode = data.get("errcode", 0)
        if errcode is None or errcode == 0:
            return ""
        errmsg = data.get("errmsg", "Unknown WeChat API error")
        return f"WeChat API error [{errcode}]: {errmsg}"

    def _fetch_published_articles(self, access_token: str) -> list[dict[str, Any]]:
        """Paginate through all published articles via freepublish/batchget.

        Returns a flat list of article dicts from the WeChat API.
        """
        all_items: list[dict[str, Any]] = []
        offset = 0

        while True:
            try:
                resp = requests.post(
                    FREEPUBLISH_BATCHGET_URL,
                    params={"access_token": access_token},
                    json={
                        "offset": offset,
                        "count": DEFAULT_PAGE_SIZE,
                        "no_content": 1,
                    },
                    timeout=self._timeout,
                )
                resp.raise_for_status()
            except requests.RequestException as exc:
                self.logger.warning(
                    "wechat_mp_fetch_articles_request_failed",
                    extra={"offset": offset, "error": str(exc)},
                )
                break

            data = resp.json()

            # Check for WeChat API error
            wechat_err = self._check_wechat_error(data)
            if wechat_err:
                self.logger.warning(
                    "wechat_mp_fetch_articles_api_error",
                    extra={"offset": offset, "error": wechat_err},
                )
                break

            items = data.get("item", [])
            if not items:
                break

            all_items.extend(items)
            total = data.get("total_count", 0)
            if offset + len(items) >= total:
                break
            offset += DEFAULT_PAGE_SIZE

        return all_items


# ── Auto-registration ──

from src.sync import _register  # noqa: E402

_register("wechat_mp", WechatMpConnector)
