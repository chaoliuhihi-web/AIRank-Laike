# Integration Tests

These tests are skipped by default because they touch real local services.

Run real MySQL checks after starting MySQL and applying local grants:

```bash
AIRANK_RUN_REAL_MYSQL=1 \
AIRANK_DATABASE_URL="mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4" \
python3 -m pytest tests/integration -q
```

Run real yudao checks after starting yudao and exporting local test credentials:

```bash
AIRANK_RUN_REAL_YUDAO=1 \
YUDAO_BASE_URL="http://127.0.0.1:48080" \
YUDAO_TENANT_ID="1" \
YUDAO_USERNAME="$YUDAO_USERNAME" \
YUDAO_PASSWORD="$YUDAO_PASSWORD" \
python3 -m pytest tests/integration -q
```

For release-gate validation on a local all-in-one dev stack, enable both flags
in one command. The tests never print yudao access tokens.
