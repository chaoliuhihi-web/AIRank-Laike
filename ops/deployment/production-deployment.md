# AIRank 来客生产部署文档

本文档用于把 AIRank 来客交给开发、运维或客户技术团队部署上线。当前仓库分成两条部署线：

- 官网宣传站：`AIRank素材/Web宣传/airank-design-grade-frontend`，当前已经可以作为官网上线候选版本。
- AIRank SaaS 系统：`apps/web`、`apps/api`、`apps/worker`，用于后续控制台、API、扫描和报告主链路，必须通过 release gate 后再上线。

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

## 9. 完整 SaaS 系统部署

完整 AIRank 系统包含：

```text
apps/web      控制台前端
apps/api      FastAPI 产品 API
apps/worker   扫描、归因、内容、报告等异步任务
MySQL         业务数据库
对象存储       快照、证据包、报告文件
```

当前完整 SaaS 必须通过 release gate 后才能声明可上线：

```bash
python3 scripts/release_readiness.py \
  --database-url "$AIRANK_RELEASE_DATABASE_URL" \
  --require-optional-capabilities \
  --require-browser-providers
```

API 基础部署命令：

```bash
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r apps/api/requirements-dev.txt 'uvicorn[standard]'
```

准备数据库：

```bash
mysql -uroot -p < ops/deployment/mysql-bootstrap.sql
export AIRANK_DATABASE_URL='mysql+pymysql://airank:airank_dev_password@127.0.0.1:3306/airank_laike?charset=utf8mb4'
cd apps/api
python3 -m alembic upgrade head
```

启动 API：

```bash
cd /path/to/AIRank-Laike
. .venv/bin/activate
python3 -m uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/version
```

控制台前端：

```bash
cd apps/web
npm ci
npm run build
npm run preview -- --port 5173
```

生产环境需要把 `apps/web/dist` 交给 Nginx/CDN，并把 `/api/v1/*` 反向代理到 `apps/api`。

## 10. 环境变量

基础环境变量参考：

```text
ops/deployment/env.example
```

生产必须替换：

```text
AIRANK_ENV=production
AIRANK_DATABASE_URL=生产 MySQL 连接串
AIRANK_OBJECT_STORAGE_DRIVER=生产对象存储类型
AIRANK_OBJECT_STORAGE_ROOT=生产持久化路径或对象存储配置
AIRANK_AUTH_MODE=yudao
YUDAO_BASE_URL=生产 yudao 地址
YUDAO_BEARER_TOKEN=生产 token
XINGHE_CAPABILITY_MODE=adapter
```

真实生产密钥只允许放在部署平台、CI/CD Secret、systemd EnvironmentFile 或容器 secret 中，不允许提交到 Git。

## 11. 发布和回滚

发布前记录当前 commit：

```bash
git rev-parse HEAD
```

推荐打 tag：

```bash
git tag -a web-$(date +%Y%m%d-%H%M) -m "AIRank web release"
git push origin --tags
git push gitee --tags
```

回滚官网：

- Vercel/Netlify：在平台控制台选择上一个成功 deployment 回滚。
- Nginx：保留上一版 `/var/www/airank-frontend` 目录快照，失败时切回并 reload Nginx。

Nginx 快照示例：

```bash
sudo cp -a /var/www/airank-frontend /var/www/airank-frontend.backup.$(date +%Y%m%d%H%M)
```

回滚 API：

- 先回滚应用版本。
- 数据库迁移如果涉及破坏性变更，必须按迁移说明执行，不允许临时手动删表改表。
- 回滚后重新检查 `/api/v1/health`、核心页面和线索提交。

## 12. 交付给第三方的最短说明

可以直接发给部署人员：

```text
代码地址：
GitHub: https://github.com/chaoliuhihi-web/AIRank-Laike
Gitee: https://gitee.com/xinghetech/AIRank-Laike

当前先部署官网目录：
AIRank素材/Web宣传/airank-design-grade-frontend

推荐部署平台：
Vercel 或 Netlify

构建配置：
Root/Base Directory: AIRank素材/Web宣传/airank-design-grade-frontend
Install Command: npm install
Build Command: npm run check && npm run routes
Output/Publish Directory: .

必须配置邮件环境变量：
SMTP_HOST
SMTP_PORT
SMTP_SECURE
SMTP_USER
SMTP_PASS
SMTP_FROM
LEAD_EMAIL_TO=airank@xinghetech.cn
ALLOWED_ORIGINS=https://airank.net.cn,https://www.airank.net.cn

上线后检查：
首页、产品、解决方案、资源、定价、免费体检页面都能打开；
免费体检表单提交后 airank@xinghetech.cn 能收到邮件。
```
