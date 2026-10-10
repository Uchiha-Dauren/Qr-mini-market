"""Create a local configuration once with independent, generated secrets."""

import os
import secrets
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRET_NAMES = ("BANK_MERCHANT_API_KEY", "WEBHOOK_SECRET", "SECRET_KEY")


def create_env(destination: Path, template: Path) -> bool:
    """Never replace an existing configuration or print its generated values."""
    content = template.read_text(encoding="utf-8")
    for name in SECRET_NAMES:
        content = content.replace(f"{name}=\n", f"{name}={secrets.token_urlsafe(48)}\n")
    try:
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as target:
        target.write(content)
    return True


def main() -> None:
    created = create_env(PROJECT_ROOT / ".env", PROJECT_ROOT / ".env.example")
    print("Настройки .env созданы." if created else "Файл .env уже существует и сохранён.")


if __name__ == "__main__":
    main()
