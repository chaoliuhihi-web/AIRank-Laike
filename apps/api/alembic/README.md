# AIRank API Alembic

Run migrations from this directory:

```bash
cd apps/api
alembic upgrade head
```

The migration runner reads the database URL from the first configured value:

1. `AIRANK_DATABASE_URL`
2. `ALEMBIC_DATABASE_URL`
3. `DATABASE_URL`
4. the local development default in `alembic.ini`

The local development database and user can be bootstrapped with:

```bash
mysql -uroot -p < ../../ops/deployment/mysql-bootstrap.sql
```

Migrations intentionally do not create MySQL users, grants, or databases. Those
deployment concerns stay in `ops/deployment/mysql-bootstrap.sql`.
