# publishing — 发布状态机和渠道管理

管理内容资产从生成发布包到复测的完整发布生命周期。

## 发布状态机

```text
DRAFT → PACKAGED → PUBLISHED → CRAWLING → CRAWLED → INDEXED → PENDING_RETEST → RETESTED
```

状态说明：

| 状态 | 含义 |
| --- | --- |
| DRAFT | 未发布，内容待确认 |
| PACKAGED | 已生成发布包 |
| PUBLISHED | 已正式发布，或人工记录了客户确认发布 URL |
| CRAWLING | 搜索引擎或 AI 平台抓取中 |
| CRAWLED | 已被抓取 |
| INDEXED | 已被索引 |
| PENDING_RETEST | 待复测 |
| RETESTED | 已完成复测 |

## 发布渠道

### MVP 发布能力

```text
导出官网发布包
导出公众号 / 知乎 / 小红书草稿文本
导出 JSON-LD / sitemap / robots 建议
记录发布 URL
加入复测队列
```

### V1 发布能力

```text
官网 CMS 草稿
公众号草稿
知乎草稿
小红书草稿
飞书 / 企业微信任务通知
```

### V2 发布能力

```text
客户授权自动发布
定时发布
多平台发布状态同步
自动记录 URL
自动进入复测队列
```

## MVP 发布流程

```text
1. 导出官网发布包
2. 生成独立 AI 来客资产页
3. 更新 sitemap
4. 生成百度搜索资源平台提交建议
5. 导出公众号草稿
6. 导出知乎草稿
7. 导出小红书草稿
8. 记录发布 URL
9. 加入复测队列
```

## 国内优先

第一阶段优先发布渠道：

```text
官网发布包
百度搜索资源平台
公众号
知乎
小红书
视频号脚本
```

Google / Bing 作为出海增强。

## 核心领域对象

- `PublishRecord`：单个资产的发布记录，包含状态、渠道、URL、时间线。
- `PublishChannel`：发布渠道配置（官网、公众号、知乎等）。
- `RetestEntry`：复测队列条目，关联问题集和发布记录。
