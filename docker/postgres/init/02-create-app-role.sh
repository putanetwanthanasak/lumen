#!/bin/sh
# S2: the app's own login role. Not a superuser, owns nothing; the table grants
# live in the Alembic migration a1c3e5f7b9d2, run as the superuser.
#
# Runs once on first container init (docker-entrypoint-initdb.d). Safe to run again
# on an existing cluster: it only creates the role if it is missing. CI runs this
# same file against its service container. The password comes from env only.
set -eu
: "${LUMEN_APP_PASSWORD:?set LUMEN_APP_PASSWORD}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
    -v app_password="$LUMEN_APP_PASSWORD" <<'SQL'
SELECT format(
    'CREATE ROLE lumen_app LOGIN PASSWORD %L '
    'NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS',
    :'app_password'
)
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'lumen_app')
\gexec
SQL
