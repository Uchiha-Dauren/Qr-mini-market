"""Durable outbox with HTTP outside transactions and stable signed payloads."""

import hashlib
import hmac
from datetime import timedelta
from uuid import uuid4

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.config import Settings
from mock_bank.db import run_write, utc_now
from mock_bank.models import BankEvent, WebhookDelivery

RETRY_DELAYS = (1, 5, 25)


class WebhookNotifier:
    def __init__(
        self, factory: sessionmaker[Session], settings: Settings, client: httpx.Client
    ) -> None:
        self.factory = factory
        self.settings = settings
        self.client = client

    def _claim(self) -> dict | None:
        def operation(session: Session) -> dict | None:
            now = utc_now()
            due = (
                BankEvent.delivered.is_(False),
                BankEvent.stopped.is_(False),
                BankEvent.next_attempt_at <= now,
                or_(BankEvent.lease_until.is_(None), BankEvent.lease_until <= now),
            )
            event = session.scalar(
                select(BankEvent)
                .where(*due)
                .order_by(BankEvent.next_attempt_at, BankEvent.id)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if event is None:
                return None
            lease = uuid4()
            if (
                session.execute(
                    update(BankEvent)
                    .where(BankEvent.id == event.id, *due)
                    .values(
                        lease_token=lease,
                        lease_until=now + timedelta(seconds=30),
                        attempts=BankEvent.attempts + 1,
                    )
                ).rowcount
                != 1
            ):
                return None
            delivery = WebhookDelivery(event_id=event.id, attempt=event.attempts, requested_at=now)
            session.add(delivery)
            session.flush()
            return {
                "event_id": event.id,
                "lease": lease,
                "body": event.raw_body.encode(),
                "attempt": event.attempts,
                "delivery_id": delivery.id,
            }

        return run_write(self.factory, operation)

    def _finish(self, claim: dict, status: int | None, error_kind: str | None) -> None:
        def operation(session: Session) -> None:
            now = utc_now()
            delivery = session.get(WebhookDelivery, claim["delivery_id"])
            delivery.completed_at = now
            delivery.response_status = status
            delivery.error_kind = error_kind
            success = status is not None and 200 <= status < 300
            retryable = status is None or status >= 500
            exhausted = claim["attempt"] > len(RETRY_DELAYS)
            delay = RETRY_DELAYS[min(claim["attempt"] - 1, len(RETRY_DELAYS) - 1)]
            session.execute(
                update(BankEvent)
                .where(
                    BankEvent.id == claim["event_id"],
                    BankEvent.lease_token == claim["lease"],
                )
                .values(
                    delivered=success,
                    stopped=not success and (not retryable or exhausted),
                    lease_token=None,
                    lease_until=None,
                    next_attempt_at=now + timedelta(seconds=delay),
                )
            )

        run_write(self.factory, operation)

    def deliver_due(self, limit: int = 20) -> int:
        """Send immediate attempts; persisted due times replace sleeping retry tasks."""
        delivered = 0
        for _ in range(limit):
            claim = self._claim()
            if claim is None:
                break
            timestamp = str(int(utc_now().timestamp()))
            signature = hmac.new(
                self.settings.webhook_secret.get_secret_value().encode(),
                timestamp.encode() + b"." + claim["body"],
                hashlib.sha256,
            ).hexdigest()
            status = None
            error_kind = None
            try:
                result = self.client.post(
                    str(self.settings.shop_webhook_url),
                    content=claim["body"],
                    headers={
                        "Content-Type": "application/json",
                        "X-Timestamp": timestamp,
                        "X-Signature": signature,
                    },
                    timeout=5,
                    follow_redirects=False,
                )
                status = result.status_code
            except httpx.HTTPError as exc:
                error_kind = type(exc).__name__
            self._finish(claim, status, error_kind)
            delivered += 1
        return delivered
