// Build-only SVG rendering: no browser scripts or Mermaid runtime are published.
import { build } from 'esbuild';
import { chromium } from 'playwright';
import { existsSync, readFileSync, writeFileSync, mkdirSync, readdirSync, unlinkSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export async function renderSources(diagrams, inspect) {
  const script = await build({ entryPoints: [fileURLToPath(new URL('../frontend/mermaid-renderer.js', import.meta.url))], bundle: true, write: false, format: 'iife', platform: 'browser', minify: true, legalComments: 'none' });
  const browser = await chromium.launch({ headless: true });
  const images = {};
  try {
    for (const [identity, source] of Object.entries(diagrams)) {
      if (!/^[a-f0-9]{64}$/.test(identity)) throw Error('Invalid diagram identifier');
      const context = await browser.newContext({ serviceWorkers: 'block', acceptDownloads: false });
      await context.route('**/*', route => route.abort());
      const page = await context.newPage();
      const timeout = setTimeout(() => { context.close().catch(() => {}); }, 15000);
      try {
        await page.setContent('<!doctype html><html><head></head><body></body></html>');
        await page.addScriptTag({ content: script.outputFiles[0].text });
        images[identity] = await page.evaluate(async ([source, identity]) => window.JoongiDiagram.renderDiagram(source, identity), [source, identity]);
        if (inspect) await inspect(page, images[identity]);
      } finally { clearTimeout(timeout); await context.close(); }
    }
  } finally { await browser.close(); }
  return images;
}

function pages(directory) {
  return readdirSync(directory, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? pages(join(directory, entry.name)) : entry.name.endsWith('.html') ? [join(directory, entry.name)] : []);
}

export async function renderSite(directory) {
  directory = resolve(directory);
  const manifest = join(directory, 'mermaid-diagrams.json');
  if (!existsSync(manifest)) return 0;
  const diagrams = JSON.parse(readFileSync(manifest, 'utf8'));
  if (Object.keys(diagrams).length > 128) throw Error('Too many diagrams in one build');
  const images = await renderSources(diagrams);
  mkdirSync(join(directory, 'diagrams'), { recursive: true });
  for (const [identity, svg] of Object.entries(images)) writeFileSync(join(directory, 'diagrams', identity + '.svg'), svg);
  for (const page of pages(join(directory, 'read'))) {
    const html = readFileSync(page, 'utf8').replace(/<p data-mermaid-slot="([a-f0-9]{64})" data-mermaid-src="([^"]+)">[^<]*<\/p>/g, (_, identity, src) => {
      if (!Object.hasOwn(images, identity)) throw Error('Unrendered diagram');
      return `<img src="${src}" alt="Mermaid 도표" loading="lazy">`;
    });
    writeFileSync(page, html);
  }
  unlinkSync(manifest);
  return Object.keys(images).length;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const directory = process.argv[2];
  if (!directory) throw Error('Usage: node scripts/render_mermaid.mjs OUTPUT_DIRECTORY');
  console.log('Rendered safe static Mermaid images:', await renderSite(directory));
}
