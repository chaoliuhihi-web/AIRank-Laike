#!/bin/sh
set -eu

required_names="MYSQL_ROOT_PASSWORD AIRANK_DB_APP_PASSWORD AIRANK_DB_MIGRATOR_PASSWORD"
for name in $required_names; do
  case "$name" in
    MYSQL_ROOT_PASSWORD) value=${MYSQL_ROOT_PASSWORD:-} ;;
    AIRANK_DB_APP_PASSWORD) value=${AIRANK_DB_APP_PASSWORD:-} ;;
    AIRANK_DB_MIGRATOR_PASSWORD) value=${AIRANK_DB_MIGRATOR_PASSWORD:-} ;;
    *)
      printf '%s\n' "unexpected database bootstrap variable: $name" >&2
      exit 1
      ;;
  esac
  if [ -z "$value" ]; then
    printf '%s\n' "missing required database bootstrap variable: $name" >&2
    exit 1
  fi
  case "$value" in
    *[!A-Za-z0-9._~@%+=:-]*)
      printf '%s\n' "database bootstrap variable contains unsupported characters: $name" >&2
      exit 1
      ;;
  esac
done

MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=socket --user=root <<SQL
CREATE DATABASE IF NOT EXISTS airank_laike CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS 'airank_app'@'%' IDENTIFIED BY '${AIRANK_DB_APP_PASSWORD}' REQUIRE SSL;
ALTER USER 'airank_app'@'%' IDENTIFIED BY '${AIRANK_DB_APP_PASSWORD}' REQUIRE SSL;
GRANT SELECT, INSERT, UPDATE, DELETE ON airank_laike.* TO 'airank_app'@'%';
CREATE USER IF NOT EXISTS 'airank_migrator'@'%' IDENTIFIED BY '${AIRANK_DB_MIGRATOR_PASSWORD}' REQUIRE SSL;
ALTER USER 'airank_migrator'@'%' IDENTIFIED BY '${AIRANK_DB_MIGRATOR_PASSWORD}' REQUIRE SSL;
GRANT ALL PRIVILEGES ON airank_laike.* TO 'airank_migrator'@'%';
FLUSH PRIVILEGES;
SQL
