"""Create an account interactively without passwords in process arguments."""

import argparse
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.enums import UserRole
from app.core.errors import AppError
from app.db.session import create_db_engine, create_session_factory
from app.schemas.auth import CreateUserInput
from app.services.auth import create_user


def main() -> int:
    parser = argparse.ArgumentParser(description="Создать пользователя QR Mini-Market")
    parser.add_argument(
        "--username", required=True, help="3–64 символа: буквы латиницы, цифры, _.-"
    )
    parser.add_argument("--role", required=True, choices=[role.value for role in UserRole])
    arguments = parser.parse_args()
    try:
        password = getpass.getpass("Пароль (12–128 символов): ")
        if password != getpass.getpass("Повторите пароль: "):
            print("Пароли не совпадают.", file=sys.stderr)
            return 1
        data = CreateUserInput(username=arguments.username, password=password, role=arguments.role)
        settings = get_settings()
        engine = create_db_engine(settings.database_url)
        try:
            user = create_user(create_session_factory(engine), data)
        finally:
            engine.dispose()
    except (EOFError, KeyboardInterrupt):
        print("\nСоздание пользователя отменено.", file=sys.stderr)
        return 1
    except ValidationError:
        print("Проверьте имя, длину пароля (12–128) и настройки .env.", file=sys.stderr)
        return 1
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "База данных недоступна. Проверьте DATABASE_URL и выполните alembic upgrade head.",
            file=sys.stderr,
        )
        return 1
    print(f"Пользователь {user.username} создан, роль {user.role.value}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
