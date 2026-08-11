import fs from 'node:fs';
import path from 'node:path';

const root = process.cwd();
const routes = ['index','product','solutions','cases','resources','pricing','diagnosis','about','terms','privacy'];
const files = new Set(['index.html']);
for (const route of routes.filter((route) => route !== 'index')) {
  files.add(`${route}.html`);
  files.add(path.join(route, 'index.html'));
}

const organizationId = 'https://airank.net.cn/#organization';
const sameAs = [
  'https://github.com/chaoliuhihi-web/AIRank-Laike',
  'https://gitee.com/xinghetech/AIRank-Laike',
];
let updated = 0;

for (const relative of files) {
  const file = path.join(root, relative);
  if (!fs.existsSync(file)) continue;
  let html = fs.readFileSync(file, 'utf8');
  let changed = false;
  html = html.replace(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g, (block, source) => {
    let graph;
    try { graph = JSON.parse(source); } catch { return block; }
    const nodes = Array.isArray(graph) ? graph : [graph];
    const organization = nodes.find((node) => node?.['@type'] === 'Organization');
    if (!organization) return block;

    organization['@id'] = organizationId;
    organization.name = 'AIRank 来客';
    organization.legalName = '北京智界问道科技有限公司';
    organization.url = 'https://airank.net.cn/';
    organization.sameAs = sameAs;
    for (const node of nodes) {
      if (node?.['@type'] === 'WebSite') node.publisher = { '@id': organizationId };
      if (node?.['@type'] === 'SoftwareApplication') node.provider = { '@id': organizationId };
    }
    changed = true;
    return `<script type="application/ld+json">${JSON.stringify(graph)}</script>`;
  });
  if (changed) {
    fs.writeFileSync(file, html);
    updated += 1;
  }
}

console.log(`Enhanced AIRank entity schema on ${updated} public page files.`);
