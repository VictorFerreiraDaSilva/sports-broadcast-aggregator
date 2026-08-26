#!/bin/sh
set -e

# Antes do alembic: com o banco fora do ar o alembic morreria aqui, o container
# morreria junto e o `restart: unless-stopped` faria o crash loop mudo que o
# ADR 0007 descreve. Este passo mantém o container de pé, notifica uma vez e
# espera o banco voltar.
echo "esperando o banco..."
python -m app.core.wait_for_db

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
