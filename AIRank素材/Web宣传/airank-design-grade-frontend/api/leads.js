const DEFAULT_ALLOWED = [
  'https://airank.net.cn',
  'https://www.airank.net.cn',
  'http://localhost:8080',
  'http://127.0.0.1:8080'
];
const DEFAULT_TO = 'airank@xinghetech.cn';

function send(res, status, body){
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(status === 204 ? '' : JSON.stringify(body));
}

function parseBody(body){
  if (!body) return {};
  if (typeof body === 'string') return JSON.parse(body || '{}');
  if (Buffer.isBuffer(body)) return JSON.parse(body.toString('utf8') || '{}');
  return body;
}

function normalizeWebsite(value){
  const v = String(value || '').trim();
  if (!v) return '';
  return /^https?:\/\//i.test(v) ? v : `https://${v}`;
}

function sanitize(input){
  const out = {};
  for (const [key, value] of Object.entries(input || {})) {
    if (typeof value === 'string') out[key] = value.trim().slice(0, 1000);
    else if (value && typeof value === 'object') out[key] = value;
    else out[key] = value;
  }
  if (out.website) out.website = normalizeWebsite(out.website);
  if (!out.submittedAt) out.submittedAt = new Date().toISOString();
  return out;
}

function validate(lead){
  const hasContact = Boolean(lead.phone || lead.email || lead.website);
  if (!hasContact) return '请至少提供官网、手机号或邮箱中的一项';
  if (lead.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(lead.email)) return '邮箱格式不正确';
  if (lead.website && !/^https?:\/\//i.test(lead.website)) return '官网地址格式不正确';
  return '';
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
    `来源：${lead.attribution?.utm_source || lead.attribution?.referrer || '-'}`,
    `提交时间：${lead.submittedAt || new Date().toISOString()}`
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
    ['意图', lead.intent],
    ['公司', lead.company],
    ['姓名', lead.name],
    ['手机号', lead.phone],
    ['邮箱', lead.email],
    ['官网', lead.website],
    ['页面', lead.page],
    ['来源', lead.attribution?.utm_source || lead.attribution?.referrer],
    ['提交时间', lead.submittedAt]
  ];
  return [
    '<h2>AIRank 来客官网新线索</h2>',
    '<table cellpadding="8" cellspacing="0" style="border-collapse:collapse;font-family:Arial,Helvetica,sans-serif;font-size:14px;">',
    ...rows.map(([label, value]) => `<tr><td style="border:1px solid #e5e7eb;background:#f8fafc;font-weight:700;">${escapeHtml(label)}</td><td style="border:1px solid #e5e7eb;">${escapeHtml(value || '-')}</td></tr>`),
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
  return { host, port, secure, auth: { user, pass } };
}

async function sendLeadEmail(lead){
  const to = process.env.LEAD_EMAIL_TO || DEFAULT_TO;
  if (process.env.LEAD_DRY_RUN === '1') return { type: 'dry_run_email', to };
  const config = smtpConfig();
  if (!config) throw new Error('SMTP_HOST/SMTP_USER/SMTP_PASS is not configured');
  const nodemailer = require('nodemailer');
  const transporter = nodemailer.createTransport(config);
  await transporter.sendMail({
    from: process.env.SMTP_FROM || config.auth.user,
    to,
    subject: `AIRank 来客官网新线索 - ${lead.company || lead.website || lead.phone || '未命名企业'}`,
    text: textPayload(lead),
    html: htmlPayload(lead)
  });
  return { type: 'email', to };
}

async function forwardToWebhook(lead){
  const url = process.env.LEAD_WEBHOOK_URL;
  if (!url) return null;
  const mode = (process.env.LEAD_WEBHOOK_MODE || 'json').toLowerCase();
  const text = textPayload(lead);
  let body;
  if (mode === 'feishu') body = { msg_type:'text', content:{ text } };
  else if (mode === 'dingtalk') body = { msgtype:'text', text:{ content:text } };
  else body = { source:'airank-web', lead, text };
  const resp = await fetch(url, { method:'POST', headers:{ 'Content-Type':'application/json' }, body: JSON.stringify(body) });
  if (!resp.ok) throw new Error(`webhook failed: ${resp.status}`);
  return { type: 'webhook' };
}

async function deliverLead(lead){
  const deliveries = [];
  const emailConfigured = Boolean(smtpConfig()) || process.env.LEAD_DRY_RUN === '1';
  if (emailConfigured) deliveries.push(await sendLeadEmail(lead));
  const webhookDelivery = await forwardToWebhook(lead);
  if (webhookDelivery) deliveries.push(webhookDelivery);
  if (!deliveries.length) throw new Error('No lead delivery channel is configured');
  return deliveries;
}

module.exports = async function handler(req, res) {
  const allowed = (process.env.ALLOWED_ORIGINS || DEFAULT_ALLOWED.join(',')).split(',').map(s => s.trim()).filter(Boolean);
  const origin = req.headers.origin || '';
  if (allowed.includes(origin)) res.setHeader('Access-Control-Allow-Origin', origin);
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  res.setHeader('X-Content-Type-Options', 'nosniff');
  if (req.method === 'OPTIONS') return send(res, 204, {});
  if (req.method !== 'POST') return send(res, 405, { ok:false, message:'Method not allowed' });
  try {
    const lead = sanitize(parseBody(req.body));
    if (lead.airank_company_url) return send(res, 200, { ok:true });
    const error = validate(lead);
    if (error) return send(res, 400, { ok:false, message:error });
    const deliveries = await deliverLead(lead);
    return send(res, 200, { ok:true, deliveries });
  } catch (error) {
    console.error(error);
    return send(res, 500, { ok:false, message:'Lead submit failed' });
  }
};
