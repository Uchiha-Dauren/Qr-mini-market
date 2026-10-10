"""Create three demo accounts once; never reset their balances."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from mock_bank.config import get_settings
from mock_bank.db import Base, create_db_engine, create_session_factory, run_write
from mock_bank.models import BankAccount

DEMO_ACCOUNTS = (
    ("rich", "Айдос", 50_000_000),
    ("poor", "Алия", 100_000),
    ("empty", "Дана", 0),
)


def seed_accounts(factory: sessionmaker[Session]) -> list[dict]:
    def operation(session: Session) -> list[dict]:
        for seed_key, holder, balance in DEMO_ACCOUNTS:
            if (
                session.scalar(select(BankAccount.id).where(BankAccount.seed_key == seed_key))
                is None
            ):
                session.add(
                    BankAccount(seed_key=seed_key, holder_name=holder, balance_minor=balance)
                )
        session.flush()
        return [
            {
                "public_id": str(account.id),
                "holder_name": account.holder_name,
                "balance_minor": account.balance_minor,
            }
            for account in session.scalars(select(BankAccount).order_by(BankAccount.holder_name))
        ]

    try:
        return run_write(factory, operation)
    except IntegrityError:
        return run_write(factory, operation)


def main() -> None:
    engine = create_db_engine(get_settings().bank_database_url)
    try:
        Base.metadata.create_all(engine)
        accounts = seed_accounts(create_session_factory(engine))
        print(f"Демо-счета готовы: {len(accounts)}. Существующие балансы сохранены.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
