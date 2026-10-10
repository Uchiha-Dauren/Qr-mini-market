#!/bin/sh
set -eu

# Named volumes preserve data. Both seeds insert missing demo entries only.
case "${1:-shop}" in
    shop)
        python -m alembic upgrade head
        python -m app.seed
        exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
        ;;
    mock_bank)
        python -m mock_bank.seed
        exec python -m uvicorn mock_bank.main:app --host 0.0.0.0 --port 8001 --no-access-log
        ;;
    *)
        exec "$@"
        ;;
esac
