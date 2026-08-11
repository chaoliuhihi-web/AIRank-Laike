import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const root = process.cwd();
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'assets', 'data', 'research-library.json'), 'utf8'));
const outDir = path.join(root, 'assets', 'img', 'research');
fs.mkdirSync(outDir, { recursive: true });

const categories = {
  observability: ['多平台观测', 'assets/img/visuals/airank-trusted-answer-glass-v6.webp', '#1367ff'],
  citation: ['引用证据', 'assets/img/visuals/airank-product-evidence-glass-v6.webp', '#0b9da8'],
  assets: ['事实资产', 'assets/img/visuals/airank-knowledge-evidence-v7.webp', '#3d62c8'],
  technical: ['页面工程', 'assets/img/visuals/airank-growth-engine-v4.webp', '#6579ae'],
  operations: ['模型治理', 'assets/img/visuals/airank-product-glass-v5.webp', '#77664d'],
  business: ['企业落地', 'assets/img/visuals/airank-solutions-glass-v6.webp', '#263a61'],
};
const font = '/System/Library/Fonts/Hiragino Sans GB.ttc';

function generate(output, title, label, source, accent, index) {
  const base = path.resolve(root, source);
  execFileSync('magick', [
    '-size', '1200x675', 'xc:#eef7ff',
    '(', base, '-resize', '690x675^', '-gravity', 'center', '-extent', '690x675', '-modulate', '102,78,100', ')', '-gravity', 'east', '-composite',
    '-fill', 'rgba(238,247,255,0.90)', '-draw', 'rectangle 0,0 670,675',
    '-fill', accent, '-draw', 'rectangle 0,0 18,675',
    '-font', font, '-fill', accent, '-pointsize', '28', '-gravity', 'northwest', '-annotate', '+72+64', `AIRank RESEARCH · ${label}`,
    '-font', font, '-fill', '#071a39', '-pointsize', '52', '-gravity', 'northwest', '-size', '520x350', `caption:${title}`,
    '-geometry', '+72+150', '-composite',
    '-font', font, '-fill', '#5a7392', '-pointsize', '24', '-gravity', 'southwest', '-annotate', '+72+62', '证据优先 · 方法透明 · 持续复测',
    '-font', font, '-fill', 'rgba(23,107,255,0.20)', '-pointsize', '92', '-gravity', 'southeast', '-annotate', '+58+48', String(index).padStart(2, '0'),
    '-quality', '86', output,
  ]);
}

for (const [index, article] of manifest.entries()) {
  const [label, source, accent] = categories[article.category];
  generate(path.join(outDir, `${article.slug}-cover.webp`), article.title, label, source, accent, index + 1);
}
for (const [category, [label, source, accent]] of Object.entries(categories)) {
  const topicSlug = { observability: 'ai-observability', citation: 'citation-evidence', assets: 'enterprise-facts', technical: 'ai-extractability', operations: 'model-governance', business: 'enterprise-geo' }[category];
  generate(path.join(outDir, `topic-${topicSlug}.webp`), `${label}研究专题`, label, source, accent, Number.parseInt(Object.keys(categories).indexOf(category), 10) + 1);
}
console.log(`Generated ${manifest.length + Object.keys(categories).length} research cover images.`);
