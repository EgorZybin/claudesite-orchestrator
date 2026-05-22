from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WpCategory:
    term_id: int
    term_taxonomy_id: int
    slug: str
    name: str
    count: int


@dataclass(frozen=True)
class WpPage:
    post_id: int
    slug: str
    title: str


_VALID_PREFIX_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"


def _validate_prefix(prefix: str) -> str:
    if not prefix or len(prefix) > 32 or any(c not in _VALID_PREFIX_CHARS for c in prefix):
        raise ValueError(f"Invalid wp table_prefix: {prefix!r}")
    return prefix


class WordPressDbAdapter:
    """Connection holder + write helpers for one WP installation."""

    def __init__(self, database_url: str, table_prefix: str = "wp_") -> None:
        self._url = database_url
        self._prefix = _validate_prefix(table_prefix)
        self._engine: Engine | None = None
        self._sessionmaker: sessionmaker | None = None

    @property
    def posts_table(self) -> str:
        return f"{self._prefix}posts"

    @property
    def postmeta_table(self) -> str:
        return f"{self._prefix}postmeta"

    @property
    def terms_table(self) -> str:
        return f"{self._prefix}terms"

    @property
    def term_taxonomy_table(self) -> str:
        return f"{self._prefix}term_taxonomy"

    @property
    def term_relationships_table(self) -> str:
        return f"{self._prefix}term_relationships"

    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = create_engine(self._url, pool_pre_ping=True, future=True)
            self._sessionmaker = sessionmaker(bind=self._engine, expire_on_commit=False, future=True)
        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        self.engine()
        assert self._sessionmaker is not None
        s = self._sessionmaker()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def ping(self) -> None:
        """Проверка подключения; кидает SQLAlchemyError если БД недоступна."""
        with self.session() as s:
            s.execute(text("SELECT 1"))

    def insert_post(
        self,
        *,
        title: str,
        slug: str,
        content_html: str,
        excerpt: str = "",
        post_status: str = "publish",
        post_type: str = "post",
        author_id: int = 1,
        comment_status: str = "closed",
        ping_status: str = "closed",
    ) -> int:
        """Вставить запись в wp_posts. Возвращает ID нового поста.

        Заполняет post_date/post_date_gmt текущим временем (UTC). Поля,
        специфичные для Yoast/ACF/прочих плагинов, добавляются через
        upsert_postmeta() после получения post_id.
        """
        now = datetime.utcnow().replace(microsecond=0)
        with self.session() as s:
            r = s.execute(
                text(
                    f"""
                    INSERT INTO {self.posts_table} (
                        post_author, post_date, post_date_gmt, post_content, post_title,
                        post_excerpt, post_status, comment_status, ping_status, post_password,
                        post_name, to_ping, pinged, post_modified, post_modified_gmt,
                        post_content_filtered, post_parent, guid, menu_order, post_type,
                        post_mime_type, comment_count
                    ) VALUES (
                        :author_id, :now, :now, :content, :title,
                        :excerpt, :status, :comment_status, :ping_status, '',
                        :slug, '', '', :now, :now,
                        '', 0, '', 0, :post_type,
                        '', 0
                    )
                    """
                ),
                {
                    "author_id": author_id,
                    "now": now,
                    "content": content_html,
                    "title": title,
                    "excerpt": excerpt,
                    "status": post_status,
                    "comment_status": comment_status,
                    "ping_status": ping_status,
                    "slug": slug,
                    "post_type": post_type,
                },
            )
            post_id = int(r.lastrowid)
        logger.info("wp_post_inserted id=%s slug=%s title=%s status=%s", post_id, slug, title[:60], post_status)
        return post_id

    def update_post(
        self,
        post_id: int,
        *,
        title: str | None = None,
        content_html: str | None = None,
        excerpt: str | None = None,
        post_status: str | None = None,
        slug: str | None = None,
    ) -> None:
        """Точечный UPDATE по wp_posts. NULL-аргументы пропускаются."""
        fields: dict[str, str] = {}
        params: dict[str, object] = {"id": post_id}
        if title is not None:
            fields["post_title"] = ":title"
            params["title"] = title
        if content_html is not None:
            fields["post_content"] = ":content"
            params["content"] = content_html
        if excerpt is not None:
            fields["post_excerpt"] = ":excerpt"
            params["excerpt"] = excerpt
        if post_status is not None:
            fields["post_status"] = ":status"
            params["status"] = post_status
        if slug is not None:
            fields["post_name"] = ":slug"
            params["slug"] = slug
        if not fields:
            return
        now = datetime.utcnow().replace(microsecond=0)
        fields["post_modified"] = ":now"
        fields["post_modified_gmt"] = ":now"
        params["now"] = now
        set_clause = ", ".join(f"{col} = {val}" for col, val in fields.items())
        with self.session() as s:
            s.execute(text(f"UPDATE {self.posts_table} SET {set_clause} WHERE ID = :id"), params)
        logger.info("wp_post_updated id=%s fields=%s", post_id, list(fields.keys()))

    def upsert_postmeta(self, post_id: int, meta_key: str, meta_value: str) -> None:
        """INSERT или UPDATE строки в wp_postmeta для (post_id, meta_key)."""
        with self.session() as s:
            r = s.execute(
                text(
                    f"""
                    UPDATE {self.postmeta_table}
                    SET meta_value = :value
                    WHERE post_id = :pid AND meta_key = :key
                    """
                ),
                {"value": meta_value, "pid": post_id, "key": meta_key},
            )
            if r.rowcount == 0:
                s.execute(
                    text(
                        f"""
                        INSERT INTO {self.postmeta_table} (post_id, meta_key, meta_value)
                        VALUES (:pid, :key, :value)
                        """
                    ),
                    {"pid": post_id, "key": meta_key, "value": meta_value},
                )

    def list_categories(self, limit: int = 50) -> list[WpCategory]:
        """Список таксономии 'category' с slug/name/count, отсортированных по count desc."""
        with self.session() as s:
            rows = s.execute(
                text(
                    f"""
                    SELECT t.term_id, tt.term_taxonomy_id, t.slug, t.name, tt.count
                    FROM {self.terms_table} t
                    JOIN {self.term_taxonomy_table} tt ON tt.term_id = t.term_id
                    WHERE tt.taxonomy = 'category'
                    ORDER BY tt.count DESC, t.name
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            ).fetchall()
        return [WpCategory(int(r[0]), int(r[1]), str(r[2]), str(r[3]), int(r[4])) for r in rows]

    def list_top_pages(self, limit: int = 30) -> list[WpPage]:
        """Опубликованные top-level страницы (post_type=page, parent=0) — для nav-контекста."""
        with self.session() as s:
            rows = s.execute(
                text(
                    f"""
                    SELECT ID, post_name, post_title
                    FROM {self.posts_table}
                    WHERE post_type = 'page' AND post_status = 'publish' AND post_parent = 0
                    ORDER BY menu_order, post_title
                    LIMIT :lim
                    """
                ),
                {"lim": limit},
            ).fetchall()
        return [WpPage(int(r[0]), str(r[1]), str(r[2])) for r in rows]

    def lookup_term_taxonomy(self, taxonomy: str, term_slug: str) -> int | None:
        """Вернуть term_taxonomy_id для (taxonomy, term_slug) или None если не найдено."""
        with self.session() as s:
            r = s.execute(
                text(
                    f"""
                    SELECT tt.term_taxonomy_id
                    FROM {self.term_taxonomy_table} tt
                    JOIN {self.terms_table} t ON t.term_id = tt.term_id
                    WHERE tt.taxonomy = :tax AND t.slug = :slug
                    LIMIT 1
                    """
                ),
                {"tax": taxonomy, "slug": term_slug},
            ).first()
        return None if r is None else int(r[0])

    def assign_categories(self, post_id: int, term_taxonomy_ids: list[int]) -> None:
        """Связать пост с таксономиями. Дубли (post + tt_id уже связаны) игнорируются.
        Каждая успешная связь инкрементит wp_term_taxonomy.count.
        """
        if not term_taxonomy_ids:
            return
        with self.session() as s:
            for tt_id in term_taxonomy_ids:
                exists = s.execute(
                    text(
                        f"""
                        SELECT 1 FROM {self.term_relationships_table}
                        WHERE object_id = :pid AND term_taxonomy_id = :tt
                        """
                    ),
                    {"pid": post_id, "tt": tt_id},
                ).first()
                if exists:
                    continue
                s.execute(
                    text(
                        f"""
                        INSERT INTO {self.term_relationships_table} (object_id, term_taxonomy_id, term_order)
                        VALUES (:pid, :tt, 0)
                        """
                    ),
                    {"pid": post_id, "tt": tt_id},
                )
                s.execute(
                    text(
                        f"""
                        UPDATE {self.term_taxonomy_table}
                        SET count = count + 1
                        WHERE term_taxonomy_id = :tt
                        """
                    ),
                    {"tt": tt_id},
                )
        logger.info("wp_post_categorized id=%s term_taxonomy_ids=%s", post_id, term_taxonomy_ids)

    @property
    def options_table(self) -> str:
        return f"{self._prefix}options"

    def get_option(self, name: str) -> str | None:
        with self.session() as s:
            r = s.execute(
                text(f"SELECT option_value FROM {self.options_table} WHERE option_name = :n"),
                {"n": name},
            ).first()
        return None if r is None else str(r[0])

    def list_post_types(self) -> list[tuple[str, int]]:
        """Все post_types и сколько публикаций каждого. Сортировка по убыванию count."""
        with self.session() as s:
            rows = s.execute(
                text(
                    f"""
                    SELECT post_type, COUNT(*) AS c
                    FROM {self.posts_table}
                    WHERE post_status IN ('publish', 'draft', 'pending', 'private')
                    GROUP BY post_type
                    ORDER BY c DESC
                    """
                )
            ).fetchall()
        return [(str(r[0]), int(r[1])) for r in rows]

    def list_taxonomies(self) -> list[tuple[str, int]]:
        """Все таксономии (category / post_tag / custom) + сколько термов."""
        with self.session() as s:
            rows = s.execute(
                text(
                    f"""
                    SELECT taxonomy, COUNT(*) AS c
                    FROM {self.term_taxonomy_table}
                    GROUP BY taxonomy
                    ORDER BY c DESC
                    """
                )
            ).fetchall()
        return [(str(r[0]), int(r[1])) for r in rows]

    def list_templates_for_post_type(self, post_type: str = "post", limit: int = 10) -> list[tuple[str, int]]:
        """Какие .php шаблоны используются для записей данного post_type."""
        with self.session() as s:
            rows = s.execute(
                text(
                    f"""
                    SELECT pm.meta_value AS tpl, COUNT(*) AS c
                    FROM {self.postmeta_table} pm
                    JOIN {self.posts_table} p ON p.ID = pm.post_id
                    WHERE pm.meta_key = '_wp_page_template'
                      AND p.post_type = :pt
                      AND p.post_status = 'publish'
                      AND pm.meta_value <> ''
                      AND pm.meta_value <> 'default'
                    GROUP BY tpl
                    ORDER BY c DESC
                    LIMIT :lim
                    """
                ),
                {"pt": post_type, "lim": limit},
            ).fetchall()
        return [(str(r[0]), int(r[1])) for r in rows]

    def list_acf_field_groups(self) -> list[dict]:
        """Группы ACF — post_type=acf-field-group + дочерние acf-field записи.
        Возвращает [{group_id, group_title, fields:[{field_id, name, label, type}]}, ...].
        """
        with self.session() as s:
            groups = s.execute(
                text(
                    f"""
                    SELECT ID, post_title, post_name
                    FROM {self.posts_table}
                    WHERE post_type = 'acf-field-group' AND post_status = 'publish'
                    """
                )
            ).fetchall()
            result = []
            for grp in groups:
                grp_id = int(grp[0])
                fields_rows = s.execute(
                    text(
                        f"""
                        SELECT ID, post_name, post_title, post_excerpt, post_content
                        FROM {self.posts_table}
                        WHERE post_type = 'acf-field' AND post_parent = :gid
                        ORDER BY menu_order
                        """
                    ),
                    {"gid": grp_id},
                ).fetchall()
                fields = []
                for fr in fields_rows:
                    field_type = ""
                    try:
                        import json as _json
                        content = _json.loads(fr[4] or "{}")
                        field_type = str(content.get("type", ""))
                    except Exception:
                        pass
                    fields.append({
                        "field_id": str(fr[1]),       
                        "field_name": str(fr[3] or ""),
                        "label": str(fr[2]),
                        "type": field_type,
                    })
                result.append({
                    "group_id": grp_id,
                    "group_title": str(grp[1]),
                    "fields": fields,
                })
        return result

    def sample_postmeta_for_recent(self, post_type: str = "post", limit: int = 3) -> list[dict]:
        """Возвращает по 1 записи последних N публикаций данного типа со всем
        набором их postmeta — это пример «полного» паттерна публикации для темы.
        """
        with self.session() as s:
            posts = s.execute(
                text(
                    f"""
                    SELECT ID, post_title, post_name
                    FROM {self.posts_table}
                    WHERE post_type = :pt AND post_status = 'publish'
                    ORDER BY post_date DESC
                    LIMIT :lim
                    """
                ),
                {"pt": post_type, "lim": limit},
            ).fetchall()
            samples = []
            for p in posts:
                pid = int(p[0])
                metas = s.execute(
                    text(
                        f"""
                        SELECT meta_key, meta_value
                        FROM {self.postmeta_table}
                        WHERE post_id = :pid
                        ORDER BY meta_key
                        """
                    ),
                    {"pid": pid},
                ).fetchall()
                samples.append({
                    "post_id": pid,
                    "title": str(p[1]),
                    "slug": str(p[2]),
                    "meta": [(str(m[0]), str(m[1])[:300]) for m in metas],
                })
        return samples

    def detect_seo_plugin(self) -> str:
        """Эвристическая детекция активного SEO-плагина по namespace мета-ключей."""
        candidates = [
            ("yoast", "_yoast_wpseo_"),
            ("rankmath", "rank_math_"),
            ("aioseo", "_aioseo_"),
            ("seopress", "_seopress_"),
        ]
        with self.session() as s:
            for name, prefix in candidates:
                hit = s.execute(
                    text(
                        f"""
                        SELECT 1 FROM {self.postmeta_table}
                        WHERE meta_key LIKE :p LIMIT 1
                        """
                    ),
                    {"p": prefix + "%"},
                ).first()
                if hit:
                    return name
        return "none"
