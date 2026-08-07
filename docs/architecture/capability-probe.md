# AIRank Capability Probe

`packages/xinghe-adapter` owns capability readiness checks for yudao, object
storage, and optional XingheAI2026V2/Hermes services.

## Status meanings

| Status | Meaning |
| --- | --- |
| `ready` | Probe succeeded and the capability can be used. |
| `partial` | Optional external capability is configured but unhealthy; AIRank fallback remains available. |
| `blocked` | Required MVP capability is missing or failed. |
| `dev_only` | Local/mock fallback is available for development but is not release-ready. |

## M4 probe coverage

| Capability | Required | Environment | Fallback |
| --- | --- | --- | --- |
| `yudao_auth` | Yes | `AIRANK_AUTH_MODE`, `YUDAO_PERMISSION_INFO_URL`, `YUDAO_BEARER_TOKEN` | `apps/api dev auth` |
| `yudao_tenant_user` | Yes | `YUDAO_PERMISSION_INFO_URL`, `YUDAO_BEARER_TOKEN` | `apps/api dev tenant context` |
| `object_storage` | Yes | `AIRANK_OBJECT_STORAGE_DRIVER`, filesystem root or S3 endpoint/bucket/region/credentials | local filesystem object storage |
| `xinghe_crawler_gateway` | No | `XINGHE_CRAWLER_GATEWAY_BASE_URL` | `packages/crawler-lite` |
| `xinghe_kb_service` | No | `XINGHE_KB_SERVICE_BASE_URL` | `packages/kb-lite` |
| `xinghe_creator_marketing` | No | `XINGHE_CREATOR_MARKETING_BASE_URL` | `packages/evidence` |
| `xinghe_workflow_runner` | No | `XINGHE_WORKFLOW_RUNNER_BASE_URL` | `apps/worker` |
| `xinghe_hermes` | No | `XINGHE_HERMES_BASE_URL` or `HERMES_BASE_URL` | `apps/worker scheduled jobs` |

The probe never reads XingheAI2026V2 internal paths and never treats optional
`partial` capabilities as `ready`.

For `s3` or `minio`, the required probe performs a unique write, byte-for-byte
readback, and delete. Production mode rejects filesystem-only storage,
plaintext S3 endpoints, and `AIRANK_S3_ALLOW_HTTP=true`; HTTP MinIO is allowed
only for an explicitly marked local test environment.
