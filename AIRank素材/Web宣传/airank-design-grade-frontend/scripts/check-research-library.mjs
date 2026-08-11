import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const hub = fs.readFileSync(path.join(root, 'resources', 'index.html'), 'utf8');
const sitemap = fs.readFileSync(path.join(root, 'sitemap.xml'), 'utf8');
const cards = [...hub.matchAll(/<a class="research-library-card"[^>]+href="(\/resources\/([^/]+)\/)"/g)];
const errors = [];
const slugs = new Set();
const titles = new Set();

if (cards.length < 25) errors.push(`research library has ${cards.length} cards; expected at least 25`);

for (const [, route, slug] of cards) {
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
  const required = [
    [`href="${canonical}" rel="canonical"`, 'canonical'],
    ['"@type":"BlogPosting"', 'BlogPosting schema'],
    ['"@type":"BreadcrumbList"', 'BreadcrumbList schema'],
    ['"url":"https://airank.net.cn/research/methodology/"', 'author URL'],
    [`https://airank.net.cn/assets/img/research/${slug}-cover.webp`, 'unique article image'],
    ['class="research-transparency"', 'research transparency'],
    ['class="research-related"', 'related research section'],
  ];
  for (const [needle, label] of required) if (!html.includes(needle)) errors.push(`missing ${label}: ${route}`);
  const related = html.match(/class="research-related__grid">([\s\S]*?)<\/div>/)?.[1] ?? '';
  if ((related.match(/<a /g) || []).length < 3) errors.push(`fewer than 3 related articles: ${route}`);
  if (!sitemap.includes(`<loc>${canonical}</loc>`)) errors.push(`missing sitemap entry: ${route}`);
  if (!fs.existsSync(path.join(root, 'assets', 'img', 'research', `${slug}-cover.webp`))) errors.push(`missing cover file: ${slug}`);
}

const topics = ['ai-observability','citation-evidence','enterprise-facts','ai-extractability','model-governance','enterprise-geo'];
for (const topic of topics) {
  const route = `/research/${topic}/`;
  const file = path.join(root, 'research', topic, 'index.html');
  if (!fs.existsSync(file)) errors.push(`missing topic hub: ${route}`);
  else {
    const html = fs.readFileSync(file, 'utf8');
    if (!html.includes('"@type":"CollectionPage"')) errors.push(`missing CollectionPage schema: ${route}`);
    if (!html.includes('"@type":"BreadcrumbList"')) errors.push(`missing BreadcrumbList schema: ${route}`);
  }
  if (!sitemap.includes(`<loc>https://airank.net.cn${route}</loc>`)) errors.push(`missing topic sitemap entry: ${route}`);
}

for (const file of ['research/methodology/index.html','feed.xml','llms.txt']) {
  if (!fs.existsSync(path.join(root, file))) errors.push(`missing research support file: ${file}`);
}

if (errors.length) {
  console.error(errors.map((error) => `ERROR: ${error}`).join('\n'));
  process.exit(1);
}
console.log(`OK: ${cards.length} articles, 6 topic hubs, authorship, evidence metadata, related paths and research feeds verified.`);
