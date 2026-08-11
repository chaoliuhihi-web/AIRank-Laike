import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const errors = [];
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const sitemap = read('sitemap.xml');
const urls = [...sitemap.matchAll(/<loc>(https:\/\/airank\.net\.cn([^<]*))<\/loc>/g)];
const seen = new Set();

for (const [, absolute, route] of urls) {
  if (seen.has(absolute)) errors.push(`duplicate sitemap URL: ${absolute}`);
  seen.add(absolute);
  const local = route === '/' ? 'index.html' : path.join(route.slice(1), 'index.html');
  if (!fs.existsSync(path.join(root, local))) {
    errors.push(`sitemap route has no static page: ${route}`);
    continue;
  }
  const html = read(local);
  if (!html.includes(`href="${absolute}" rel="canonical"`)) errors.push(`canonical mismatch: ${route}`);
  if (/name="robots"[^>]+noindex/i.test(html)) errors.push(`sitemap contains noindex page: ${route}`);
}

if (urls.length < 42) errors.push(`sitemap has only ${urls.length} URLs; expected public pages, 25 articles and 7 research pages`);

const robots = read('robots.txt');
for (const token of ['OAI-SearchBot','GPTBot','ChatGPT-User','Googlebot','Baiduspider','Sitemap: https://airank.net.cn/sitemap.xml']) {
  if (!robots.includes(token)) errors.push(`robots.txt missing: ${token}`);
}

const nginx = read('nginx.conf.example');
for (const token of ['server_name www.airank.net.cn','return 301 https://airank.net.cn$request_uri','\\.html$','/home/www1/airank.net.cn/current','feed\\.xml','llms\\.txt']) {
  if (!nginx.includes(token)) errors.push(`nginx canonical or discovery rule missing: ${token}`);
}

const redirectFiles = [['vercel.json', read('vercel.json')], ['netlify.toml', read('netlify.toml')]];
for (const [file, content] of redirectFiles) {
  for (const route of ['index','product','solutions','cases','resources','pricing','diagnosis','about','terms','privacy','login','thank-you']) {
    if (!content.includes(`/${route}.html`)) errors.push(`${file} missing redirect for /${route}.html`);
  }
}

const keyFiles = fs.readdirSync(root).filter((file) => /^[a-f0-9]{32}\.txt$/.test(file));
if (keyFiles.length !== 1) errors.push(`expected exactly one IndexNow key file, found ${keyFiles.length}`);
else if (read(keyFiles[0]).trim() !== keyFiles[0].replace('.txt','')) errors.push('IndexNow key file content does not match filename');

if (errors.length) {
  console.error(errors.map((error) => `ERROR: ${error}`).join('\n'));
  process.exit(1);
}
console.log(`OK: ${urls.length} canonical sitemap URLs, crawler policy, redirect rules and IndexNow key verified.`);
