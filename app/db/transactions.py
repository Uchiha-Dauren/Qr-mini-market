"""Retry complete local write transactions; never run network calls inside them."""

import logging
import time
from collections.abc import Callable
from typing import TypeVar

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError

T = TypeVar("T")
logger = logging.getLogger(__name__)


def run_write(factory: sessionmaker[Session], operation: Callable[[Session], T]) -> T:
    """Commit a fresh session, with serialized SQLite writers and bounded retries."""
    for attempt in range(4):
        try:
            with factory.begin() as session:
                if session.get_bind().dialect.name == "sqlite":
                    session.connection(execution_options={"write_transaction": True})
                return operation(session)
        except OperationalError as exc:
            sqlite_code = getattr(exc.orig, "sqlite_errorcode", 0)
            sqlstate = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
            retryable = (sqlite_code & 255) in (5, 6) or sqlstate in ("40001", "40P01")
            if not retryable:
                raise
            if attempt == 3:
                raise AppError(
                    409, "CONCURRENT_UPDATE", "Данные изменяются. Повторите операцию."
                ) from None
            logger.info("Retrying local database transaction, attempt %s", attempt + 2)
            time.sleep(0.01 * 2**attempt)
    raise AssertionError("Unreachable transaction retry state")
