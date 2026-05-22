from enum import StrEnum


class SiteMode(StrEnum):
    WORDPRESS = "wordpress"
    CUSTOM = "custom"


class PageStatus(StrEnum):
    DRAFT = "draft"
    GENERATING = "generating"
    PUBLISHED = "published"
    MANUAL_REVIEW = "manual_review"
    FAILED = "failed"


class JobRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"
    MANUAL_REVIEW = "manual_review"


class ManualReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class JobTaskType(StrEnum):
    CREATE_PAGE = "create_page"
    UPDATE_PAGE = "update_page"
    ROLLBACK_PAGE = "rollback_page"
    BULK_SEMANTICS = "bulk_semantics"
    GENERATE_SITE = "generate_site"
    ADD_PAGE = "add_page"
    ADD_PAGE_TYPE = "add_page_type"
    DESIGN_EDIT = "design_edit"
    WP_DO = "wp_do"
    WP_PUBLISH_ARTICLE = "wp_publish_article"
