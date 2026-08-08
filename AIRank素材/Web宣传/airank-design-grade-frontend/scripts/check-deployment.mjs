import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const required = [
  'package-lock.json',
  'vercel.json',
  'netlify.toml',
  'api/leads.js',
  'netlify/functions/leads.js',
  'server/lead-core.js'
];
const failures = [];

for (const file of required) {
  if (!fs.existsSync(path.join(root, file))) failures.push(`missing deployment file: ${file}`);
}

const vercel = JSON.parse(fs.readFileSync(path.join(root, 'vercel.json'), 'utf8'));
const globalHeaders = vercel.headers?.find(entry => entry.source === '/(.*)')?.headers || [];
const headerNames = new Set(globalHeaders.map(header => header.key.toLowerCase()));
for (const requiredHeader of ['content-security-policy','strict-transport-security','x-content-type-options']) {
  if (!headerNames.has(requiredHeader)) failures.push(`vercel security header missing: ${requiredHeader}`);
}

const netlify = fs.readFileSync(path.join(root, 'netlify.toml'), 'utf8');
if (!/from\s*=\s*"\/api\/leads"[\s\S]*?to\s*=\s*"\/\.netlify\/functions\/leads"/.test(netlify)) {
  failures.push('netlify /api/leads rewrite is missing');
}
for (const token of ['Content-Security-Policy','Strict-Transport-Security','X-Content-Type-Options']) {
  if (!netlify.includes(token)) failures.push(`netlify security header missing: ${token}`);
}

const trackedSourcePngs = execFileSync('git', ['ls-files','assets/img/visuals/*.png'], { cwd:root, encoding:'utf8' }).trim();
if (trackedSourcePngs) failures.push(`source PNGs must not be deployed:\n${trackedSourcePngs}`);

if (failures.length) {
  console.error(failures.map(item => `- ${item}`).join('\n'));
  process.exit(1);
}
console.log('OK: deployment files, security headers and production asset boundary passed.');
