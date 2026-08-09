# AIRank 单机生产部署（4C/8G）

本方案用于资源受限但要求真实数据、真实 Provider 和可审计证据的首发环境。
它不是开发模式：MySQL 与 MinIO 使用独立 TLS，应用只监听宿主机回环地址，
所有持久数据必须落在数据盘。

## 1. 前置门禁

- 数据盘可用空间至少 40 GiB，根盘使用率低于 75%。
- `console.airank.net.cn` 已解析到部署服务器，且可签发公网证书。
- 已取得独立 Yudao 服务凭证及正式租户绑定。
- 所有曾暴露的 Provider 密钥已经轮换；没有轮换时保持
  `AIRANK_COMPROMISED_CREDENTIALS_ROTATED=false`，应用会拒绝启动。
- Kimi 和 DeepSeek 仅在新密钥与非下架窗口模型完成 L3 验证后启用。

## 2. 构建不可变版本

从已同步并通过测试的 Git commit 构建镜像，镜像标签必须包含完整 commit：

```bash
commit=$(git rev-parse HEAD)
docker build --build-arg AIRANK_BUILD_COMMIT="$commit" \
  -f ops/deployment/Dockerfile.backend -t "airank-backend:$commit" .
docker build -f ops/deployment/Dockerfile.web -t "airank-web:$commit" .
docker image inspect "airank-backend:$commit" "airank-web:$commit" \
  --format '{{.RepoTags}} {{.Id}}'
```

网络受限的部署机可额外传入 `APT_MIRROR`、`PIP_INDEX_URL` 与
`NPM_REGISTRY` build arg；默认值仍是官方源，锁文件中的精确版本不因镜像源
改变。

生产环境应把镜像推入私有仓库并在 `.env.production` 中使用 digest；单机候选
验收至少要保存 commit 标签与本机 image ID 的对应记录。

## 3. 准备数据和私密配置

```bash
install -d -m 0750 /home/www1/airank/data/{mysql,minio,browser-profiles,browser-captures}
install -d -m 0700 /home/www1/airank/secrets/pki
install -d -m 0755 /home/www1/airank/acme
cp ops/deployment/env.single-node.production.example ops/deployment/.env.production
chmod 0600 ops/deployment/.env.production
```

通过已构建的后端镜像生成内部 PKI。脚本拒绝覆盖已有证书，输出只包含公开
指纹与有效期：

```bash
docker run --rm --user 0 \
  -v /home/www1/airank/secrets/pki:/out \
  "airank-backend:$commit" \
  python3 scripts/bootstrap_single_node_pki.py --output-dir /out
```

根据固定镜像内的运行 UID 设置三个私钥的 owner，私钥保持 `0400`；CA 与服务
证书保持 `0444`。不要把私钥复制进代码仓或工单。

生成独立随机值填入 `.env.production`：MySQL root/app/migrator、MinIO、
Provider Vault 加密 keyring 与 fingerprint keyring。两个 keyring 必须使用不同的
32 字节随机材料。数据库密码使用 URL-safe 字符，并分别同步到数据库 URL。

## 4. 配置检查与启动

```bash
cd ops/deployment
docker compose --env-file .env.production \
  -f compose.single-node.production.yml config --quiet
docker compose --env-file .env.production \
  -f compose.single-node.production.yml up -d mysql minio yudao-proxy
docker compose --env-file .env.production \
  -f compose.single-node.production.yml run --rm object-storage-bootstrap
docker compose --env-file .env.production \
  -f compose.single-node.production.yml up -d --wait
```

`migrate`、对象存储建桶与版本化、API preflight 任一失败时，Web 都不会启动。

## 5. 公网入口

DNS 生效并签发证书后，把 `console.airank.net.cn.conf.example` 安装为宿主机
Nginx vhost。宿主机只反代 `127.0.0.1:18080`；MySQL、MinIO、Yudao 代理均不
开放公网端口。

## 6. 验收

```bash
curl -fsS http://127.0.0.1:18080/healthz
curl -fsS http://127.0.0.1:18080/api/v1/ready
python3 scripts/release_readiness.py --require-browser-providers
```

还必须完成真实 Provider L3、浏览器 E2E、队列、报告导出、对象存储写读探测、
租户绑定与远端 commit 同步。报告中出现任何 `BLOCKED` 都不能声明上线。
