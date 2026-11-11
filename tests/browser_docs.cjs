'use strict';
const assert = require('node:assert/strict');
const { spawnSync } = require('node:child_process');
const { mkdtempSync, readFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, resolve, sep } = require('node:path');
const { chromium } = require('playwright');

const directory = mkdtempSync(join(tmpdir(), 'joongi-docs-browser-'));
let browser;
async function main() {
  const output = join(directory, 'pages');
  const build = spawnSync(process.env.PYTHON || 'python3', ['-B', 'scripts/build_pages.py', '--out', output, '--base-url', 'https://pages.example/joongi-skills'], { cwd: resolve(__dirname, '..'), encoding: 'utf8' });
  assert.equal(build.status, 0, build.stderr);
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ javaScriptEnabled: false });
  await context.route('https://pages.example/joongi-skills/**', route => {
    const name = decodeURIComponent(new URL(route.request().url()).pathname.slice('/joongi-skills/'.length)) || 'index.html';
    const file = resolve(output, name);
    if (!file.startsWith(resolve(output) + sep)) return route.fulfill({ status: 404, body: '' });
    try {
      const type = file.endsWith('.css') ? 'text/css' : file.endsWith('.html') ? 'text/html' : 'application/octet-stream';
      return route.fulfill({ contentType: type, body: readFileSync(file) });
    } catch { return route.fulfill({ status: 404, body: '' }); }
  });
  const page = await context.newPage();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('https://pages.example/joongi-skills/read/docs/00-index.html');
  await page.getByRole('heading', { name: '문서 안내', exact: true }).waitFor();
  const menu = page.getByRole('navigation', { name: '문서 탐색', exact: true });
  await menu.getByText('설치와 업데이트', { exact: true }).click();
  await menu.getByRole('link', { name: '설치·업데이트·제거', exact: true }).click();
  assert(page.url().endsWith('/read/docs/installation/00-index.html'));
  await page.locator('.page-toc > summary').click();
  await page.getByRole('navigation', { name: '본문 목차' }).getByRole('link', { name: 'Windows', exact: true }).click();
  assert(page.url().endsWith('#section-windows'));
  await page.locator('#section-windows').waitFor();
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('https://pages.example/joongi-skills/read/docs/00-index.html');
    assert.equal(await page.locator('html').evaluate(el => el.scrollWidth > innerWidth), false, 'Document overflow at ' + width);
    if (width <= 900) {
      await page.locator('.document-menu > summary').click();
      await menu.getByRole('link', { name: '문서 안내', exact: true }).waitFor();
    }
  }
  await page.goto('https://pages.example/joongi-skills/');
  await page.getByRole('navigation', { name: '주 메뉴' }).getByRole('link', { name: '문서', exact: true }).click();
  await page.getByRole('heading', { name: '문서 안내', exact: true }).waitFor();
  console.log('Static documentation: no-JS navigation, Korean anchors, mobile menu, widths 320–1440 and installation-page entry passed.');
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  rmSync(directory, { recursive: true, force: true });
});
