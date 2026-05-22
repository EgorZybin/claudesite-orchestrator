from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.site_content import PageType


class DesignTokens(BaseModel):
    """Базовые design-tokens, которые Claude выбирает при первой генерации.

    Эти токены отражают визуальный язык сайта и помогают:
    - orchestrator'у понять что было сгенерировано (для UI/админки)
    - edit-режиму держать консистентность ('используй те же радиусы')
    """
    accent_hsl: str
    neutral_family: Literal["slate", "zinc", "stone", "gray", "neutral"]
    display_font: str
    body_font: str
    radius_base: int = Field(ge=0, le=24)
    spacing_unit: int = Field(default=4, ge=2, le=8)
    dark_mode: bool = False


class SupportsFlags(BaseModel):
    """Какие фичи реально поддерживает текущий build."""
    dark_mode: bool = False
    rtl: bool = False
    print_styles: bool = False
    reduced_motion: bool = True


class SiteManifest(BaseModel):
    """Manifest.json — корневой контракт сайт-билда."""
    schema_version: Literal["1"] = "1"
    generator: str = "claude-cli"
    generated_at: str

    page_types: list[PageType]
    page_slots: dict[PageType, list[str]]

    asset_hashes: dict[Literal["css", "js"], str]

    design_tokens: DesignTokens
    supports: SupportsFlags = SupportsFlags()

    notes: str | None = None
