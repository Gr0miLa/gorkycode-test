#!/bin/sh
set -eu

alembic upgrade head
if [ "${IMPORT_SEED:-false}" = "true" ]; then
  python -m scripts.import_seed
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
