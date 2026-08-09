# AIRank Skill Trust Gate

AIRank 的 Skill 是内部可组合能力，不是面向客户安装的 Skill 广场。Trust Gate 的目标是让每个 Skill 的依赖、网络、secret、文件写入、子进程、管理员权限和安装边界可审计，并在违反声明时阻止手工执行或晋级。

## 运行门禁

```bash
python3 scripts/audit_skill_trust.py --report /tmp/airank-skill-trust-report.json
python3 scripts/evaluate_core_skills.py
```

第一条命令只有在以下条件全部满足时返回 0：

- manifest 的 `dependencies` 与 `trust_policy.dependency_refs` 一一对应；
- Python module/symbol 和 Skill contract 均可解析；
- entrypoint 存在且可调用；
- runner 及其本地 helper 调用闭包没有越过声明的网络、secret、文件或子进程边界；
- 不存在疑似明文 secret；
- 管理员执行权限明确为 `airank:skill:admin`；
- 临时目录只复制声明的内部包根后，11 个 Skill 仍能完成隔离导入与依赖解析。

`--skip-install-simulation` 只用于快速诊断。因为隔离安装未执行，完整报告会保持失败，不能作为发布证据。

## API 与产品边界

- `GET /api/v1/admin/skills/trust-report` 返回 `airank.skill-trust-report.v1`，并受可信管理员权限保护。
- `POST /api/v1/admin/skills/{skill_id}/eval` 在 trust 失败时返回 `SKILL_TRUST_BLOCKED`，不会继续调用 runner。
- Skill 控制台显示本地信任放行数、隔离安装结果、policy/package/report hash 和边界声明。
- Promotion Ledger `1.1.0` 绑定 registry schema、trust engine 和 trust report hash；trust 失败会成为晋级 blocker。

## 不允许扩大的声明

当前报告固定：

```text
claim_level=repository_gate_only
native_runtime_enforcement=false
```

这表示当前已验证的是 AIRank 仓库级确定性门禁和隔离导入，不是 OS 级沙箱，也不是生产 Worker 或第三方客户端的原生权限强制。Provider 调用、对象存储和客户数据访问继续由各自 Gateway、RBAC、任务和证据契约控制。11 个 Skill 即使本地 trust/eval 全通过，也会因真实 Provider、人工 benchmark 或时间窗口证据未齐而保留 `partial`。
