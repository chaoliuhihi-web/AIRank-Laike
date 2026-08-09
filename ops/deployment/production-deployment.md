# AIRank 来客生产部署文档

本文档用于把 AIRank 来客交给开发、运维或客户技术团队部署上线。当前仓库分成两条部署线：

- 官网宣传站：`AIRank素材/Web宣传/airank-design-grade-frontend`，当前已经可以作为官网上线候选版本。
- AIRank SaaS 系统：`apps/web`、`apps/api`、`apps/worker`、`apps/scheduler`，用于控制台、API、扫描、到期复测和报告主链路，必须通过 release gate 后再上线。

## 1. 下载代码

推荐从 GitHub 下载，国内网络环境也可以从 Gitee 下载。

GitHub：

```bash
git clone https://github.com/chaoliuhihi-web/AIRank-Laike.git
cd AIRank-Laike
```

Gitee：

```bash
git clone https://gitee.com/xinghetech/AIRank-Laike.git
cd AIRank-Laike
```

有写权限的开发人员也可以使用 SSH：

```bash
git clone git@github.com:chaoliuhihi-web/AIRank-Laike.git
git remote add gitee git@gitee.com:xinghetech/AIRank-Laike.git
```

部署前先同步最新代码：

```bash
git fetch origin
git merge --ff-only origin/main
```

## 2. 当前推荐上线范围

现阶段推荐先上线官网宣传站，路径如下：

```text
AIRank素材/Web宣传/airank-design-grade-frontend
```

这个目录是静态页面，包含首页、产品能力、解决方案、客户案例、资源中心、定价、免费体检、隐私政策、服务条款、404、sitemap 和 robots。

免费体检表单会提交到：

```text
/api/leads
```

Vercel 默认使用 `api/leads.js`，Netlify 默认使用 `netlify/functions/leads.js`。如果使用纯 Nginx 静态部署，必须额外把 `/api/leads` 反向代理到一个 Node/serverless 接口，否则表单无法发送邮件。

## 3. 官网本地验证

进入官网目录：

```bash
cd AIRank素材/Web宣传/airank-design-grade-frontend
npm install
```

启动本地预览：

```bash
npm run serve
```

访问：

```text
http://localhost:8080/
http://localhost:8080/product/
http://localhost:8080/solutions/
http://localhost:8080/pricing/
http://localhost:8080/diagnosis/
```

上线前必须运行：

```bash
npm run check
npm run routes
```

期望结果：

- 所有 HTML、CSS、JS、图片引用通过检查。
- clean URL 路由目录存在，例如 `/product/`、`/solutions/`、`/pricing/`。
- 浏览器控制台没有 error。
- 桌面端和移动端没有横向滚动、图片破图或按钮遮挡。

## 4. 方式 A：Vercel 部署官网

适合快速上线官网和线索邮件接口。

Vercel 项目配置：

```text
Framework Preset: Other
Root Directory: AIRank素材/Web宣传/airank-design-grade-frontend
Install Command: npm install
Build Command: npm run check && npm run routes
Output Directory: .
Node.js Version: 20 或 22
```

环境变量：

```text
SMTP_HOST=你的 SMTP 服务器
SMTP_PORT=465
SMTP_SECURE=true
SMTP_USER=发件邮箱账号
SMTP_PASS=发件邮箱授权码
SMTP_FROM=发件邮箱
LEAD_EMAIL_TO=airank@xinghetech.cn
ALLOWED_ORIGINS=https://airank.net.cn,https://www.airank.net.cn
```

可选环境变量：

```text
LEAD_WEBHOOK_URL=飞书/钉钉/自定义 webhook
LEAD_WEBHOOK_MODE=json
LEAD_DRY_RUN=1
```

上线后验证：

```bash
curl -I https://airank.net.cn/
curl -I https://airank.net.cn/product/
curl -I https://airank.net.cn/sitemap.xml
```

表单接口验证：

```bash
curl -X POST https://airank.net.cn/api/leads \
  -H 'Content-Type: application/json' \
  -d '{"website":"https://www.xinghetech.cn","company":"测试公司","name":"测试","phone":"13800000000","intent":"deploy-smoke"}'
```

返回 `{"ok":true,...}` 且 `airank@xinghetech.cn` 收到邮件，才算线索链路通过。

## 5. 方式 B：Netlify 部署官网

Netlify 项目配置：

```text
Base directory: AIRank素材/Web宣传/airank-design-grade-frontend
Build command: npm run check && npm run routes
Publish directory: .
Functions directory: netlify/functions
Node.js Version: 20 或 22
```

环境变量与 Vercel 相同。

`netlify.toml` 已经包含 clean URL 跳转和缓存头。部署后同样要验证：

- 首页、产品、解决方案、资源中心、定价页可以访问。
- `/product.html` 会 301 到 `/product/`。
- `/api/leads` 或 `/.netlify/functions/leads` 能成功提交。
- 邮件能送达 `airank@xinghetech.cn`。

## 6. 方式 C：Nginx 静态部署官网

适合部署到自有服务器。注意：纯静态 Nginx 只能托管页面，不能直接运行邮件接口。

服务器准备：

```bash
sudo mkdir -p /var/www/airank-frontend
```

同步静态文件：

```bash
cd AIRank素材/Web宣传/airank-design-grade-frontend
npm install
npm run check
npm run routes
sudo rsync -a --delete ./ /var/www/airank-frontend/ \
  --exclude node_modules \
  --exclude .git
```

Nginx 配置可从仓库复制：

```bash
sudo cp nginx.conf.example /etc/nginx/conf.d/airank.net.cn.conf
sudo nginx -t
sudo systemctl reload nginx
```

如果要让表单可用，必须增加其中一种方案：

- 把 `/api/leads` 反向代理到 Vercel/Netlify/serverless 地址。
- 单独部署一个 Node API，复用 `api/leads.js` 的逻辑。
- 后续接入 `apps/api` 后，把线索接口迁移到 AIRank API，再由 Nginx 反向代理到 API 服务。

示例反向代理片段：

```nginx
location /api/leads {
  proxy_pass http://127.0.0.1:3001/api/leads;
  proxy_set_header Host $host;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_set_header X-Forwarded-Proto $scheme;
}
```

HTTPS 推荐使用 Certbot：

```bash
sudo certbot --nginx -d airank.net.cn -d www.airank.net.cn
```

## 7. DNS 配置

按部署平台给出的记录配置域名：

- Vercel/Netlify：通常配置 `CNAME` 到平台分配域名。
- 自有服务器：配置 `A` 记录到服务器公网 IP。
- 同时配置 `airank.net.cn` 和 `www.airank.net.cn`。

生效后检查：

```bash
dig airank.net.cn
dig www.airank.net.cn
curl -I https://airank.net.cn/
```

## 8. 上线前检查清单

官网上线前至少检查：

- `npm run check` 通过。
- `npm run routes` 通过。
- 首页、产品能力、解决方案、客户案例、资源中心、定价、免费体检、关于我们全部能打开。
- PC 端和手机端首屏、第二屏、底部页脚无明显错位。
- LOGO、备案号、电话、公司名、隐私政策、服务协议为最终版本。
- `sitemap.xml`、`robots.txt`、canonical 是正式域名。
- 表单能提交，邮件能发送到 `airank@xinghetech.cn`。
- 静态资源缓存头正确，HTML 不长缓存，`assets/*` 可以长缓存。
- 404 页面存在。
- HTTPS 正常，HTTP 自动跳转 HTTPS。

## 9. 完整 SaaS 生产拓扑

生产只使用 `ops/deployment/compose.production.yml` 或与其等价的 Kubernetes
编排，不使用 `vite preview`、开发 MySQL、文件系统证据存储或仓库内明文
`.env`。编排包含五个相互独立的进程：

```text
migrate → Alembic 单次迁移
api     → FastAPI，同一镜像双进程
worker  → 扫描、证据、内容、发布任务
scheduler → T0/T+7/T+14/T+30 和治理任务调度
web     → 非 root Nginx 静态控制台和同源 API 反向代理
```

MySQL、S3/MinIO、Yudao 和 TLS 终止层必须由生产基础设施提供，Compose
不会偷偷启动弱口令数据库或本地对象存储。API、Worker、Scheduler 均先运行
`scripts/production_preflight.py`；任何 dev/mock/local、明文传输、占位密钥、
未轮换泄露凭证、DeepSeek 临下架模型或错误权限配置都会拒绝启动。

Web 容器只绑定 `127.0.0.1:8080`；公网 TLS 终止层必须追加 HSTS、证书续期
监控和真实客户端 IP 限流。容器内 Nginx 负责 CSP、点击劫持、MIME 嗅探和
同源 API 代理，但不能替代公网 WAF/限流。

## 10. 构建不可变镜像

构建机必须处于干净、已评审的 commit：

```bash
git status --short
release_commit=$(git rev-parse HEAD)
test -n "$release_commit"

docker build \
  --build-arg AIRANK_BUILD_COMMIT="$release_commit" \
  --file ops/deployment/Dockerfile.backend \
  --tag registry.example.cn/airank/backend:"$release_commit" .

docker build \
  --file ops/deployment/Dockerfile.web \
  --tag registry.example.cn/airank/web:"$release_commit" .
```

后端镜像使用 `requirements-prod.lock` 的精确依赖版本；升级依赖必须先重新跑
全量门禁并更新锁文件。两个镜像必须完成漏洞扫描（Python 包由 `pip-audit`，
最终 OS 层由 Trivy）、生成 SBOM、签名并推送。部署时只接受 registry
返回的 `image@sha256:...`，不接受 `latest` 或可变 tag：

```bash
export AIRANK_BACKEND_IMAGE='registry.example.cn/airank/backend@sha256:实际摘要'
export AIRANK_WEB_IMAGE='registry.example.cn/airank/web@sha256:实际摘要'
```

后端镜像以 UID/GID `10001` 运行，包含 Playwright Chromium，但浏览器登录
profile 仍须通过加密卷受控注入；profile 不进入镜像、Git 或构建缓存。

## 11. 生产配置与密钥

以 `ops/deployment/env.production.example` 为字段清单。实际值只由云 Secret
Manager、Vault 或部署平台 Secret 注入；若临时使用 `.env.production`，文件
权限必须为 `0600`，部署完成后按组织策略销毁。不要从
`ops/deployment/env.example` 复制开发密码。

强制边界包括：

- `AIRANK_ENV=production`、`AIRANK_AUTH_MODE=yudao`、认证强制开启。
- Yudao tenant-id 必须通过 `airank_tenant_bindings` 显式映射到 AIRank tenant；
  生产使用 `AIRANK_TENANT_RESOLUTION_MODE=database`，不允许默认租户兜底。
- 首个客户租户的 `AIRANK_RELEASE_TENANT_ID` 与
  `AIRANK_RELEASE_YUDAO_TENANT_ID` 必须唯一对应一条 active 绑定；严格门禁会查询
  数据库确认，不能使用 `tenant_demo`。
- 运行账号只授予业务 DML；迁移使用独立 `AIRANK_MIGRATION_DATABASE_URL`。
- MySQL URL 开启证书、证书链和主机名校验。
- S3/MinIO 仅 HTTPS，证据桶开启版本控制、服务端加密和保留策略；
  `AIRANK_S3_TIMEOUT_SECONDS` 必须设在 1–300 秒内（建议 10 秒），连接与读取
  共用该超时，并在 SDK 层执行标准退避重试。
- AES-GCM 与 HMAC keyring 使用两组不同的 32 字节随机材料。
- 曾出现在聊天、日志、工单中的凭证全部轮换后，才允许设置
  `AIRANK_COMPROMISED_CREDENTIALS_ROTATED=true`。
- Provider API 与 Consumer Browser 样本分别标记证据等级；要声明 Consumer
  Browser 能力，必须另行通过浏览器 L3 门禁。
- DeepSeek v3.2 不允许作为新生产发布目标；先完成替代模型 L3、迁移计划和审批。
- `AIRANK_PUBLISH_ALLOWED_HOSTS` 只列实际客户发布域名，默认发布状态为
  `draft` 或 `pending`。

构建并推送镜像后，通过与正式服务相同的容器环境做无副作用配置检查：

```bash
docker compose \
  --file ops/deployment/compose.production.yml \
  run --rm --no-deps api \
  python3 scripts/production_preflight.py --role release
```

脚本只输出检查名称、blocker 和 warning，不输出 Token、Provider Key 或
keyring 材料。

在启动服务前，显式授权一次生产 S3 写读探测。该探测只创建一个固定内容、
幂等且不可变的系统哨兵，不删除或修改客户证据：

```bash
AIRANK_RELEASE_RUN_STORAGE_PROBE=true \
  docker compose \
  --file ops/deployment/compose.production.yml \
  run --rm --no-deps api \
  python3 scripts/probe_object_storage.py
```

输出 `status=pass` 后才能继续；输出不包含 S3 凭证。

## 12. 数据库备份、迁移和启动

迁移前在云数据库创建一致性快照并完成恢复抽检，把不可变备份任务号写入
`AIRANK_DATABASE_BACKUP_RECEIPT`。没有备份回执，迁移容器会失败关闭。

确认生产配置后启动：

```bash
docker compose \
  --file ops/deployment/compose.production.yml \
  config --quiet

docker compose \
  --file ops/deployment/compose.production.yml \
  up --detach
```

Compose 先等待迁移成功，再启动 API/Worker/Scheduler；Web 只有在 API
`/api/v1/ready` 返回 200 后才进入服务。检查：

```bash
docker compose --file ops/deployment/compose.production.yml ps
curl --fail https://console.airank.example.cn/api/v1/health
curl --fail https://console.airank.example.cn/api/v1/ready
curl --fail https://console.airank.example.cn/api/v1/version
```

`/health` 只证明进程存活；`/ready` 同时检查生产配置、数据库连通、Alembic
版本并真实读取发布阶段写入的 S3 哨兵，部署探针必须使用 `/ready`。Worker 与
Scheduler 会在各自主循环内原子更新 `/tmp/airank-health/*.json`；Compose
分别按 600 秒和 120 秒新鲜度检查，不能只凭“进程还在”判定健康。

## 13. 严格上线门禁

生产变更窗口前，在与生产等价的隔离数据库运行：

```bash
python3 scripts/release_readiness.py \
  --database-url "$AIRANK_RELEASE_DATABASE_URL" \
  --require-browser-providers \
  --report /tmp/airank-release-readiness.md
```

只有报告首部 `Result: PASS` 才能进入流量。若本次销售范围承诺 Xinghe 可选
增强能力，再追加 `--require-optional-capabilities`；未采购的可选能力应保持
`disabled`，不能配置假 endpoint 让门禁误判。

发布后还要完成：

1. 真实 Yudao 用户登录、租户隔离和权限拒绝验证。
2. 四平台重复采样，逐样本检查回答、引用、request-id、时间、模型和证据等级。
3. 真实客户 WordPress/HTTP 的首次发布、更新、撤回和回执核验。
4. 两名不同人员完成一次结果未知发布对账。
5. 导出客户报告并从任一指标下钻到原始样本。
6. 建立 T+7/T+14/T+30 观察窗口；时间未到必须显示 pending。

## 14. 回滚和灾难恢复

应用回滚只切换到上一份已签名镜像 digest。迁移均应保持向后兼容；已有新
版本写入后，不直接对生产库执行 Alembic downgrade。需要数据回滚时：

1. 停止入口流量、Scheduler 和 Worker，记录队列水位与 operation guard 状态。
2. 从预迁移快照恢复到新数据库实例，不覆盖原生产实例。
3. 对恢复库运行 `alembic current`、证据 hash 审计和关键数量核对。
4. 使用上一版镜像连接恢复库，先跑 `/ready` 和只读验收。
5. 经双人批准后切换连接，保留原实例供审计。

发布、凭证轮换等外部副作用处于 `external_started/outcome_unknown` 时，不自动
重试；必须进入对账流程。完整凭证轮换见
[Provider Credential Vault 运维手册](../../docs/operations/provider-credential-vault.md)。

## 15. 当前不可伪造的外部门禁

仓库代码通过不能替代以下生产证据：最终域名和证书、Yudao 生产租户、托管
MySQL/S3、四平台当前有效凭证与额度、Kimi 泄露凭证轮换、DeepSeek 替代模型
额度、Consumer Browser 登录态、真实客户发布账号、双人对账人员以及实际经过
的 T+7/T+14/T+30 时间窗口。任一缺失都应在上线报告中保持
`blocked/partial/disabled`，不得用本地成功或 mock 改写为完成。
