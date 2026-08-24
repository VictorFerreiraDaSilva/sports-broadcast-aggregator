#!/bin/sh
set -e

echo "aplicando migrações (alembic upgrade head)..."
alembic upgrade head

case "$1" in
  scheduler)
    exec python -m app.scheduler
    ;;
  games|catalog)
    exec python -m app.main "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
