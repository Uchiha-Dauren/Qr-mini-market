"""Standalone bank application, independent of every shop module."""

import asyncio
import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from mock_bank.config import Settings, get_settings
from mock_bank.db import Base, create_db_engine, create_session_factory
from mock_bank.errors import BankError, install_errors
from mock_bank.notifier import WebhookNotifier
from mock_bank.schemas import InvoiceCreate, PayRequest
from mock_bank.service import BankService

ROOT = Path(__file__).resolve().parent
logger = logging.getLogger(__name__)


def require_merchant(request: Request) -> None:
    supplied = request.headers.get("Authorization", "")
    expected = "Bearer " + request.app.state.settings.bank_merchant_api_key.get_secret_value()
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise BankError(401, "UNAUTHORIZED", "Неверный ключ магазина.")


def create_app(
    settings: Settings | None = None,
    webhook_client: httpx.Client | None = None,
    run_worker: bool = True,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active = settings if settings is not None else get_settings()
        engine = create_db_engine(active.bank_database_url)
        client = webhook_client if webhook_client is not None else httpx.Client(trust_env=False)
        stop = asyncio.Event()
        worker = None
        try:
            await asyncio.to_thread(Base.metadata.create_all, engine)
            factory = create_session_factory(engine)
            service = BankService(factory, active)
            notifier = WebhookNotifier(factory, active, client)
            application.state.settings = active
            application.state.engine = engine
            application.state.session_factory = factory
            application.state.service = service
            application.state.notifier = notifier

            async def work() -> None:
                while not stop.is_set():
                    try:
                        await asyncio.to_thread(service.sweep_expired)
                        await asyncio.to_thread(notifier.deliver_due)
                    except Exception as exc:
                        logger.error("Bank worker failed (%s)", type(exc).__name__)
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=1)
                    except TimeoutError:
                        pass

            if run_worker:
                worker = asyncio.create_task(work())
            yield
        finally:
            stop.set()
            if worker is not None:
                await worker
            if webhook_client is None:
                await asyncio.to_thread(client.close)
            await asyncio.to_thread(engine.dispose)

    application = FastAPI(
        title="Учебный Mock Bank", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    install_errors(application)
    application.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    templates = Jinja2Templates(directory=ROOT / "templates")

    def schedule(request: Request, tasks: BackgroundTasks) -> BankService:
        tasks.add_task(request.app.state.notifier.deliver_due)
        return request.app.state.service

    @application.get("/health")
    def health(request: Request) -> dict:
        try:
            with request.app.state.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise BankError(503, "DATABASE_UNAVAILABLE", "База данных банка недоступна.") from None
        return {"status": "ok", "database": "ok"}

    @application.post("/api/merchant/invoices", dependencies=[Depends(require_merchant)])
    def create_invoice(payload: InvoiceCreate, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).create_invoice(payload)

    @application.get(
        "/api/merchant/invoices/{invoice_id}", dependencies=[Depends(require_merchant)]
    )
    def get_invoice(invoice_id: UUID, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).get_invoice(invoice_id)

    @application.post(
        "/api/merchant/invoices/{invoice_id}/cancel", dependencies=[Depends(require_merchant)]
    )
    def cancel_invoice(invoice_id: UUID, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).cancel(invoice_id)

    @application.get("/pay/{token}")
    def page(token: str, request: Request, tasks: BackgroundTasks):
        invoice = schedule(request, tasks).get_invoice(token)
        return templates.TemplateResponse(
            request=request,
            name="pay.html",
            context={"token": token, "invoice": invoice},
            background=tasks,
        )

    @application.get("/api/pay/{token}")
    def customer_invoice(token: str, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).get_invoice(token, accounts=True)

    @application.post("/api/pay/{token}")
    def pay(token: str, payload: PayRequest, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).pay(token, payload.account_id)

    @application.post("/api/pay/{token}/cancel")
    def cancel(token: str, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).cancel(token)

    @application.post("/api/pay/{token}/decline")
    def decline(token: str, request: Request, tasks: BackgroundTasks) -> dict:
        return schedule(request, tasks).decline(token)

    return application


app = create_app()
