FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 market \
    && useradd --uid 10001 --gid 10001 --create-home market \
    && mkdir -p /data \
    && chown market:market /data

COPY app/ ./app/
COPY mock_bank/ ./mock_bank/
COPY migrations/ ./migrations/
COPY alembic.ini ./
COPY scripts/docker-entrypoint.sh ./scripts/docker-entrypoint.sh

RUN chmod 0555 /app/scripts/docker-entrypoint.sh

USER 10001:10001

EXPOSE 8000 8001

ENTRYPOINT ["/app/scripts/docker-entrypoint.sh"]
CMD ["shop"]
