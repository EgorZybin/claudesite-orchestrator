from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.worker"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "claudesite-orchestrator"
    database_url: str = Field(
        default="mysql+pymysql://claudesite:claudesite@127.0.0.1:3306/claudesite",
        description="SQLAlchemy database URL",
    )
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    idempotency_ttl_seconds: int = Field(
        default=604800,
        ge=60,
        le=2592000,
        description="TTL (sec) for idempotency keys in Redis. Default: 7d. Lower for dev/testing.",
    )
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    orchestrator_api_token: str | None = None
    sites_config_root: str = Field(
        default="sites",
        description="Path to directory containing site_slug/config.yaml",
    )

    def sites_config_root_path(self) -> Path:
        return Path(self.sites_config_root).expanduser().resolve()
    claude_cli_argv: str = Field(
        default="claude",
        description="Shell-split argv; full prompt is written to stdin.",
    )
    claude_gateway_url: str | None = Field(
        default=None,
        description="Base URL of remote Claude CLI gateway (used when LLM_PROVIDER=claude_remote).",
    )
    claude_gateway_token: str | None = Field(
        default=None,
        description="Bearer token for the remote Claude CLI gateway.",
    )
    claude_gateway_ca_bundle: str | None = Field(
        default=None,
        description="Path to CA cert (PEM) for verifying the gateway TLS endpoint. "
                    "Used when the gateway runs with a self-signed cert pinned by IP.",
    )
    llm_provider: str = Field(
        default="claude_local",
        description="LLM provider: claude_local, claude_remote, or openai",
    )
    llm_openai_model: str = Field(
        default="openai/gpt-5",
        description="Model id for OpenAI-compatible text generation endpoint.",
    )
    llm_openai_timeout_seconds: float = Field(default=180.0, ge=5)
    llm_openai_vision_model: str = Field(
        default="claude-sonnet-4.5",
        description=(
            "Model id для vision-вызовов (analyze-url дизайн-скан). Использует "
            "тот же OPENAI_BASE_URL/OPENAI_API_KEY, что и text. Default claude-"
            "sonnet-4.5 — топ vision-модель у vsellm, существенно точнее в "
            "pixel-color extraction чем gpt-4o-mini (тот склонен подменять "
            "конкретные пиксели стереотипными палитрами по индустрии). gpt-4o "
            "тоже сильнее mini, но всё ещё уступает Sonnet-4.5 на детализации."
        ),
    )
    claude_cli_timeout_seconds: int = Field(default=600, ge=10, le=86400)
    claude_cli_max_retries: int = Field(default=3, ge=1, le=10)
    smodin_api_key: str | None = None
    smodin_humanize_url: str | None = None
    smodin_timeout_seconds: float = Field(default=120.0, ge=5)
    smodin_language: str = Field(
        default="auto",
        description="Язык для Smodin rewrite ('auto' — автоопределение, либо en/ru/...).",
    )
    smodin_strength: int = Field(
        default=3, ge=1, le=4, description="Сила перефразирования Smodin (1..4)."
    )
    turgenev_api_key: str | None = None
    turgenev_analyze_url: str | None = None
    turgenev_autocorrect_url: str | None = None
    turgenev_timeout_seconds: float = Field(default=120.0, ge=5)

    adapter_http_max_retries: int = Field(default=3, ge=1, le=10)
    adapter_dlq_path: str | None = None
    pipeline_soft_fail_adapters: bool = Field(
        default=False,
        description="При падении Smodin/Тургенева после HTTP-retry — не валить пайплайн: пропустить humanize или уйти в manual_review",
    )
    pipeline_disable_smodin: bool = False
    pipeline_disable_turgenev: bool = False
    pipeline_humanize_max_concurrency: int = Field(
        default=4,
        ge=1,
        le=8,
        description="Сколько prose-блоков гуманизировать параллельно за один проход. "
                    "EU gateway держит MAX_CONCURRENCY=8 — оставляем headroom для других job'ов.",
    )
    pipeline_expand_prose_max_concurrency: int = Field(
        default=4,
        ge=1,
        le=8,
        description="Сколько страниц раскрывать в expand_site_prose параллельно. "
                    "Каждая страница = один LLM-вызов на EU-gateway, чисто I/O-bound. "
                    "Отдельная ручка от humanize, чтобы тюнить независимо.",
    )
    pipeline_image_max_concurrency: int = Field(
        default=3,
        ge=1,
        le=8,
        description="Сколько hero-картинок генерить параллельно (OpenAI Images). "
                    "Не уменьшается ниже 1; рейт-лимиты gpt-image-1 ~5 RPM, держим консервативно.",
    )
    smtp_host: str | None = Field(default=None, description="SMTP-сервер провайдера (e.g. smtp.mailgun.org)")
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_user: str | None = Field(default=None, description="Логин SMTP")
    smtp_password: str | None = Field(default=None, description="Пароль SMTP")
    smtp_use_tls: bool = Field(default=True, description="STARTTLS на соединении (по умолчанию true)")
    smtp_from_default: str | None = Field(
        default=None,
        description="From: для писем по умолчанию (e.g. noreply@lead-hunter.ru). "
                    "Per-site можно переопределить через site config forms.from_name+global from address.",
    )
    smtp_timeout_seconds: float = Field(default=15.0, ge=2)
    bulk_wordpress_backup_hook: str | None = None
    bulk_backup_hook_timeout_seconds: int = Field(default=3600, ge=30, le=86400)
    openai_api_key: str | None = None
    openai_base_url: str = Field(default="https://api.openai.com/v1")
    openai_image_timeout_seconds: float = Field(default=180.0, ge=30)
    gemini_api_key: str | None = None
    gemini_api_base: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        description="Gemini API root (AI Studio / Gemini API)",
    )
    gemini_image_timeout_seconds: float = Field(default=180.0, ge=30)
    enable_public_html_cache: bool = Field(
        default=True,
        description="Кешировать готовый HTML публичных custom-страниц в page_render_cache",
    )
    react_renderer_url: str = Field(
        default="http://renderer:8090",
        description=(
            "Base URL of the claudesite-renderer container (Node + Vite + React). "
            "Two endpoints used: POST /build (vite compile per-site src) and "
            "POST /render (SSR a page with props)."
        ),
    )
    react_renderer_build_timeout_seconds: float = Field(default=300.0, ge=30, le=1800)
    react_renderer_render_timeout_seconds: float = Field(default=10.0, ge=1, le=60)

    @property
    def celery_broker(self) -> str:
        return self.celery_broker_url or self.redis_url

    @property
    def celery_backend(self) -> str:
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
