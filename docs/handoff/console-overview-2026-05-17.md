# Console Overview Handoff - 2026-05-17

## Closed Loop

- Contract: `packages/contracts/console_overview.schema.json`
- API: `GET /api/v1/console/overview`
- Web: `apps/web/src/console/api.ts` hydrates the console overview and falls back to local data when the API is unavailable.
- Test: `tests/contracts/test_console_overview_contract.py` validates the FastAPI response data against the JSON Schema.

## Contract Notes

The contract covers the first dashboard slice only:

- `project`: tenant-scoped project identity used by the sidebar, date pill, project strip, and settings panel.
- `metric_cards`: dashboard KPI cards with stable tone and icon fields for frontend rendering.

The response remains inside the shared AIRank envelope:

```json
{
  "data": {},
  "meta": {
    "trace_id": "trc_...",
    "request_id": "req_..."
  }
}
```

## API Notes

`apps/api/main.py` is a FastAPI baseline. It keeps data deterministic and tenant-scoped by deriving the project id from the `tenant-id` header. It does not call worker scheduling or XingheAI2026V2 internals.

Run locally:

```bash
uvicorn apps.api.main:app --reload
```

## Web Notes

The Vite app requests `/api/v1/console/overview` with `tenant-id: tenant_demo`. In local static builds where the API is not running, the existing console data remains the fallback, so the UI stays usable.

For dev proxying, point Vite to the API server in a later pass once API dev serving is standardized.
