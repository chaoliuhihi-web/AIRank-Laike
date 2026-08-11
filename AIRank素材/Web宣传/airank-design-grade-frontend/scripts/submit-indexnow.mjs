import fs from 'node:fs';

const key = '3fe8059d55375a079a5e2f013a7a3f0e';
const sitemap = fs.readFileSync(new URL('../sitemap.xml', import.meta.url), 'utf8');
const urlList = [...sitemap.matchAll(/<loc>(https:\/\/airank\.net\.cn\/[^<]*)<\/loc>/g)].map((match) => match[1]);
const response = await fetch('https://api.indexnow.org/indexnow', {
  method: 'POST',
  headers: { 'content-type': 'application/json; charset=utf-8' },
  body: JSON.stringify({ host: 'airank.net.cn', key, keyLocation: `https://airank.net.cn/${key}.txt`, urlList }),
});
console.log(`IndexNow submitted ${urlList.length} URLs: HTTP ${response.status}`);
if (![200, 202].includes(response.status)) process.exit(1);
