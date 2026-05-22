class OrchestratorError(Exception):
    """Базовая ошибка приложения."""


class UnknownSiteError(OrchestratorError):
    def __init__(self, slug: str) -> None:
        super().__init__(f"No site registered in DB with slug={slug!r}")
        self.slug = slug


class SiteConfigNotFoundError(OrchestratorError):
    def __init__(self, path: str) -> None:
        super().__init__(f"Site config file not found: {path}")
        self.path = path


class SiteConfigValidationError(OrchestratorError):
    """Некорректный YAML или ошибка валидации pydantic."""


class DuplicateKeywordError(OrchestratorError):
    def __init__(self, site_id: int, keyword_hash: str) -> None:
        super().__init__(f"Keyword already processed for site_id={site_id} hash={keyword_hash!r}")
        self.site_id = site_id
        self.keyword_hash = keyword_hash


class SlugTakenError(OrchestratorError):
    def __init__(self, slug: str) -> None:
        super().__init__(f"Page slug already exists: {slug!r}")
        self.slug = slug


class PageNotFoundError(OrchestratorError):
    def __init__(self, page_id: int) -> None:
        super().__init__(f"No page with id={page_id}")
        self.page_id = page_id


class WrongSiteModeError(OrchestratorError):
    def __init__(self, slug: str, expected: str, actual: str) -> None:
        super().__init__(
            f"Site {slug!r} mode is {actual!r}, expected {expected!r} for this operation",
        )
        self.slug = slug
        self.expected = expected
        self.actual = actual


class PageHasNoRevisionError(OrchestratorError):
    def __init__(self, page_id: int) -> None:
        super().__init__(f"Page id={page_id} has no revisions (nothing to publish)")
        self.page_id = page_id


class ManualReviewNotFoundError(OrchestratorError):
    def __init__(self, queue_id: int) -> None:
        super().__init__(f"No manual review queue row id={queue_id}")
        self.queue_id = queue_id


class ManualReviewBadStateError(OrchestratorError):
    def __init__(self, queue_id: int, status: str) -> None:
        super().__init__(f"Manual review id={queue_id} is not pending (status={status!r})")
        self.queue_id = queue_id
        self.status = status


class PageRevisionNotFoundError(OrchestratorError):
    def __init__(self, page_id: int, revision_no: int) -> None:
        super().__init__(f"No revision page_id={page_id} revision_no={revision_no}")
        self.page_id = page_id
        self.revision_no = revision_no


class RollbackNotPossibleError(OrchestratorError):
    """Недостаточно истории ревизий для отката."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
