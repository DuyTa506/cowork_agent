"""Application factory: wires configuration, schema, routers and error handling together."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agent.runtime import AgentPool
from app.api import admin, auth, chat, documents, formatcheck, spellcheck, stats, system
from app.core import config
from app.core.database import SessionLocal, engine
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.migrate import ensure_schema
from app.services import users

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start-up: make sure the schema exists and there is an administrator to sign in with."""
    configure_logging()
    ensure_schema(engine)
    with SessionLocal() as db:
        if users.ensure_admin(db):
            log.warning("Created the bootstrap administrator '%s'; change its password after the first sign-in.", config.ADMIN_USERNAME)
    app.state.agent_pool = AgentPool()
    app.state.session_factory = SessionLocal
    yield
    app.state.agent_pool.close_all()


def create_app() -> FastAPI:
    """Builds the FastAPI application."""
    app = FastAPI(title=config.APP_NAME, version=config.APP_VERSION, docs_url="/api/docs", redoc_url="/api/redoc",
                  openapi_url="/api/openapi.json", lifespan=lifespan)
    if config.CORS_ORIGINS:
        app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=False, allow_methods=["*"],
                           allow_headers=["*"])
    install_error_handlers(app)
    for module in (system, auth, documents, formatcheck, spellcheck, chat, admin, stats):
        app.include_router(module.router)
    return app


app = create_app()
