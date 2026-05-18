# AIRank 来客 官网前端（视觉精修上线候选版）

域名：`https://airank.net.cn`  
公司：北京智界问道科技有限公司  
电话：400-110-8776

本版本重点修复：

- 统一 clean URL、canonical、sitemap：如 `/product/`、`/solutions/`、`/pricing/`。
- 修缓存策略：CSS/JS 使用版本化文件名，HTML 短缓存，图片/静态资源长缓存。
- 视觉精修：切图资源做 2x 高清化和 WebP 高质量重生成；字体、标题、卡片、按钮、Hero 间距、移动端断点重新调整。
- 产品页首屏改为更接近原始效果图的居中大视觉布局。
- 解决方案页锚点与页脚跳转整理。
- 资源中心下载链路跳到体检页并带 source 参数，后续可继续接真实线索接口或下载文件。

## 本地预览

```bash
npm run serve
# 或
python3 -m http.server 8080
```

访问：

```text
http://localhost:8080/
http://localhost:8080/product/
http://localhost:8080/solutions/
http://localhost:8080/pricing/
```

## 检查

```bash
npm run check
npm run routes
```

## 线索邮件配置

所有 `免费测一测` 的官网输入会进入 `/diagnosis/`，用户填写信息后由 `/api/leads` 发送到 `airank@xinghetech.cn`。Netlify 部署会通过 `/.netlify/functions/leads` 走同一套逻辑。

上线时需要在 Vercel 或 Netlify 配置 SMTP 环境变量：

```text
SMTP_HOST=你的 SMTP 服务器
SMTP_PORT=465
SMTP_SECURE=true
SMTP_USER=发件邮箱账号
SMTP_PASS=发件邮箱授权码
SMTP_FROM=发件邮箱
LEAD_EMAIL_TO=airank@xinghetech.cn
```

可选项：

```text
ALLOWED_ORIGINS=https://airank.net.cn,https://www.airank.net.cn
LEAD_WEBHOOK_URL=可选的飞书/钉钉/自定义 webhook
LEAD_WEBHOOK_MODE=json
LEAD_DRY_RUN=1
```

## 仍需正式替换

- 公安备案号
- 二维码
- 隐私政策/服务协议的最终法务版本
