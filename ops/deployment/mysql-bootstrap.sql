-- AIRank Laike MySQL bootstrap schema.
-- Target: MySQL 8.0+, InnoDB, utf8mb4.
-- Run: mysql -uroot -p < ops/deployment/mysql-bootstrap.sql

CREATE DATABASE IF NOT EXISTS airank_laike
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_0900_ai_ci;

CREATE USER IF NOT EXISTS 'airank'@'%' IDENTIFIED BY 'airank_dev_password';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES
  ON airank_laike.* TO 'airank'@'%';

USE airank_laike;

CREATE TABLE IF NOT EXISTS airank_tenant_bindings (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  yudao_tenant_id VARCHAR(64) NOT NULL,
  display_name VARCHAR(255) NULL,
  plan_code VARCHAR(64) NOT NULL DEFAULT 'mvp',
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  settings_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_airank_tenant_bindings_tenant (tenant_id),
  UNIQUE KEY uk_airank_tenant_bindings_yudao (yudao_tenant_id),
  KEY idx_airank_tenant_bindings_status (status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_user_bindings (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  yudao_user_id VARCHAR(64) NOT NULL,
  display_name VARCHAR(255) NULL,
  mobile VARCHAR(64) NULL,
  email VARCHAR(255) NULL,
  role_code VARCHAR(64) NOT NULL DEFAULT 'member',
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  last_seen_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_airank_user_bindings_yudao (tenant_id, yudao_user_id),
  KEY idx_airank_user_bindings_tenant_status (tenant_id, status, updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_projects (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  name VARCHAR(255) NOT NULL,
  brand_name VARCHAR(255) NOT NULL,
  website_url VARCHAR(1024) NULL,
  industry VARCHAR(128) NULL,
  region VARCHAR(128) NULL,
  products_services_json JSON NULL COMMENT '产品和服务列表',
  selling_points_json JSON NULL COMMENT '核心卖点列表',
  target_audience_json JSON NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_by VARCHAR(64) NULL,
  updated_by VARCHAR(64) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY idx_airank_projects_tenant_status (tenant_id, status, updated_at),
  KEY idx_airank_projects_brand (tenant_id, brand_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_project_members (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  yudao_user_id VARCHAR(64) NOT NULL,
  role_code VARCHAR(64) NOT NULL DEFAULT 'viewer',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_airank_project_members_user (tenant_id, project_id, yudao_user_id),
  KEY idx_airank_project_members_project (tenant_id, project_id),
  CONSTRAINT fk_airank_project_members_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_competitors (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  name VARCHAR(255) NOT NULL,
  website_url VARCHAR(1024) NULL,
  category VARCHAR(128) NULL,
  priority INT NOT NULL DEFAULT 100,
  notes TEXT NULL,
  metadata_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY idx_airank_competitors_project (tenant_id, project_id, priority),
  CONSTRAINT fk_airank_competitors_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_buyer_questions (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  question_text TEXT NOT NULL,
  question_type VARCHAR(64) NOT NULL DEFAULT 'commercial' COMMENT '问题类型：purchase/compare/select/trust/price/risk/scenario/local/alternative',
  intent VARCHAR(64) NOT NULL DEFAULT 'commercial',
  funnel_stage VARCHAR(64) NOT NULL DEFAULT 'consideration',
  search_volume INT NULL COMMENT '搜索热度估值',
  locale VARCHAR(32) NOT NULL DEFAULT 'zh-CN',
  source VARCHAR(64) NOT NULL DEFAULT 'manual',
  priority INT NOT NULL DEFAULT 100,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  metadata_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY idx_airank_questions_project_priority (tenant_id, project_id, priority),
  KEY idx_airank_questions_type (tenant_id, project_id, question_type),
  KEY idx_airank_questions_intent (tenant_id, project_id, intent, funnel_stage),
  CONSTRAINT fk_airank_questions_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_scan_runs (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  name VARCHAR(255) NULL,
  run_type VARCHAR(64) NOT NULL DEFAULT 'baseline',
  status VARCHAR(32) NOT NULL DEFAULT 'queued',
  provider_scope_json JSON NULL,
  question_scope_json JSON NULL,
  model_route_snapshot JSON NULL,
  metrics_json JSON NULL,
  error_message TEXT NULL,
  started_at DATETIME(3) NULL,
  finished_at DATETIME(3) NULL,
  created_by VARCHAR(64) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY idx_airank_scan_runs_project_status (tenant_id, project_id, status, created_at),
  KEY idx_airank_scan_runs_created (tenant_id, created_at),
  CONSTRAINT fk_airank_scan_runs_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_scan_tasks (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  run_id VARCHAR(64) NOT NULL,
  question_id VARCHAR(64) NOT NULL,
  provider VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'queued',
  attempt_count INT NOT NULL DEFAULT 0,
  scheduled_at DATETIME(3) NULL,
  started_at DATETIME(3) NULL,
  finished_at DATETIME(3) NULL,
  error_code VARCHAR(128) NULL,
  error_message TEXT NULL,
  request_json JSON NULL,
  response_meta_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_airank_scan_tasks_once (tenant_id, run_id, question_id, provider),
  KEY idx_airank_scan_tasks_worker (status, scheduled_at, updated_at),
  KEY idx_airank_scan_tasks_project (tenant_id, project_id, status, updated_at),
  CONSTRAINT fk_airank_scan_tasks_run FOREIGN KEY (run_id) REFERENCES airank_scan_runs (id),
  CONSTRAINT fk_airank_scan_tasks_question FOREIGN KEY (question_id) REFERENCES airank_buyer_questions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_answer_snapshots (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  run_id VARCHAR(64) NOT NULL,
  task_id VARCHAR(64) NULL,
  question_id VARCHAR(64) NOT NULL,
  provider VARCHAR(64) NOT NULL,
  answer_text MEDIUMTEXT NOT NULL,
  brand_mentioned TINYINT(1) NOT NULL DEFAULT 0,
  brand_rank INT NULL,
  competitor_mentions_json JSON NULL,
  sentiment VARCHAR(64) NULL,
  confidence DECIMAL(5,4) NULL,
  raw_response_ref_id VARCHAR(64) NULL,
  external_trace_id VARCHAR(128) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_airank_snapshots_run_question (tenant_id, project_id, run_id, question_id),
  KEY idx_airank_snapshots_brand_rank (tenant_id, project_id, brand_mentioned, brand_rank),
  CONSTRAINT fk_airank_snapshots_run FOREIGN KEY (run_id) REFERENCES airank_scan_runs (id),
  CONSTRAINT fk_airank_snapshots_question FOREIGN KEY (question_id) REFERENCES airank_buyer_questions (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_source_citations (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  snapshot_id VARCHAR(64) NOT NULL,
  citation_order INT NOT NULL DEFAULT 0,
  title VARCHAR(512) NULL,
  url VARCHAR(2048) NULL,
  host VARCHAR(255) NULL,
  source_type VARCHAR(64) NOT NULL DEFAULT 'web',
  cited_text TEXT NULL,
  relevance_score DECIMAL(6,4) NULL,
  capture_ref_id VARCHAR(64) NULL,
  metadata_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_airank_citations_snapshot (tenant_id, snapshot_id, citation_order),
  KEY idx_airank_citations_host (tenant_id, project_id, host),
  CONSTRAINT fk_airank_citations_snapshot FOREIGN KEY (snapshot_id) REFERENCES airank_answer_snapshots (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_fact_atoms (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  fact_type VARCHAR(64) NOT NULL DEFAULT 'brand_claim' COMMENT '事实类型：brand_identity/product_service/customer_case/industry_solution/qualification/pricing/faq/competitor_diff/channel',
  title VARCHAR(255) NOT NULL,
  fact_text TEXT NOT NULL,
  source_type VARCHAR(64) NULL COMMENT '原始来源类型：website/ppt/case/whitepaper/sales_qa/interview/manual',
  source_excerpt TEXT NULL COMMENT '来源原文片段',
  trust_level VARCHAR(8) NOT NULL DEFAULT 'C' COMMENT '可信等级：A(official)/B(confirmed)/C(pending)/D(restricted)',
  disclosure VARCHAR(32) NOT NULL DEFAULT 'pending_approval' COMMENT '可公开程度：public/redacted/internal/forbidden/pending_approval',
  status VARCHAR(32) NOT NULL DEFAULT 'draft' COMMENT 'draft/confirmed/rejected/stale',
  ai_confidence DECIMAL(5,4) NULL COMMENT 'AI 自动提取时的置信度，仅供参考',
  applicable_question_ids JSON NULL COMMENT '适用的买家问题 ID 列表',
  applicable_asset_types JSON NULL COMMENT '适用的内容资产类型列表',
  risk_note TEXT NULL COMMENT '风险提示：涉及客户案例、竞品对比、价格承诺等需人工确认',
  owner_user_id VARCHAR(64) NULL,
  reviewed_by VARCHAR(64) NULL COMMENT '人工确认人',
  reviewed_at DATETIME(3) NULL COMMENT '确认时间',
  metadata_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY idx_airank_fact_atoms_project_status (tenant_id, project_id, status, updated_at),
  KEY idx_airank_fact_atoms_trust (tenant_id, project_id, trust_level, disclosure),
  KEY idx_airank_fact_atoms_type (tenant_id, project_id, fact_type),
  CONSTRAINT fk_airank_fact_atoms_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_fact_sources (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  fact_atom_id VARCHAR(64) NOT NULL,
  citation_id VARCHAR(64) NULL,
  object_ref_id VARCHAR(64) NULL,
  source_url VARCHAR(2048) NULL,
  source_title VARCHAR(512) NULL,
  support_type VARCHAR(64) NOT NULL DEFAULT 'supports',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_airank_fact_sources_fact (tenant_id, fact_atom_id),
  CONSTRAINT fk_airank_fact_sources_fact FOREIGN KEY (fact_atom_id) REFERENCES airank_fact_atoms (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_content_gaps (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  run_id VARCHAR(64) NULL,
  gap_type VARCHAR(64) NOT NULL DEFAULT 'evidence_gap',
  severity VARCHAR(32) NOT NULL DEFAULT 'medium',
  title VARCHAR(255) NOT NULL,
  description TEXT NULL,
  related_question_ids JSON NULL,
  related_competitor_ids JSON NULL,
  suggested_asset_type VARCHAR(64) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'open',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY idx_airank_content_gaps_project_status (tenant_id, project_id, status, severity),
  CONSTRAINT fk_airank_content_gaps_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_content_assets (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  gap_id VARCHAR(64) NULL,
  asset_type VARCHAR(64) NOT NULL,
  title VARCHAR(255) NOT NULL,
  body_md MEDIUMTEXT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'draft',
  fact_atom_ids JSON NULL,
  target_url VARCHAR(2048) NULL,
  reviewed_by VARCHAR(64) NULL,
  reviewed_at DATETIME(3) NULL,
  metadata_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY idx_airank_content_assets_project_status (tenant_id, project_id, status, updated_at),
  KEY idx_airank_content_assets_type (tenant_id, project_id, asset_type),
  CONSTRAINT fk_airank_content_assets_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_publish_packages (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  asset_id VARCHAR(64) NULL,
  package_type VARCHAR(64) NOT NULL DEFAULT 'content_asset',
  channel VARCHAR(64) NOT NULL DEFAULT 'website' COMMENT '发布渠道：website/wechat_mp/zhihu/xiaohongshu/video_account/baidu/toutiao/industry_media',
  status VARCHAR(32) NOT NULL DEFAULT 'draft' COMMENT 'draft/packaged/published/crawling/crawled/indexed/pending_retest/retested/failed',
  package_ref_id VARCHAR(64) NULL,
  platform_draft_id VARCHAR(255) NULL COMMENT '目标平台的草稿 ID',
  published_url VARCHAR(2048) NULL,
  published_at DATETIME(3) NULL,
  crawled_at DATETIME(3) NULL COMMENT '被搜索引擎或 AI 平台抓取的时间',
  indexed_at DATETIME(3) NULL,
  retest_due_at DATETIME(3) NULL,
  platform_meta_json JSON NULL COMMENT '平台特有元数据（标签、分类、封面等）',
  metadata_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY idx_airank_publish_packages_status (tenant_id, project_id, status, updated_at),
  KEY idx_airank_publish_packages_channel (tenant_id, project_id, channel, status),
  KEY idx_airank_publish_packages_retest (status, retest_due_at),
  CONSTRAINT fk_airank_publish_packages_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_retest_runs (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  baseline_run_id VARCHAR(64) NULL,
  compare_run_id VARCHAR(64) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'queued',
  summary_json JSON NULL,
  started_at DATETIME(3) NULL,
  finished_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY idx_airank_retest_runs_project_status (tenant_id, project_id, status, created_at),
  CONSTRAINT fk_airank_retest_runs_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_reports (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NOT NULL,
  report_type VARCHAR(64) NOT NULL DEFAULT 'executive',
  title VARCHAR(255) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'draft',
  run_id VARCHAR(64) NULL,
  retest_run_id VARCHAR(64) NULL,
  report_ref_id VARCHAR(64) NULL,
  metrics_json JSON NULL,
  generated_by VARCHAR(64) NULL,
  generated_at DATETIME(3) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  deleted_at DATETIME(3) NULL,
  PRIMARY KEY (id),
  KEY idx_airank_reports_project_status (tenant_id, project_id, status, updated_at),
  KEY idx_airank_reports_type (tenant_id, project_id, report_type, generated_at),
  CONSTRAINT fk_airank_reports_project FOREIGN KEY (project_id) REFERENCES airank_projects (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_object_refs (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NULL,
  object_type VARCHAR(64) NOT NULL,
  object_uri VARCHAR(2048) NOT NULL,
  content_type VARCHAR(128) NULL,
  byte_size BIGINT NULL,
  sha256 VARCHAR(128) NULL,
  metadata_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_airank_object_refs_project (tenant_id, project_id, object_type, created_at),
  KEY idx_airank_object_refs_sha (sha256)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_async_jobs (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NULL,
  job_type VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'queued',
  priority INT NOT NULL DEFAULT 100,
  scheduled_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  locked_by VARCHAR(128) NULL,
  locked_at DATETIME(3) NULL,
  heartbeat_at DATETIME(3) NULL COMMENT 'worker 最近一次心跳时间，用于检测 worker 崩溃',
  timeout_seconds INT NOT NULL DEFAULT 300 COMMENT '任务超时秒数，超时后可被其他 worker 接管',
  attempt_count INT NOT NULL DEFAULT 0,
  max_attempts INT NOT NULL DEFAULT 3,
  payload_json JSON NULL,
  result_json JSON NULL,
  error_code VARCHAR(128) NULL,
  error_message TEXT NULL,
  started_at DATETIME(3) NULL COMMENT '任务实际开始执行时间',
  finished_at DATETIME(3) NULL COMMENT '任务完成或失败时间',
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_airank_async_jobs_claim (status, scheduled_at, priority),
  KEY idx_airank_async_jobs_heartbeat (status, heartbeat_at) COMMENT '用于守护线程回收超时任务',
  KEY idx_airank_async_jobs_project (tenant_id, project_id, job_type, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_outbox_events (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NULL,
  event_type VARCHAR(128) NOT NULL,
  aggregate_type VARCHAR(128) NOT NULL,
  aggregate_id VARCHAR(64) NOT NULL,
  trace_id VARCHAR(128) NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT 'pending/published/failed/canceled',
  available_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  published_at DATETIME(3) NULL,
  attempt_count INT NOT NULL DEFAULT 0,
  payload_json JSON NULL,
  error_code VARCHAR(128) NULL,
  error_message TEXT NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_airank_outbox_events_publish (status, available_at, attempt_count),
  KEY idx_airank_outbox_events_aggregate (tenant_id, aggregate_type, aggregate_id),
  KEY idx_airank_outbox_events_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_integration_capabilities (
  id VARCHAR(64) NOT NULL,
  capability VARCHAR(128) NOT NULL,
  source_system VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  required_for_mvp TINYINT(1) NOT NULL DEFAULT 0,
  endpoint VARCHAR(512) NULL,
  checked_at DATETIME(3) NOT NULL,
  last_success_at DATETIME(3) NULL,
  blocked_reason TEXT NULL,
  fallback VARCHAR(255) NULL,
  metadata_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  UNIQUE KEY uk_airank_capabilities (capability, source_system),
  KEY idx_airank_capabilities_status (status, checked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

CREATE TABLE IF NOT EXISTS airank_audit_events (
  id VARCHAR(64) NOT NULL,
  tenant_id VARCHAR(64) NOT NULL,
  project_id VARCHAR(64) NULL,
  actor_user_id VARCHAR(64) NULL,
  event_type VARCHAR(128) NOT NULL,
  entity_type VARCHAR(128) NULL,
  entity_id VARCHAR(64) NULL,
  trace_id VARCHAR(128) NULL,
  payload_json JSON NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  PRIMARY KEY (id),
  KEY idx_airank_audit_events_project (tenant_id, project_id, created_at),
  KEY idx_airank_audit_events_entity (tenant_id, entity_type, entity_id),
  KEY idx_airank_audit_events_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

INSERT INTO airank_integration_capabilities (
  id, capability, source_system, status, required_for_mvp, endpoint, checked_at, fallback, metadata_json
) VALUES
  ('cap_yudao_auth', 'auth', 'yudao', 'ready', 1, '/admin-api/system/auth/get-permission-info', CURRENT_TIMESTAMP(3), NULL, JSON_OBJECT('owner', 'apps/api')),
  ('cap_yudao_model_resolve', 'model_resolve', 'yudao', 'partial', 0, '/admin-api/ai/model/resolve', CURRENT_TIMESTAMP(3), 'env model route', JSON_OBJECT('owner', 'packages/xinghe-adapter')),
  ('cap_xinghe_crawler_gateway', 'crawler_gateway', 'xingheai2026v2', 'partial', 0, '/api/crawler-gateway/runtime-status', CURRENT_TIMESTAMP(3), 'packages/crawler-lite', JSON_OBJECT('owner', 'packages/xinghe-adapter')),
  ('cap_xinghe_kb_service', 'kb_service', 'xingheai2026v2', 'partial', 0, '/internal/kb/store-topology', CURRENT_TIMESTAMP(3), 'packages/kb-lite', JSON_OBJECT('owner', 'packages/xinghe-adapter')),
  ('cap_xinghe_hermes', 'hermes', 'xingheai2026v2', 'partial', 0, NULL, CURRENT_TIMESTAMP(3), 'apps/worker scheduled jobs', JSON_OBJECT('owner', 'packages/xinghe-adapter'))
ON DUPLICATE KEY UPDATE
  status = VALUES(status),
  checked_at = VALUES(checked_at),
  fallback = VALUES(fallback),
  metadata_json = VALUES(metadata_json);
