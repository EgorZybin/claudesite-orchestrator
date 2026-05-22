from __future__ import annotations

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models.site_version import SiteVersion
from app.db.repos.site_versions import SiteVersionRepository

logger = logging.getLogger(__name__)


class SiteStorageError(Exception):
    """Базовая ошибка storage-адаптера (filesystem, git, валидация путей)."""


@dataclass
class WrittenVersion:
    """Результат `write_version` — что caller'у нужно сразу же знать."""

    version_num: int
    version_dir: Path
    git_sha: str | None
    db_row: SiteVersion


class FilesystemSiteStorage:
    """Per-site versioned storage на локальной ФС + git per site.

    Создаётся с открытой Session — DB-операции (запись в site_versions, обновление
    sites.current_version_id) делаются в этой сессии. Caller отвечает за commit.
    """

    def __init__(self, session: Session, root: Path | str = "/var/claudesite/sites") -> None:
        self._s = session
        self._root = Path(root)
        self._versions_repo = SiteVersionRepository(session)


    def site_dir(self, site_id: int) -> Path:
        """Корневая директория сайта (родитель v1/, v2/, current)."""
        return self._root / str(site_id)

    def current_dir(self, site_id: int) -> Path:
        """Путь к активной версии через symlink — резолвится в v{N}/."""
        return self.site_dir(site_id) / "current"

    def version_dir(self, site_id: int, version_num: int) -> Path:
        return self.site_dir(site_id) / f"v{version_num}"


    def write_version(
        self,
        site_id: int,
        files: dict[str, str],
        *,
        comment: str,
        manifest: dict | None = None,
    ) -> WrittenVersion:
        """Записать новую черновую версию.

        `files` — dict из workspace-relative POSIX-путей в UTF-8 контент.
        `manifest` опционален; если None, парсится из `files["manifest.json"]`.
        Создаёт git-репо на первой версии, коммитит все файлы каждой версии.
        Версия получает статус `draft` — `switch_current` потом промотит в published.
        """
        if not files:
            raise SiteStorageError("write_version: empty files dict")

        version_num = self._versions_repo.next_version_num(site_id)
        target = self.version_dir(site_id, version_num)

        if target.exists():
            raise SiteStorageError(f"version dir already exists: {target}")

        self.site_dir(site_id).mkdir(parents=True, exist_ok=True)
        target.mkdir(parents=True, exist_ok=False)
        target_abs = target.resolve()

        for rel, content in files.items():
            full = self._safe_join(target, target_abs, rel)
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")

        if manifest is None:
            manifest_text = files.get("manifest.json")
            if manifest_text:
                try:
                    manifest = json.loads(manifest_text)
                except json.JSONDecodeError as e:
                    raise SiteStorageError(f"manifest.json invalid JSON: {e}") from e
            else:
                manifest = {}

        git_sha = self._git_commit_version(site_id, version_num, comment)

        row = self._versions_repo.create(
            site_id=site_id,
            version_num=version_num,
            manifest_json=manifest or {},
            git_commit_sha=git_sha,
            comment=comment,
            status="draft",
        )

        logger.info(
            "site_storage_write site_id=%s version=%s files=%d git=%s",
            site_id,
            version_num,
            len(files),
            (git_sha or "(none)")[:8],
        )
        return WrittenVersion(
            version_num=version_num,
            version_dir=target,
            git_sha=git_sha,
            db_row=row,
        )


    def read_version(
        self,
        site_id: int,
        version_num: int | None = None,
    ) -> dict[str, str]:
        """Вернуть {relative_posix_path: content} для версии.

        Если `version_num=None` — читает current. Если current не существует —
        бросает SiteStorageError. `.git/` и его содержимое не включаются в результат.
        """
        if version_num is None:
            current = self.current_dir(site_id)
            if not (current.is_symlink() or current.is_dir()):
                raise SiteStorageError(f"no current version for site_id={site_id}")
            base = current.resolve()
        else:
            base = self.version_dir(site_id, version_num)
            if not base.is_dir():
                raise SiteStorageError(f"version dir not found: {base}")

        out: dict[str, str] = {}
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(base).as_posix()
            if rel == ".git" or rel.startswith(".git/"):
                continue
            try:
                out[rel] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                logger.info("site_storage_skip_binary path=%s", rel)
        return out


    def switch_current(self, site_id: int, version_num: int) -> SiteVersion:
        """Атомарно переключить symlink `current` на v{N} + publish в БД.

        В БД: status старой published-версии → archived, новой → published,
        `sites.current_version_id` указывает на новую.
        """
        target = self.version_dir(site_id, version_num)
        if not target.is_dir():
            raise SiteStorageError(f"version dir not found: {target}")

        version_row = self._versions_repo.get_by_version_num(site_id, version_num)
        if version_row is None:
            raise SiteStorageError(
                f"version {version_num} of site {site_id} not in site_versions table",
            )

        current = self.current_dir(site_id)
        tmp_link = self.site_dir(site_id) / f".current.tmp.{os.getpid()}"
        if tmp_link.is_symlink() or tmp_link.exists():
            tmp_link.unlink()
        tmp_link.symlink_to(f"v{version_num}", target_is_directory=True)
        os.replace(tmp_link, current)

        published = self._versions_repo.publish(version_row.id)
        logger.info(
            "site_storage_switch site_id=%s version=%s prev_status=%s",
            site_id,
            version_num,
            version_row.status,
        )
        return published


    def list_versions(
        self,
        site_id: int,
        *,
        limit: int | None = None,
    ) -> list[SiteVersion]:
        """Версии сайта, отсортированы по убыванию version_num."""
        return self._versions_repo.list_for_site(site_id, limit=limit)

    @staticmethod
    def _safe_join(target: Path, target_abs: Path, rel: str) -> Path:
        """Resolve rel внутри target_abs; raise если выходит за пределы."""
        rel_clean = rel.lstrip("/")
        if not rel_clean:
            raise SiteStorageError(f"empty file path")
        full = (target / rel_clean).resolve()
        try:
            full.relative_to(target_abs)
        except ValueError:
            raise SiteStorageError(f"path escapes version dir: {rel}")
        return full

    def _git_commit_version(self, site_id: int, version_num: int, comment: str) -> str | None:
        """Коммитит все файлы только что записанной версии в per-site git-репо.

        Репо живёт в `site_dir/.git` (накрывает все v1/v2/... подпапки).
        Возвращает commit SHA или None если git упал (graceful — версии работают и без git).
        """
        site_dir = self.site_dir(site_id)
        git_dir = site_dir / ".git"

        try:
            if not git_dir.is_dir():
                self._git(site_dir, "init", "-q")
                self._git(site_dir, "config", "user.email", "claudesite@localhost")
                self._git(site_dir, "config", "user.name", "claudesite")
            self._git(site_dir, "add", "-A")
            status = self._git(site_dir, "status", "--porcelain", capture=True)
            if not status.strip():
                logger.info(
                    "site_storage_git_nochanges site_id=%s version=%s",
                    site_id,
                    version_num,
                )
                return None
            commit_msg = f"v{version_num}: {comment}"[:200]
            self._git(site_dir, "commit", "-q", "-m", commit_msg)
            sha = self._git(site_dir, "rev-parse", "HEAD", capture=True).strip()
            return sha or None
        except Exception as e:
            logger.warning("site_storage_git_failed site_id=%s err=%s", site_id, e)
            return None

    @staticmethod
    def _git(cwd: Path, *args: str, capture: bool = False) -> str:
        r = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
        )
        if r.returncode != 0:
            raise SiteStorageError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
        return r.stdout if capture else ""
