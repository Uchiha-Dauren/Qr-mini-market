"""Bootstrap configuration must preserve previous values and generate distinct keys."""

from pathlib import Path

from app.core.config import Settings
from app.setup_env import PROJECT_ROOT, SECRET_NAMES, create_env


def test_create_and_preserve_configuration(tmp_path: Path) -> None:
    target = tmp_path / ".env"
    assert create_env(target, PROJECT_ROOT / ".env.example")
    original = target.read_text(encoding="utf-8")
    values = dict(
        line.split("=", 1)
        for line in original.splitlines()
        if "=" in line and not line.startswith("#")
    )
    assert len({values[name] for name in SECRET_NAMES}) == 3
    settings = Settings(_env_file=target)
    assert settings.currency == "KZT"
    assert not create_env(target, PROJECT_ROOT / ".env.example")
    assert target.read_text(encoding="utf-8") == original
