"""Application factory and lifecycle-owned resources."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings, get_settings
from app.core.errors import HTTP_ERRORS, install_error_handlers
from app.db.session import create_db_engine, create_session_factory
from app.dependencies import ping_database
from app.providers.base import PaymentProvider
from app.providers.mock_bank import MockBankProvider
from app.routers import auth, catalog, health, orders, pages, payments, reports
from app.schemas.common import ErrorResponse
from app.services.payments import PaymentService

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    provider: PaymentProvider | None = None,
    run_worker: bool = True,
) -> FastAPI:
    """Build an application without reading settings or opening a database yet."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active_settings = settings if settings is not None else get_settings()
        engine = create_db_engine(active_settings.database_url)
        client = None
        worker = None
        stop = asyncio.Event()
        try:
            factory = create_session_factory(engine)
            application.state.settings = active_settings
            application.state.engine = engine
            application.state.session_factory = factory
            await asyncio.to_thread(ping_database, engine)
            active_provider = provider
            if active_provider is None:
                client = httpx.Client(trust_env=False)
                active_provider = MockBankProvider(client, active_settings)
            application.state.provider = active_provider
            service = PaymentService(factory, active_provider, active_settings)

            async def reconcile() -> None:
                while not stop.is_set():
                    try:
                        await asyncio.to_thread(service.sweep)
                    except Exception as exc:
                        logger.error("Payment reconciliation failed (%s)", type(exc).__name__)
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=15)
                    except TimeoutError:
                        pass

            if run_worker:
                worker = asyncio.create_task(reconcile())
            yield
        finally:
            stop.set()
            if worker is not None:
                await worker
            if client is not None:
                await asyncio.to_thread(client.close)
            await asyncio.to_thread(engine.dispose)
            for name in ("provider", "session_factory", "engine", "settings"):
                if hasattr(application.state, name):
                    delattr(application.state, name)

    application = FastAPI(
        title="QR Mini-Market",
        debug=False,
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        responses={status: {"model": ErrorResponse} for status in HTTP_ERRORS},
    )
    install_error_handlers(application)
    application.mount(
        "/static", StaticFiles(directory=Path(__file__).resolve().parent / "static"), name="static"
    )
    for router in (health, auth, catalog, orders, payments, reports, pages):
        application.include_router(router.router)
    return application


app = create_app()
