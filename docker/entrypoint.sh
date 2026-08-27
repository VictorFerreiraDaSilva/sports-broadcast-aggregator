#!/bin/sh
set -e

# Before alembic: with the database down, alembic would die here, the container
# would die with it and `restart: unless-stopped` would produce the mute crash
# loop ADR 0007 describes. This step keeps the container up, notifies once and
# waits for the database to come back.
echo "waiting for the database..."
python -m app.core.wait_for_db

echo "applying migrations (alembic upgrade head)..."
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
