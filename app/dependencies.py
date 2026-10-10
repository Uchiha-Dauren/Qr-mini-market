"""Request-scoped sessions and the database readiness probe."""

import logging
from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.errors import AppError

logger = logging.getLogger(__name__)


def get_session(request: Request) -> Iterator[Session]:
    """Close the request session without implicitly committing pending changes."""
    factory: sessionmaker[Session] = request.app.state.session_factory
    with factory() as session:
        yield session


def ping_database(engine: Engine) -> None:
    """Check connectivity without requiring or creating business tables."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.warning("Database readiness probe failed (%s)", type(exc).__name__)
        raise AppError(503, "DATABASE_UNAVAILABLE", "База данных временно недоступна.") from None


def require_database(request: Request) -> None:
    """Resolve the current application's engine for the health endpoint."""
    ping_database(request.app.state.engine)
