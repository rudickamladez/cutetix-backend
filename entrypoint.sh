#!/usr/bin/env bash
set -euo pipefail

echo "[entrypoint] Applying Alembic migrations..."

python - <<'PY'
import os
import time
import sqlalchemy as sa

url = os.environ.get("SQLALCHEMY_DATABASE_URL")
if url is None:
    raise SystemExit("SQLALCHEMY_DATABASE_URL is not set")

if url is not None:
    # wait for DB (max 60s)
    for i in range(60):
        try:
            sa.create_engine(url).connect().close()
            break
        except Exception as e:
            print(f"[wait-db] attempt {i+1}/60: {e}")
            time.sleep(1)
else:
    raise SystemExit("Database not reachable")

eng = sa.create_engine(url)
with eng.connect() as c:
    insp = sa.inspect(c)
    tables = set(insp.get_table_names())

    has_alembic_tbl = "alembic_version" in tables
    version = None
    if has_alembic_tbl:
        try:
            version = c.execute(sa.text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:
            version = None

    app_tables = sorted(tables - {"alembic_version"})

    if (not has_alembic_tbl or not version):
        # DB není „zapsaná“ do Alembicu
        if app_tables:
            action = "STAMP_INIT_THEN_UPGRADE"   # tabulky existují → stamp initial, pak upgrade
        else:
            action = "UPGRADE"                   # čistá DB → stačí upgrade (vytvoří initial)
    else:
        action = "UPGRADE"                       # máme platnou verzi → normální upgrade

    print(f"[entrypoint] tables={app_tables}; has_alembic_tbl={has_alembic_tbl}; version={version}; action={action}")
    open("/tmp/alembic_action", "w").write(action)
PY

ACTION=$(cat /tmp/alembic_action)
# You can put the initial revision ID in ENV, default here:
ALEMBIC_INIT_REV="${ALEMBIC_INIT_REV:-0001_initial_schema}"

if [ "$ACTION" = "STAMP_INIT_THEN_UPGRADE" ]; then
  python -m alembic stamp "$ALEMBIC_INIT_REV"
  python -m alembic upgrade head
else
  python -m alembic upgrade head
fi

echo "[entrypoint] Alembic done. Starting API..."
exec uvicorn app.main:app --proxy-headers --forwarded-allow-ips '*' --host 0.0.0.0 --port 80 --log-config logging.json
