import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const hubPath = path.join(root, 'resources', 'index.html');
const sitemapPath = path.join(root, 'sitemap.xml');
const hub = fs.readFileSync(hubPath, 'utf8');
const sitemap = fs.readFileSync(sitemapPath, 'utf8');
const hrefs = [...hub.matchAll(/<a class="research-library-card"[^>]+href="(\/resources\/([^/]+)\/)"/g)];
const errors = [];

if (hrefs.length < 25) {
  errors.push(`research library has ${hrefs.length} cards; expected at least 25`);
}

const slugs = new Set();
const titles = new Set();
for (const [, route, slug] of hrefs) {
  if (slugs.has(slug)) errors.push(`duplicate resource slug: ${slug}`);
  slugs.add(slug);

  const articlePath = path.join(root, route, 'index.html');
  if (!fs.existsSync(articlePath)) {
    errors.push(`missing article route: ${route}`);
    continue;
  }

  const html = fs.readFileSync(articlePath, 'utf8');
  const title = html.match(/<h1>(.*?)<\/h1>/)?.[1];
  if (!title) errors.push(`missing h1: ${route}`);
  else if (titles.has(title)) errors.push(`duplicate article title: ${title}`);
  else titles.add(title);

  const prose = html.match(/<main[^>]*>([\s\S]*?)<\/main>/)?.[1]
    ?.replace(/<[^>]+>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim() ?? '';
  if (prose.length < 1100) errors.push(`article body is too short (${prose.length} chars): ${route}`);

  const canonical = `https://airank.net.cn${route}`;
  if (!html.includes(`href="${canonical}" rel="canonical"`)) errors.push(`missing canonical: ${route}`);
  if (!html.includes('"@type":"Article"')) errors.push(`missing Article schema: ${route}`);
  if (!sitemap.includes(`<loc>${canonical}</loc>`)) errors.push(`missing sitemap entry: ${route}`);
}

if (errors.length) {
  console.error(errors.map((error) => `ERROR: ${error}`).join('\n'));
  process.exit(1);
}

console.log(`OK: ${hrefs.length} deep research articles, routes, canonical URLs, schemas and sitemap entries verified.`);
