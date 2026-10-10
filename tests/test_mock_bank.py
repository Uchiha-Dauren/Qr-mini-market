"""Exercise the independent bank through HTTP and durable transaction boundaries."""

import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from mock_bank.config import Settings
from mock_bank.db import utc_now
from mock_bank.errors import BankError
from mock_bank.main import create_app
from mock_bank.models import BankAccount, BankEvent, BankTransaction, Invoice, WebhookDelivery
from mock_bank.schemas import InvoiceCreate
from mock_bank.seed import seed_accounts


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in list(os.environ):
        if name.casefold() in Settings.model_fields:
            monkeypatch.delenv(name)
    return Settings(
        _env_file=None,
        bank_database_url=f"sqlite:///{tmp_path / 'bank.db'}",
        bank_public_url="http://bank.test",
        shop_webhook_url="http://shop.test/webhook",
        bank_merchant_api_key=secrets.token_urlsafe(32),
        webhook_secret=secrets.token_urlsafe(32),
    )


@pytest.fixture
def bank(settings: Settings):
    deliveries = []

    def webhook(request: httpx.Request) -> httpx.Response:
        assert application.state.engine.pool.checkedout() == 0
        deliveries.append(request)
        return httpx.Response(204)

    with httpx.Client(transport=httpx.MockTransport(webhook)) as client:
        application = create_app(settings, webhook_client=client, run_worker=False)
        with TestClient(application) as api:
            seed_accounts(application.state.session_factory)
            yield api, application, deliveries


def auth(settings: Settings) -> dict:
    return {"Authorization": "Bearer " + settings.bank_merchant_api_key.get_secret_value()}


def payload(**changes) -> dict:
    return {
        "merchant_reference": str(uuid4()),
        "amount_minor": 10000,
        "currency": "KZT",
        "description": "Учебная покупка",
        "ttl_seconds": 300,
        **changes,
    }


def create(bank, settings: Settings, **changes) -> dict:
    result = bank[0].post("/api/merchant/invoices", json=payload(**changes), headers=auth(settings))
    assert result.status_code == 200, result.text
    return result.json()


def token(invoice: dict) -> str:
    return invoice["pay_url"].rsplit("/", 1)[1]


def account(bank, *, richest=True) -> BankAccount:
    with bank[1].state.session_factory() as session:
        ordering = BankAccount.balance_minor.desc() if richest else BankAccount.balance_minor
        return session.scalar(select(BankAccount).order_by(ordering).limit(1))


def test_bank_merchant_auth_and_health(bank, settings: Settings) -> None:
    api, app, _ = bank
    assert api.get("/health").json() == {"status": "ok", "database": "ok"}
    for headers in ({}, {"Authorization": "Bearer invalid"}, {"Authorization": "Basic x"}):
        result = api.post("/api/merchant/invoices", json=payload(), headers=headers)
        assert result.status_code == 401
        assert result.json()["error"]["code"] == "UNAUTHORIZED"
    assert api.get(f"/api/merchant/invoices/{uuid4()}", headers=auth(settings)).status_code == 404
    assert not app.state.engine.url.database.endswith("shop.db")


def test_idempotent_create_current_status_and_parameter_conflict(bank, settings: Settings) -> None:
    api, _, _ = bank
    data = payload()
    first = api.post("/api/merchant/invoices", json=data, headers=auth(settings)).json()
    second = api.post("/api/merchant/invoices", json=data, headers=auth(settings)).json()
    assert first["invoice_id"] == second["invoice_id"]
    assert first["expires_at"] == second["expires_at"]
    assert len(token(first)) == 32
    assert UUID(first["invoice_id"]).version == 4
    assert first["event_id"] is None
    conflict = api.post(
        "/api/merchant/invoices", json={**data, "amount_minor": 2}, headers=auth(settings)
    )
    assert conflict.status_code == 409
    cancelled = api.post(
        f"/api/merchant/invoices/{first['invoice_id']}/cancel", headers=auth(settings)
    ).json()
    replay = api.post("/api/merchant/invoices", json=data, headers=auth(settings)).json()
    assert replay["status"] == "CANCELLED"
    assert replay["event_id"] == cancelled["event_id"]


@pytest.mark.parametrize("value", [True, False, 0, -1, "100", 1.5, 2**63])
def test_amounts_require_positive_bounded_integers(bank, settings: Settings, value) -> None:
    assert (
        bank[0]
        .post("/api/merchant/invoices", json=payload(amount_minor=value), headers=auth(settings))
        .status_code
        == 422
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"currency": "USD"},
        {"ttl_seconds": 0},
        {"ttl_seconds": True},
        {"ttl_seconds": 86401},
        {"description": ""},
        {"unexpected": "secret-canary"},
    ],
)
def test_invalid_invoice_fields_are_sanitized(bank, settings: Settings, changes: dict) -> None:
    result = bank[0].post("/api/merchant/invoices", json=payload(**changes), headers=auth(settings))
    assert result.status_code == 422
    assert "secret-canary" not in result.text


def test_payment_once_signed_webhook_and_transaction(bank, settings: Settings) -> None:
    api, app, deliveries = bank
    invoice = create(bank, settings)
    selected = account(bank)
    result = api.post(f"/api/pay/{token(invoice)}", json={"account_id": str(selected.id)})
    assert result.status_code == 200
    paid = result.json()
    assert paid["status"] == "PAID"
    assert paid["event_id"] and paid["paid_at"]
    assert (
        api.post(f"/api/pay/{token(invoice)}", json={"account_id": str(selected.id)}).status_code
        == 409
    )
    assert (
        api.post(
            f"/api/merchant/invoices/{invoice['invoice_id']}/cancel", headers=auth(settings)
        ).status_code
        == 409
    )
    assert len(deliveries) == 1
    request = deliveries[0]
    expected = hmac.new(
        settings.webhook_secret.get_secret_value().encode(),
        request.headers["X-Timestamp"].encode() + b"." + request.content,
        hashlib.sha256,
    ).hexdigest()
    assert request.headers["X-Signature"] == expected
    event = json.loads(request.content)
    assert event["event_id"] == paid["event_id"]
    assert event["type"] == "invoice.paid"
    assert event["data"]["merchant_reference"] == invoice["merchant_reference"]
    with app.state.session_factory() as session:
        assert (
            session.get(BankAccount, selected.id).balance_minor
            == selected.balance_minor - invoice["amount_minor"]
        )
        assert session.scalar(select(func.count()).select_from(BankTransaction)) == 1
        assert session.scalar(select(func.count()).select_from(BankEvent)) == 1
        assert session.scalar(select(WebhookDelivery)).response_status == 204


def test_insufficient_funds_preserves_balance_and_emits_failure(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    selected = account(bank, richest=False)
    result = bank[0].post(f"/api/pay/{token(invoice)}", json={"account_id": str(selected.id)})
    assert result.status_code == 200
    assert result.json()["status"] == "FAILED"
    assert result.json()["failure_reason"] == "insufficient_funds"
    with bank[1].state.session_factory() as session:
        assert session.get(BankAccount, selected.id).balance_minor == 0
        assert session.scalar(select(BankTransaction)).status == "FAILED"
    assert json.loads(bank[2][0].content)["type"] == "invoice.failed"


def test_expired_payment_commits_event_before_410(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    with bank[1].state.session_factory.begin() as session:
        session.execute(update(Invoice).values(expires_at=utc_now() - timedelta(seconds=1)))
    result = bank[0].post(f"/api/pay/{token(invoice)}", json={"account_id": str(account(bank).id)})
    assert result.status_code == 410
    with bank[1].state.session_factory() as session:
        assert session.scalar(select(Invoice)).status == "EXPIRED"
        assert session.scalar(select(BankEvent)).event_type == "invoice.expired"
        assert session.scalar(select(func.count()).select_from(BankTransaction)) == 0
    bank[1].state.notifier.deliver_due()
    assert len(bank[2]) == 1


def test_sweep_expiry_is_idempotent(bank, settings: Settings) -> None:
    create(bank, settings)
    with bank[1].state.session_factory.begin() as session:
        session.execute(update(Invoice).values(expires_at=utc_now() - timedelta(seconds=1)))
    assert bank[1].state.service.sweep_expired() == 1
    assert bank[1].state.service.sweep_expired() == 0
    bank[1].state.notifier.deliver_due()
    assert json.loads(bank[2][0].content)["type"] == "invoice.expired"


def test_unknown_account_leaves_invoice_created(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    assert (
        bank[0].post(f"/api/pay/{token(invoice)}", json={"account_id": str(uuid4())}).status_code
        == 404
    )
    assert bank[0].get(f"/api/pay/{token(invoice)}").json()["status"] == "CREATED"


def test_customer_page_accounts_cancel_and_decline(bank, settings: Settings) -> None:
    invoice = create(bank, settings, description="<script>alert(1)</script>")
    page = bank[0].get(f"/pay/{token(invoice)}")
    assert page.status_code == 200
    assert "Учебный эмулятор банка" in page.text
    assert "&lt;script&gt;" in page.text and "<script>alert" not in page.text
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert bank[0].get("/static/bank.js").status_code == 200
    choices = bank[0].get(f"/api/pay/{token(invoice)}").json()["accounts"]
    assert len(choices) == 3
    assert all(
        set(choice) == {"public_id", "holder_name", "balance_minor", "balance_minor_text"}
        for choice in choices
    )
    assert bank[0].post(f"/api/pay/{token(invoice)}/cancel").json()["status"] == "CANCELLED"
    other = create(bank, settings)
    declined = bank[0].post(f"/api/pay/{token(other)}/decline").json()
    assert declined["status"] == "FAILED" and declined["failure_reason"] == "bank_declined"


def test_seed_never_restores_spent_balances(bank, settings: Settings) -> None:
    selected = account(bank)
    invoice = create(bank, settings)
    bank[1].state.service.pay(token(invoice), selected.id)
    seeded = seed_accounts(bank[1].state.session_factory)
    assert len(seeded) == 3
    assert (
        next(item for item in seeded if item["public_id"] == str(selected.id))["balance_minor"]
        == selected.balance_minor - 10000
    )


def test_negative_and_fractional_balance_rejected(bank) -> None:
    for value in (-1, "1.5"):
        with pytest.raises(IntegrityError), bank[1].state.session_factory.begin() as session:
            session.execute(
                text("UPDATE bank_accounts SET balance_minor = :value"), {"value": value}
            )


def test_concurrent_payment_debits_once(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    selected = account(bank)

    def pay():
        try:
            return bank[1].state.service.pay(token(invoice), selected.id)["status"]
        except BankError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: pay(), range(2)))
    assert sorted(map(str, results)) == ["409", "PAID"]
    with bank[1].state.session_factory() as session:
        assert session.get(BankAccount, selected.id).balance_minor == selected.balance_minor - 10000


def test_two_invoices_compete_for_last_balance(bank, settings: Settings) -> None:
    invoices = [create(bank, settings, amount_minor=60000) for _ in range(2)]
    with bank[1].state.session_factory() as session:
        selected = session.scalar(select(BankAccount).where(BankAccount.seed_key == "poor"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda invoice: bank[1].state.service.pay(token(invoice), selected.id)["status"],
                invoices,
            )
        )
    assert sorted(results) == ["FAILED", "PAID"]
    with bank[1].state.session_factory() as session:
        assert session.get(BankAccount, selected.id).balance_minor == 40000


def test_invoice_event_and_balance_roll_back_together(
    bank, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    invoice = create(bank, settings)
    selected = account(bank)
    original = bank[1].state.service._finalize

    def broken(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("Injected rollback")

    monkeypatch.setattr(bank[1].state.service, "_finalize", broken)
    with pytest.raises(RuntimeError, match="Injected rollback"):
        bank[1].state.service.pay(token(invoice), selected.id)
    with bank[1].state.session_factory() as session:
        assert session.get(BankAccount, selected.id).balance_minor == selected.balance_minor
        assert session.scalar(select(Invoice)).status == "CREATED"
        assert session.scalar(select(func.count()).select_from(BankEvent)) == 0
        assert session.scalar(select(func.count()).select_from(BankTransaction)) == 0


@pytest.mark.parametrize("response_status", [400, 401, 422, 302])
def test_permanent_webhook_response_stops_retries(settings: Settings, response_status: int) -> None:
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(response_status))
    ) as client:
        app = create_app(settings, webhook_client=client, run_worker=False)
        with TestClient(app):
            invoice = app.state.service.create_invoice(InvoiceCreate(**payload()))
            app.state.service.cancel(UUID(invoice["invoice_id"]))
            assert app.state.notifier.deliver_due() == 1
            assert app.state.notifier.deliver_due() == 0
            with app.state.session_factory() as session:
                event = session.scalar(select(BankEvent))
                assert event.stopped and not event.delivered and event.attempts == 1


def test_webhook_retries_survive_restart_and_keep_body(settings: Settings) -> None:
    requests = []

    def flaky(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError("not stored secret", request=request)
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(flaky)) as client:
        first = create_app(settings, webhook_client=client, run_worker=False)
        with TestClient(first):
            invoice = first.state.service.create_invoice(InvoiceCreate(**payload()))
            first.state.service.cancel(UUID(invoice["invoice_id"]))
            assert first.state.notifier.deliver_due() == 1
        second = create_app(settings, webhook_client=client, run_worker=False)
        with TestClient(second):
            for expected_attempt, delay in [(2, 5), (3, 25), (4, 25)]:
                with second.state.session_factory.begin() as session:
                    session.execute(
                        update(BankEvent).values(next_attempt_at=utc_now() - timedelta(seconds=1))
                    )
                before = utc_now()
                assert second.state.notifier.deliver_due() == 1
                with second.state.session_factory() as session:
                    event = session.scalar(select(BankEvent))
                    assert event.attempts == expected_attempt
                    assert event.next_attempt_at >= before + timedelta(seconds=delay)
            with second.state.session_factory() as session:
                event = session.scalar(select(BankEvent))
                assert event.stopped and not event.delivered
                assert session.scalar(select(func.count()).select_from(WebhookDelivery)) == 4
                assert (
                    session.scalar(
                        select(WebhookDelivery).where(WebhookDelivery.attempt == 1)
                    ).error_kind
                    == "ConnectError"
                )
            assert second.state.notifier.deliver_due() == 0
    assert len({request.content for request in requests}) == 1


def test_unexpected_error_does_not_expose_input_or_log_message(bank, caplog) -> None:
    @bank[1].get("/_test/failure")
    def failure():
        raise RuntimeError("secret-canary")

    result = bank[0].get("/_test/failure")
    assert result.status_code == 500
    assert result.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret-canary" not in result.text + caplog.text


def test_concurrent_idempotent_creation_returns_one_invoice(bank) -> None:
    request = InvoiceCreate(**payload())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: bank[1].state.service.create_invoice(request), range(2)))
    assert results[0]["invoice_id"] == results[1]["invoice_id"]
    with bank[1].state.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Invoice)) == 1


def test_payment_and_cancel_race_has_one_final_event(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    selected = account(bank)

    def transition(pay: bool):
        try:
            if pay:
                return bank[1].state.service.pay(token(invoice), selected.id)
            return bank[1].state.service.cancel(UUID(invoice["invoice_id"]))
        except BankError as exc:
            return exc.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(transition, [True, False]))
    with bank[1].state.session_factory() as session:
        final = session.scalar(select(Invoice))
        assert final.status in ("PAID", "CANCELLED")
        debit = invoice["amount_minor"] if final.status == "PAID" else 0
        assert session.get(BankAccount, selected.id).balance_minor == selected.balance_minor - debit
        assert session.scalar(select(func.count()).select_from(BankEvent)) == 1


def test_abandoned_delivery_lease_recovers_and_keeps_event_id(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    final = bank[1].state.service.cancel(UUID(invoice["invoice_id"]))
    abandoned = bank[1].state.notifier._claim()
    assert abandoned is not None
    assert bank[1].state.notifier.deliver_due() == 0
    with bank[1].state.session_factory.begin() as session:
        session.execute(update(BankEvent).values(lease_until=utc_now() - timedelta(seconds=1)))
    assert bank[1].state.notifier.deliver_due() == 1
    assert json.loads(bank[2][0].content)["event_id"] == final["event_id"]
    with bank[1].state.session_factory() as session:
        assert session.scalar(select(BankEvent)).delivered
        attempts = session.scalars(select(WebhookDelivery).order_by(WebhookDelivery.attempt)).all()
        assert len(attempts) == 2
        assert attempts[0].completed_at is None
        assert attempts[1].response_status == 204


def test_concurrent_notifiers_claim_one_delivery(bank, settings: Settings) -> None:
    invoice = create(bank, settings)
    bank[1].state.service.cancel(UUID(invoice["invoice_id"]))
    # Test the claim boundary: one worker owns the event before any HTTP begins.
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: bank[1].state.notifier._claim(), range(2)))
    assert sum(claim is not None for claim in claims) == 1


def test_int64_money_has_exact_decimal_text_for_browser(bank, settings: Settings) -> None:
    maximum = 2**63 - 1
    invoice = create(bank, settings, amount_minor=maximum)
    assert invoice["amount_minor_text"] == str(maximum)
    selected = account(bank)
    with bank[1].state.session_factory.begin() as session:
        session.execute(
            update(BankAccount).where(BankAccount.id == selected.id).values(balance_minor=maximum)
        )
    data = bank[0].get(f"/api/pay/{token(invoice)}").json()
    chosen = next(item for item in data["accounts"] if item["public_id"] == str(selected.id))
    assert chosen["balance_minor_text"] == str(maximum)
    paid = bank[0].post(f"/api/pay/{token(invoice)}", json={"account_id": str(selected.id)}).json()
    assert paid["status"] == "PAID" and paid["amount_minor_text"] == str(maximum)
    with bank[1].state.session_factory() as session:
        assert session.get(BankAccount, selected.id).balance_minor == 0


def test_browser_money_formatter_keeps_final_minor_units() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required only for the browser formatter check")
    source = Path(__file__).resolve().parents[1] / "mock_bank" / "static" / "money.js"
    script = (
        source.read_text()
        + """
for (const value of ['0', '10001', '9007199254740991', '9223372036854775807']) {
  console.log(formatBankMoney(value).replace(/\\s/g, ''));
}
"""
    )
    result = subprocess.run([node, "-e", script], check=True, text=True, capture_output=True)
    assert result.stdout.splitlines() == [
        "0,00₸",
        "100,01₸",
        "90071992547409,91₸",
        "92233720368547758,07₸",
    ]
