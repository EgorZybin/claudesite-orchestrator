from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.middleware.site_host_resolver import SiteHostResolverMiddleware
from app.api.routes import (
    form_submissions,
    health,
    jobs,
    metrics,
    public,
    site_edit,
    sites,
    static_files,
    uploads,
    wp,
)
from app.core.config import get_settings
from app.core.logging import configure_logging

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(SiteHostResolverMiddleware)
app.include_router(health.router)
app.include_router(metrics.router)
app.include_router(public.router)
app.include_router(site_edit.router)
app.include_router(jobs.router)
app.include_router(sites.router)
app.include_router(sites.pages_router)
app.include_router(wp.router)
app.include_router(uploads.router)
app.include_router(static_files.router)
app.include_router(form_submissions.public_router)
app.include_router(form_submissions.admin_router)
