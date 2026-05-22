from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, model_validator


class HeadingBlock(BaseModel):
    kind: Literal["heading"]
    props: dict[str, Any]

    @model_validator(mode="after")
    def _validate_props(self) -> "HeadingBlock":
        level = self.props.get("level")
        text = self.props.get("text")
        if not isinstance(level, int) or not (1 <= level <= 4):
            raise ValueError(f"heading.props.level must be int 1..4, got {level!r}")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("heading.props.text must be non-empty string")
        return self


class ParagraphBlock(BaseModel):
    kind: Literal["paragraph"]
    props: dict[str, Any]

    @model_validator(mode="after")
    def _validate_props(self) -> "ParagraphBlock":
        md = self.props.get("markdown")
        if not isinstance(md, str) or not md.strip():
            raise ValueError("paragraph.props.markdown must be non-empty string")
        return self


class ImageBlock(BaseModel):
    kind: Literal["image"]
    props: dict[str, Any]

    @model_validator(mode="after")
    def _validate_props(self) -> "ImageBlock":
        if "src" not in self.props:
            raise ValueError("image.props.src missing (use empty string for unset)")
        if not isinstance(self.props.get("alt"), str):
            raise ValueError("image.props.alt must be string")
        return self


class ListBlock(BaseModel):
    kind: Literal["list"]
    props: dict[str, Any]

    @model_validator(mode="after")
    def _validate_props(self) -> "ListBlock":
        items = self.props.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("list.props.items must be non-empty list")
        if not all(isinstance(x, str) and x.strip() for x in items):
            raise ValueError("list.props.items entries must be non-empty strings")
        return self


class QuoteBlock(BaseModel):
    kind: Literal["quote"]
    props: dict[str, Any]

    @model_validator(mode="after")
    def _validate_props(self) -> "QuoteBlock":
        text = self.props.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("quote.props.text must be non-empty string")
        return self


class TableBlock(BaseModel):
    kind: Literal["table"]
    props: dict[str, Any]

    @model_validator(mode="after")
    def _validate_props(self) -> "TableBlock":
        headers = self.props.get("headers")
        rows = self.props.get("rows")
        if not isinstance(headers, list) or not headers:
            raise ValueError("table.props.headers must be non-empty list")
        if not isinstance(rows, list) or not rows:
            raise ValueError("table.props.rows must be non-empty list of lists")
        return self


class CtaBlock(BaseModel):
    kind: Literal["cta"]
    props: dict[str, Any]

    @model_validator(mode="after")
    def _validate_props(self) -> "CtaBlock":
        label = self.props.get("label")
        href = self.props.get("href")
        if not isinstance(label, str) or not label.strip():
            raise ValueError("cta.props.label must be non-empty string")
        if not isinstance(href, str) or not href.strip():
            raise ValueError("cta.props.href must be non-empty string")
        style = self.props.get("style", "primary")
        if style not in ("primary", "secondary", "ghost"):
            raise ValueError(f"cta.props.style must be primary|secondary|ghost, got {style!r}")
        return self


ContentBlock = Annotated[
    Union[HeadingBlock, ParagraphBlock, ImageBlock, ListBlock, QuoteBlock, TableBlock, CtaBlock],
    Field(discriminator="kind"),
]


class FeaturesModule(BaseModel):
    kind: Literal["features"]
    data: dict[str, Any]

    @model_validator(mode="after")
    def _validate(self) -> "FeaturesModule":
        items = self.data.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("features.data.items must be non-empty list")
        for i, it in enumerate(items):
            if not isinstance(it, dict) or "title" not in it or "description" not in it:
                raise ValueError(f"features.items[{i}] missing title/description")
        return self


class StatsModule(BaseModel):
    kind: Literal["stats"]
    data: dict[str, Any]

    @model_validator(mode="after")
    def _validate(self) -> "StatsModule":
        items = self.data.get("items")
        if not isinstance(items, list) or len(items) < 2:
            raise ValueError("stats.data.items must have at least 2 entries")
        return self


class TestimonialsModule(BaseModel):
    kind: Literal["testimonials"]
    data: dict[str, Any]

    @model_validator(mode="after")
    def _validate(self) -> "TestimonialsModule":
        items = self.data.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("testimonials.data.items must be non-empty list")
        return self


class PricingModule(BaseModel):
    kind: Literal["pricing"]
    data: dict[str, Any]

    @model_validator(mode="after")
    def _validate(self) -> "PricingModule":
        plans = self.data.get("plans")
        if not isinstance(plans, list) or not plans:
            raise ValueError("pricing.data.plans must be non-empty list")
        highlighted = sum(1 for p in plans if isinstance(p, dict) and p.get("highlighted"))
        if highlighted > 1:
            raise ValueError(f"pricing: at most 1 highlighted plan, got {highlighted}")
        return self


class TeamModule(BaseModel):
    kind: Literal["team"]
    data: dict[str, Any]

    @model_validator(mode="after")
    def _validate(self) -> "TeamModule":
        members = self.data.get("members")
        if not isinstance(members, list) or not members:
            raise ValueError("team.data.members must be non-empty list")
        return self


class FaqModule(BaseModel):
    kind: Literal["faq"]
    data: dict[str, Any]

    @model_validator(mode="after")
    def _validate(self) -> "FaqModule":
        items = self.data.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("faq.data.items must be non-empty list")
        return self


class ContactInfoModule(BaseModel):
    kind: Literal["contact_info"]
    data: dict[str, Any]


class FooterModule(BaseModel):
    kind: Literal["footer"]
    data: dict[str, Any]

    @model_validator(mode="after")
    def _validate(self) -> "FooterModule":
        legal = self.data.get("legal")
        if not isinstance(legal, str) or not legal.strip():
            raise ValueError("footer.data.legal must be non-empty string")
        return self


SiteModule = Annotated[
    Union[
        FeaturesModule, StatsModule, TestimonialsModule, PricingModule,
        TeamModule, FaqModule, ContactInfoModule, FooterModule,
    ],
    Field(discriminator="kind"),
]


PageType = str


class Page(BaseModel):
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    page_type: PageType
    title: str = Field(min_length=1, max_length=200)
    seo_description: str = Field(min_length=80, max_length=320)
    hero_title: str | None = None
    hero_subtitle: str | None = None
    hero_image: str | None = None
    content_blocks: list[ContentBlock] = []
    modules_used: list[str] = []
    nav_label: str | None = None
    nav_order: int | None = None


class SiteMeta(BaseModel):
    brand: str
    tagline: str | None = None
    industry: str
    language: str


class SiteContent(BaseModel):
    """Корневая структура контента сайта — выход content_plan."""

    site_meta: SiteMeta
    pages: list[Page] = Field(min_length=1)
    modules: list[SiteModule] = []
