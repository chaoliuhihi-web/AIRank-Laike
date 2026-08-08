
import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const pages = fs.readdirSync(root).filter(file => file.endsWith('.html'));
const errors = [];
const warnings = [];

const publicPages = new Set([
  'index.html',
  'product.html',
  'solutions.html',
  'cases.html',
  'resources.html',
  'pricing.html',
  'diagnosis.html',
  'about.html',
  'terms.html',
  'privacy.html',
]);

const forbiddenPublicCopy = [
  [/云学堂|三一重工|迈瑞医疗|CRRC|SANY|HIKVISION|Midea|CATL|Haier/, 'unverified customer brand claim'],
  [/200\+ 服务客户|1000\+ 成功项目|5000\+ 企业|增长312%|\+243%|\+235%|\+192%/, 'unsupported performance claim'],
  [/灰度开放|增加成交周期|透明定价|无隐藏费用|关注二维码（临时）/, 'internal or misleading public copy'],
  [/3 分钟生成报告|3分钟生成/, 'unsupported instant-report promise'],
];

function existsRef(ref) {
  const clean = ref.split('?')[0].split('#')[0];
  if (!clean || /^(https?:|mailto:|tel:|data:)/.test(clean)) return true;
  if (clean.startsWith('/api/')) return true;
  const local = clean.startsWith('/') ? clean.slice(1) : clean;
  if (local === '') return true;
  if (local.endsWith('/')) return fs.existsSync(path.join(root, local, 'index.html'));
  return fs.existsSync(path.join(root, local));
}

for (const page of pages) {
  const html = fs.readFileSync(path.join(root, page), 'utf8');
  const refs = [...html.matchAll(/(?:src|href|action)="([^"#][^"]*)"/g)].map(match => match[1]);

  for (const ref of refs) {
    if (!existsRef(ref)) errors.push(`${page}: missing ${ref}`);
  }

  if (/href="#"/.test(html)) errors.push(`${page}: contains href="#"`);
  if (/example\.com|400-888-8888|智界问道（北京）/.test(html)) errors.push(`${page}: contains old placeholder text`);
  if (!/<link[^>]+rel="canonical"/.test(html)) warnings.push(`${page}: missing canonical`);
  if (!/<meta[^>]+name="description"/.test(html)) warnings.push(`${page}: missing description`);
  if (/assets\/css\/styles\.css/.test(html)) errors.push(`${page}: uses unversioned stylesheet`);
  if (/assets\/js\/main\.js/.test(html)) errors.push(`${page}: uses unversioned main script`);

  if (publicPages.has(page)) {
    for (const [pattern, message] of forbiddenPublicCopy) {
      if (pattern.test(html)) errors.push(`${page}: ${message}`);
    }
  }
}

const must = [
  'robots.txt',
  'sitemap.xml',
  'site.webmanifest',
  'api/leads.js',
  'netlify/functions/leads.js',
  'assets/css/styles.v20260517.css',
  'assets/js/main.v20260517.js',
];

for (const file of must) {
  if (!fs.existsSync(path.join(root, file))) errors.push(`missing ${file}`);
}

const sitemap = fs.readFileSync(path.join(root, 'sitemap.xml'), 'utf8');
for (const internalRoute of ['/pages/', '/design-system/', '/login/', '/thank-you/']) {
  if (sitemap.includes(internalRoute)) errors.push(`sitemap.xml: exposes internal route ${internalRoute}`);
}

if (warnings.length) console.warn(warnings.join('\n'));
if (errors.length) {
  console.error(errors.join('\n'));
  process.exit(1);
}

console.log(`OK: ${pages.length} root html files checked. Public content and static audit passed.`);
