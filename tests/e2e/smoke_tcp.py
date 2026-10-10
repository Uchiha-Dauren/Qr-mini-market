"""Optional real-process smoke; run: python tests/e2e/smoke_tcp.py.

Run this file directly from the repository using the project's Python environment.
It creates temporary databases and generated credentials, then cleans up both servers.
"""

import os
import secrets
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for(client: httpx.Client, url: str, expected, timeout: int = 20) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = client.get(url)
            if response.status_code == 200 and expected(response.json()):
                return response.json()
        except httpx.HTTPError:
            pass
        time.sleep(0.1)
    raise AssertionError(f"Timed out waiting for {url}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="qr-market-smoke-") as directory:
        temporary = Path(directory)
        shop_port = free_port()
        bank_port = free_port()
        while bank_port == shop_port:
            bank_port = free_port()
        shop_url = f"http://127.0.0.1:{shop_port}"
        bank_url = f"http://127.0.0.1:{bank_port}"
        password = secrets.token_urlsafe(24)
        environment = {
            **os.environ,
            "APP_ENV": "test",
            "DATABASE_URL": f"sqlite:///{temporary / 'shop.db'}",
            "BANK_DATABASE_URL": f"sqlite:///{temporary / 'bank.db'}",
            "BANK_BASE_URL": bank_url,
            "BANK_PUBLIC_URL": bank_url,
            "SHOP_WEBHOOK_URL": shop_url + "/api/v1/webhooks/mock-bank",
            "BANK_MERCHANT_API_KEY": secrets.token_urlsafe(32),
            "WEBHOOK_SECRET": secrets.token_urlsafe(32),
            "SECRET_KEY": secrets.token_urlsafe(32),
            "PAYMENT_TTL_SECONDS": "5",
            "PAYMENT_EXPIRY_GRACE_SECONDS": "0",
            "SMOKE_ADMIN_PASSWORD": password,
        }

        def run(*arguments: str) -> None:
            result = subprocess.run(
                [sys.executable, *arguments],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr

        run("-m", "alembic", "upgrade", "head")
        run("-m", "app.seed")
        run("-m", "app.seed")
        run("-m", "mock_bank.seed")
        run("-m", "mock_bank.seed")
        run(
            "-c",
            "import os; from app.core.config import get_settings; "
            "from app.db.session import create_db_engine, create_session_factory; "
            "from app.schemas.auth import CreateUserInput; "
            "from app.services.auth import create_user; "
            "engine=create_db_engine(get_settings().database_url); "
            "create_user(create_session_factory(engine), CreateUserInput("
            "username='smoke-admin', password=os.environ['SMOKE_ADMIN_PASSWORD'], role='ADMIN')); "
            "engine.dispose()",
        )
        print("Migration, idempotent seeds, and generated admin: OK")
        processes = []
        logs = []
        shutdown_logs = []
        try:
            for module, port in (("mock_bank.main:app", bank_port), ("app.main:app", shop_port)):
                log = (temporary / f"{port}.log").open("w+")
                logs.append(log)
                processes.append(
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "uvicorn",
                            module,
                            "--host",
                            "127.0.0.1",
                            "--port",
                            str(port),
                            "--no-access-log",
                        ],
                        cwd=ROOT,
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )
                )
            with httpx.Client(trust_env=False, timeout=15) as client:
                wait_for(client, shop_url + "/health", lambda data: data["status"] == "ok")
                wait_for(client, bank_url + "/health", lambda data: data["status"] == "ok")
                login = client.post(
                    shop_url + "/api/v1/auth/login",
                    json={
                        "username": "smoke-admin",
                        "password": password,
                    },
                )
                assert login.status_code == 200, login.text
                headers = {"Authorization": "Bearer " + login.json()["access_token"]}
                client.cookies.clear()

                def api(method: str, path: str, **kwargs) -> dict:
                    response = client.request(
                        method, shop_url + "/api/v1" + path, headers=headers, **kwargs
                    )
                    assert 200 <= response.status_code < 300, response.text
                    return response.json()

                products = api("GET", "/products", params={"limit": 100})["items"]
                assert len(products) >= 40
                pieces = sorted(
                    (p for p in products if p["unit"] == "PIECE" and p["stock_quantity"] > 0),
                    key=lambda p: p["price_minor"],
                    reverse=True,
                )[:3]
                weight = next(
                    p for p in products if p["unit"] == "KG" and p["stock_quantity"] > 3000
                )
                selected = pieces + [weight]

                def create_cart(terminal: str) -> dict:
                    order = api("POST", "/orders", json={"terminal_code": terminal})
                    for product in selected:
                        order = api(
                            "POST",
                            f"/orders/{order['public_id']}/items",
                            json={
                                "barcode": product["barcode"],
                                "quantity": 750 if product["unit"] == "KG" else 1,
                            },
                        )
                    return order

                order = create_cart("smoke-paid")
                payment = api("POST", f"/orders/{order['public_id']}/checkout")
                qr = client.get(shop_url + f"/api/v1/payments/{payment['public_id']}/qr.png")
                assert qr.status_code == 200 and qr.content.startswith(b"\x89PNG\r\n\x1a\n")
                token = urlsplit(payment["pay_url"]).path.rsplit("/", 1)[-1]
                invoice = client.get(bank_url + f"/api/pay/{token}").json()
                rich = max(invoice["accounts"], key=lambda account: account["balance_minor"])
                assert client.get(payment["pay_url"]).status_code == 200
                paid = client.post(
                    bank_url + f"/api/pay/{token}", json={"account_id": rich["public_id"]}
                )
                assert paid.status_code == 200, paid.text
                wait_for(
                    client,
                    shop_url + f"/api/v1/payments/{payment['public_id']}",
                    lambda data: data["status"] == "SUCCEEDED",
                )
                assert api("GET", f"/orders/{order['public_id']}")["status"] == "PAID"
                assert api("GET", f"/orders/{order['public_id']}/receipt")["payment_method"] == "QR"
                assert (
                    client.get(shop_url + "/api/v1/public/terminals/smoke-paid/display").json()[
                        "state"
                    ]
                    == "paid"
                )
                with sqlite3.connect(temporary / "shop.db") as connection:
                    for product in selected:
                        row = connection.execute(
                            "SELECT stock_quantity, reserved_quantity FROM products "
                            "WHERE public_id=?",
                            (product["public_id"].replace("-", ""),),
                        ).fetchone()
                        quantity = 750 if product["unit"] == "KG" else 1
                        assert row == (product["stock_quantity"] - quantity, 0)
                print("Real TCP: 3 piece products + weighted item + QR + signed webhook + PAID: OK")

                poor_order = create_cart("smoke-poor")
                poor_payment = api("POST", f"/orders/{poor_order['public_id']}/checkout")
                token = urlsplit(poor_payment["pay_url"]).path.rsplit("/", 1)[-1]
                invoice = client.get(bank_url + f"/api/pay/{token}").json()
                poor = min(
                    (a for a in invoice["accounts"] if a["balance_minor"] > 0),
                    key=lambda account: account["balance_minor"],
                )
                assert (
                    client.post(
                        bank_url + f"/api/pay/{token}", json={"account_id": poor["public_id"]}
                    ).status_code
                    == 200
                )
                wait_for(
                    client,
                    shop_url + f"/api/v1/payments/{poor_payment['public_id']}",
                    lambda data: data["status"] == "FAILED",
                )
                assert api("GET", f"/orders/{poor_order['public_id']}")["status"] == "OPEN"
                print("Real TCP: insufficient funds + webhook + order reopened: OK")

                retry = api("POST", f"/orders/{poor_order['public_id']}/checkout")
                wait_for(
                    client,
                    shop_url + f"/api/v1/payments/{retry['public_id']}",
                    lambda data: data["status"] == "EXPIRED",
                    timeout=15,
                )
                assert api("GET", f"/orders/{poor_order['public_id']}")["status"] == "OPEN"
                with sqlite3.connect(temporary / "shop.db") as connection:
                    assert (
                        connection.execute(
                            "SELECT sum(reserved_quantity) FROM products"
                        ).fetchone()[0]
                        == 0
                    )
                for path in ("/login", "/price-check", "/display/main"):
                    assert client.get(shop_url + path).status_code == 200
                print("Real TCP: background expiry + reserve released + public pages: OK")
        except Exception:
            for log in logs:
                log.flush()
                log.seek(0)
                print(log.read(), file=sys.stderr)
            raise
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            for log in logs:
                log.flush()
                log.seek(0)
                shutdown_logs.append(log.read())
                log.close()
        assert all(process.returncode in (0, -signal.SIGTERM) for process in processes)
        assert all("Application shutdown complete." in output for output in shutdown_logs)
        print("Both Uvicorn processes stopped cleanly; temporary databases removed: OK")


if __name__ == "__main__":
    main()
