#!/bin/sh
# Creates one database per service (database-per-service pattern). Runs once, on first container start.
# Production: give each service its own role with privileges only on its own database.
set -eu
for db in ${IRIS_DATABASES:-}; do
  echo "Creating database '$db'"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-SQL
	SELECT 'CREATE DATABASE $db OWNER "$POSTGRES_USER"'
	WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '$db')\gexec
SQL
done
