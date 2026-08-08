const DEFAULT_ALLOWED = [
  'https://airank.net.cn',
  'https://www.airank.net.cn',
  'http://localhost:8080',
  'http://127.0.0.1:8080'
];
const DEFAULT_TO = 'airank@xinghetech.cn';
const DEFAULT_BODY_LIMIT = 16 * 1024;
const DEFAULT_RATE_WINDOW_MS = 10 * 60 * 1000;
const DEFAULT_RATE_MAX = 5;
const rateBuckets = globalThis.__airankLeadRateBuckets || new Map();
globalThis.__airankLeadRateBuckets = rateBuckets;

function jsonResponse(status, body, extraHeaders = {}){
  return {
    status,
    headers: {
      'Content-Type':'application/json; charset=utf-8',
      'X-Content-Type-Options':'nosniff',
      'Cache-Control':'no-store',
      ...extraHeaders
    },
    body: status === 204 ? '' : JSON.stringify(body)
  };
}

function allowedOrigins(){
  return (process.env.ALLOWED_ORIGINS || DEFAULT_ALLOWED.join(','))
    .split(',')
    .map(value => value.trim())
    .filter(Boolean);
}

function corsHeaders(origin){
  const headers = {
    'Access-Control-Allow-Methods':'POST, OPTIONS',
    'Access-Control-Allow-Headers':'Content-Type'
  };
  if (origin && allowedOrigins().includes(origin)) headers['Access-Control-Allow-Origin'] = origin;
  return headers;
}

function bodySize(body){
  if (body == null) return 0;
  if (Buffer.isBuffer(body)) return body.length;
  if (typeof body === 'string') return Buffer.byteLength(body);
  return Buffer.byteLength(JSON.stringify(body));
}

function parseBody(body){
  if (!body) return {};
  if (typeof body === 'string') return JSON.parse(body || '{}');
  if (Buffer.isBuffer(body)) return JSON.parse(body.toString('utf8') || '{}');
  return body;
}

function normalizeWebsite(value){
  const raw = String(value || '').trim();
  if (!raw) return '';
  const normalized = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
  try {
    const url = new URL(normalized);
    if (!['http:','https:'].includes(url.protocol) || !url.hostname) return '';
    return url.toString();
  } catch {
    return '';
  }
}

function cleanString(value, maxLength){
  return String(value || '').trim().slice(0, maxLength);
}

function sanitize(input){
  const source = input && typeof input === 'object' ? input : {};
  return {
    name:cleanString(source.name, 80),
    phone:cleanString(source.phone, 30),
    email:cleanString(source.email, 160),
    company:cleanString(source.company, 160),
    website:normalizeWebsite(source.website),
    intent:cleanString(source.intent, 80),
    page:cleanString(source.page, 240),
    pageTitle:cleanString(source.pageTitle, 240),
    viewport:cleanString(source.viewport, 40),
    submittedAt:cleanString(source.submittedAt, 80) || new Date().toISOString(),
    consent:Boolean(source.consent),
    attribution:source.attribution && typeof source.attribution === 'object' ? {
      utm_source:cleanString(source.attribution.utm_source, 120),
      utm_medium:cleanString(source.attribution.utm_medium, 120),
      utm_campaign:cleanString(source.attribution.utm_campaign, 160),
      referrer:cleanString(source.attribution.referrer, 500)
    } : {},
    airank_company_url:cleanString(source.airank_company_url, 200)
  };
}

function validate(lead, rawInput){
  if (!(lead.phone || lead.email || lead.website)) return '请至少提供官网、手机号或邮箱中的一项';
  if (rawInput.website && !lead.website) return '官网地址格式不正确';
  if (lead.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(lead.email)) return '邮箱格式不正确';
  if (lead.phone && !/^1[3-9]\d{9}$|^400\d{7}$|^[0-9+\-\s]{6,20}$/.test(lead.phone)) return '手机号格式不正确';
  return '';
}

function clientIp(headers = {}){
  const forwarded = headers['x-forwarded-for'] || headers['X-Forwarded-For'] || '';
  return cleanString(String(forwarded).split(',')[0] || headers['x-real-ip'] || headers['client-ip'] || 'unknown', 80);
}

function takeRateLimit(ip){
  const now = Date.now();
  const windowMs = Math.max(1000, Number(process.env.LEAD_RATE_WINDOW_MS || DEFAULT_RATE_WINDOW_MS));
  const max = Math.max(1, Number(process.env.LEAD_RATE_MAX || DEFAULT_RATE_MAX));
  const bucket = rateBuckets.get(ip);
  if (!bucket || bucket.resetAt <= now) {
    rateBuckets.set(ip, { count:1, resetAt:now + windowMs });
    return { allowed:true, remaining:max - 1, resetAt:now + windowMs };
  }
  bucket.count += 1;
  if (rateBuckets.size > 2000) {
    for (const [key, value] of rateBuckets) if (value.resetAt <= now) rateBuckets.delete(key);
  }
  return { allowed:bucket.count <= max, remaining:Math.max(0, max - bucket.count), resetAt:bucket.resetAt };
}

function textPayload(lead){
  return [
    'AIRank 来客官网新线索',
    `意图：${lead.intent || '-'}`,
    `公司：${lead.company || '-'}`,
    `姓名：${lead.name || '-'}`,
    `手机号：${lead.phone || '-'}`,
    `邮箱：${lead.email || '-'}`,
    `官网：${lead.website || '-'}`,
    `页面：${lead.page || '-'}`,
    `来源：${lead.attribution.utm_source || lead.attribution.referrer || '-'}`,
    `提交时间：${lead.submittedAt}`
  ].join('\n');
}

function escapeHtml(value){
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function htmlPayload(lead){
  const rows = [
    ['意图',lead.intent],['公司',lead.company],['姓名',lead.name],['手机号',lead.phone],
    ['邮箱',lead.email],['官网',lead.website],['页面',lead.page],
    ['来源',lead.attribution.utm_source || lead.attribution.referrer],['提交时间',lead.submittedAt]
  ];
  return [
    '<h2>AIRank 来客官网新线索</h2>',
    '<table cellpadding="8" cellspacing="0" style="border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:14px;">',
    ...rows.map(([label,value]) => `<tr><td style="border:1px solid #e5e7eb;background:#f8fafc;font-weight:700;">${escapeHtml(label)}</td><td style="border:1px solid #e5e7eb;">${escapeHtml(value || '-')}</td></tr>`),
    '</table>'
  ].join('');
}

function smtpConfig(){
  const host = process.env.SMTP_HOST;
  const user = process.env.SMTP_USER;
  const pass = process.env.SMTP_PASS;
  if (!host || !user || !pass) return null;
  const port = Number(process.env.SMTP_PORT || 465);
  const secure = process.env.SMTP_SECURE ? process.env.SMTP_SECURE === 'true' : port === 465;
  return {
    host, port, secure, auth:{ user, pass },
    connectionTimeout:8000, greetingTimeout:8000, socketTimeout:12000
  };
}

async function sendLeadEmail(lead){
  const to = process.env.LEAD_EMAIL_TO || DEFAULT_TO;
  if (process.env.LEAD_DRY_RUN === '1') return { type:'dry_run_email', to };
  const config = smtpConfig();
  if (!config) throw new Error('SMTP_HOST/SMTP_USER/SMTP_PASS is not configured');
  const nodemailer = require('nodemailer');
  const transporter = nodemailer.createTransport(config);
  await transporter.sendMail({
    from:process.env.SMTP_FROM || config.auth.user,
    to,
    subject:`AIRank 来客官网新线索 - ${lead.company || lead.website || lead.phone || '未命名企业'}`,
    text:textPayload(lead),
    html:htmlPayload(lead)
  });
  return { type:'email', to };
}

async function forwardToWebhook(lead){
  const url = process.env.LEAD_WEBHOOK_URL;
  if (!url) return null;
  const mode = (process.env.LEAD_WEBHOOK_MODE || 'json').toLowerCase();
  const text = textPayload(lead);
  const body = mode === 'feishu'
    ? { msg_type:'text', content:{ text } }
    : mode === 'dingtalk'
      ? { msgtype:'text', text:{ content:text } }
      : { source:'airank-web', lead, text };
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  try {
    const response = await fetch(url, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body), signal:controller.signal
    });
    if (!response.ok) throw new Error(`webhook failed: ${response.status}`);
    return { type:'webhook' };
  } finally {
    clearTimeout(timeout);
  }
}

async function deliverLead(lead){
  const deliveries = [];
  if (smtpConfig() || process.env.LEAD_DRY_RUN === '1') deliveries.push(await sendLeadEmail(lead));
  const webhook = await forwardToWebhook(lead);
  if (webhook) deliveries.push(webhook);
  if (!deliveries.length) throw new Error('No lead delivery channel is configured');
  return deliveries;
}

async function handleLeadRequest({ method, headers = {}, body }){
  const origin = headers.origin || headers.Origin || '';
  const cors = corsHeaders(origin);
  if (method === 'OPTIONS') return jsonResponse(204, {}, cors);
  if (method !== 'POST') return jsonResponse(405, { ok:false, message:'Method not allowed' }, cors);
  if (origin && !allowedOrigins().includes(origin)) return jsonResponse(403, { ok:false, message:'Origin not allowed' }, cors);

  const bodyLimit = Math.max(1024, Number(process.env.LEAD_BODY_LIMIT || DEFAULT_BODY_LIMIT));
  if (bodySize(body) > bodyLimit) return jsonResponse(413, { ok:false, message:'Request body too large' }, cors);

  let rawInput;
  try {
    rawInput = parseBody(body);
  } catch {
    return jsonResponse(400, { ok:false, message:'Invalid JSON body' }, cors);
  }
  const lead = sanitize(rawInput);
  if (lead.airank_company_url) return jsonResponse(200, { ok:true }, cors);

  const rate = takeRateLimit(clientIp(headers));
  const rateHeaders = {
    ...cors,
    'X-RateLimit-Remaining':String(rate.remaining)
  };
  if (!rate.allowed) {
    rateHeaders['Retry-After'] = String(Math.max(1, Math.ceil((rate.resetAt - Date.now()) / 1000)));
    return jsonResponse(429, { ok:false, message:'提交过于频繁，请稍后再试' }, rateHeaders);
  }

  const error = validate(lead, rawInput);
  if (error) return jsonResponse(400, { ok:false, message:error }, rateHeaders);
  try {
    const deliveries = await deliverLead(lead);
    return jsonResponse(200, { ok:true, deliveries }, rateHeaders);
  } catch (error) {
    console.error(error);
    return jsonResponse(500, { ok:false, message:'Lead submit failed' }, rateHeaders);
  }
}

function resetRateLimitForTests(){
  rateBuckets.clear();
}

module.exports = { handleLeadRequest, resetRateLimitForTests };
