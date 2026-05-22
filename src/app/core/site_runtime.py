from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import SiteConfigNotFoundError, SiteConfigValidationError, UnknownSiteError
from app.core.site_config_schema import SiteFileConfig
from app.db.models.enums import SiteMode
from app.db.repos.sites import SiteRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SiteRuntime:
    """Эффективная конфигурация для запуска задач одного сайта."""

    slug: str
    site_id: int
    db_mode: SiteMode
    file: SiteFileConfig

    @property
    def effective_mode(self) -> SiteMode:
        return self.file.mode


class SiteRuntimeResolver:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def config_path(self, slug: str) -> Path:
        root = self._settings.sites_config_root_path()
        return root / slug / "config.yaml"

    def load_file_config(self, slug: str) -> SiteFileConfig:
        path = self.config_path(slug)
        if not path.is_file():
            raise SiteConfigNotFoundError(str(path))
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except OSError as e:
            raise SiteConfigNotFoundError(str(path)) from e
        if raw is None or not isinstance(raw, dict):
            raise SiteConfigValidationError(f"Config must be a YAML mapping: {path}")
        try:
            return SiteFileConfig.model_validate(raw)
        except ValidationError as e:
            raise SiteConfigValidationError(str(e)) from e

    def resolve(self, session: Session, slug: str) -> SiteRuntime:
        repo = SiteRepository(session)
        row = repo.get_by_slug(slug)
        if row is None:
            raise UnknownSiteError(slug)

        file_cfg = self.load_file_config(slug)

        if row.mode != file_cfg.mode:
            logger.warning(
                "site_mode_mismatch",
                extra={
                    "slug": slug,
                    "db_mode": row.mode.value,
                    "file_mode": file_cfg.mode.value,
                },
            )

        return SiteRuntime(
            slug=slug,
            site_id=row.id,
            db_mode=row.mode,
            file=file_cfg,
        )
