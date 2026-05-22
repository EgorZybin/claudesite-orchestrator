from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WpMediaResult:
    attachment_id: int
    source_url: str
    filename: str


@dataclass(frozen=True)
class WpPostResult:
    post_id: int
    link: str
    slug: str
    post_type: str
    status: str


class WordPressRestClient:
    def __init__(
        self,
        base_url: str,
        auth_user: str,
        auth_password: str,
        *,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._auth = (auth_user, auth_password)
        self._timeout = httpx.Timeout(
            connect=15.0, read=timeout_seconds, write=timeout_seconds, pool=15.0,
        )

    def upload_media(
        self,
        content: bytes,
        *,
        filename: str,
        mime_type: str = "image/png",
        alt_text: str | None = None,
        title: str | None = None,
        caption: str | None = None,
    ) -> WpMediaResult:
        """Загрузить файл как WP media attachment. Возвращает attachment_id + URL."""
        url = f"{self._base}/wp/v2/media"
        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": mime_type,
        }
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, content=content, headers=headers, auth=self._auth)
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"WP REST media upload failed: HTTP {r.status_code}: {r.text[:400]}",
                    request=r.request, response=r,
                )
            data = r.json()
            attachment_id = int(data["id"])
            source_url = str(data.get("source_url") or "")

        meta_payload: dict[str, object] = {}
        if title:
            meta_payload["title"] = title
        if alt_text:
            meta_payload["alt_text"] = alt_text
        if caption:
            meta_payload["caption"] = caption
        if meta_payload:
            with httpx.Client(timeout=self._timeout) as client:
                client.post(
                    f"{self._base}/wp/v2/media/{attachment_id}",
                    json=meta_payload, auth=self._auth,
                )

        logger.info(
            "wp_rest_media_uploaded attachment_id=%s filename=%s url=%s",
            attachment_id, filename, source_url,
        )
        return WpMediaResult(
            attachment_id=attachment_id,
            source_url=source_url,
            filename=filename,
        )

    def create_post(
        self,
        rest_base: str,
        *,
        title: str,
        content: str = "",
        excerpt: str = "",
        status: str = "publish",
        slug: str | None = None,
        author: int | None = None,
        featured_media: int | None = None,
        categories: list[int] | None = None,
        tags: list[int] | None = None,
        acf: dict | None = None,
        meta: dict | None = None,
        extra: dict | None = None,
    ) -> WpPostResult:
        """Создать запись через WP REST.

        ``rest_base`` — slug-эндпоинт коллекции (`posts`, `pages`, `services`, и т.д.).
        ``acf`` — словарь ACF-полей; ACF плагин разбирает форматы (repeater =
        list of dicts, image = attachment_id integer, и т.п.).
        """
        url = f"{self._base}/wp/v2/{rest_base.strip('/')}"
        payload: dict[str, object] = {
            "title": title,
            "content": content,
            "status": status,
        }
        if excerpt:
            payload["excerpt"] = excerpt
        if slug:
            payload["slug"] = slug
        if author:
            payload["author"] = int(author)
        if featured_media:
            payload["featured_media"] = int(featured_media)
        if categories:
            payload["categories"] = list(categories)
        if tags:
            payload["tags"] = list(tags)
        if acf:
            payload["acf"] = acf
        if meta:
            payload["meta"] = meta
        if extra:
            payload.update(extra)

        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, json=payload, auth=self._auth)
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"WP REST create failed: HTTP {r.status_code}: {r.text[:500]}",
                    request=r.request, response=r,
                )
            data = r.json()
        result = WpPostResult(
            post_id=int(data["id"]),
            link=str(data.get("link", "")),
            slug=str(data.get("slug", "")),
            post_type=str(data.get("type", "")),
            status=str(data.get("status", "")),
        )
        logger.info(
            "wp_rest_post_created post_id=%s type=%s slug=%s status=%s",
            result.post_id, result.post_type, result.slug, result.status,
        )
        return result

    def update_post(
        self, rest_base: str, post_id: int, *, fields: dict
    ) -> dict:
        """PATCH-обновление полей записи (WP REST принимает POST на /<id>)."""
        url = f"{self._base}/wp/v2/{rest_base.strip('/')}/{int(post_id)}"
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, json=fields, auth=self._auth)
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"WP REST update failed: HTTP {r.status_code}: {r.text[:500]}",
                    request=r.request, response=r,
                )
            return r.json()

    def get_post(self, rest_base: str, post_id: int, *, context: str = "view") -> dict:
        url = f"{self._base}/wp/v2/{rest_base.strip('/')}/{int(post_id)}"
        with httpx.Client(timeout=self._timeout) as client:
            r = client.get(url, params={"context": context}, auth=self._auth)
            r.raise_for_status()
            return r.json()

    def delete_post(self, rest_base: str, post_id: int, *, force: bool = True) -> dict:
        url = f"{self._base}/wp/v2/{rest_base.strip('/')}/{int(post_id)}"
        with httpx.Client(timeout=self._timeout) as client:
            r = client.delete(url, params={"force": "true" if force else "false"}, auth=self._auth)
            r.raise_for_status()
            return r.json()

    def list_post_ids(self, rest_base: str, *, per_page: int = 100, status: str = "any") -> list[int]:
        """Простой list — для cleanup-операций."""
        url = f"{self._base}/wp/v2/{rest_base.strip('/')}"
        with httpx.Client(timeout=self._timeout) as client:
            r = client.get(url, params={"per_page": per_page, "status": status}, auth=self._auth)
            r.raise_for_status()
            return [int(p["id"]) for p in r.json()]

    def create_term(
        self, taxonomy_rest_base: str, *, name: str, slug: str | None = None,
        description: str = "", parent: int | None = None,
    ) -> dict:
        """Создать term в указанной таксономии (`categories`, `tags`,
        `service-categories`, ...)."""
        url = f"{self._base}/wp/v2/{taxonomy_rest_base.strip('/')}"
        payload: dict[str, object] = {"name": name, "description": description}
        if slug:
            payload["slug"] = slug
        if parent:
            payload["parent"] = int(parent)
        with httpx.Client(timeout=self._timeout) as client:
            r = client.post(url, json=payload, auth=self._auth)
            if r.status_code == 400 and "term_exists" in r.text:
                exists = client.get(url, params={"slug": slug or self._slugify(name)}, auth=self._auth)
                exists.raise_for_status()
                rows = exists.json()
                if rows:
                    return rows[0]
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(
                    f"WP REST term create failed: HTTP {r.status_code}: {r.text[:400]}",
                    request=r.request, response=r,
                )
            return r.json()

    @staticmethod
    def _slugify(text: str) -> str:
        import re, unicodedata
        s = unicodedata.normalize("NFKD", text)
        s = "".join(c for c in s if not unicodedata.combining(c))
        s = re.sub(r"[^a-zA-Z0-9\s-]", "", s).strip().lower()
        s = re.sub(r"[\s-]+", "-", s)
        return s[:96]
