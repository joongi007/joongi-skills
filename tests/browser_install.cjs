'use strict';
const assert = require('node:assert/strict');
const { readFileSync, mkdirSync } = require('node:fs');
const { resolve, join } = require('node:path');
const { chromium } = require('playwright');
let browser;
async function main() {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] });
  const errors = [];
  await context.route('**/*', async route => {
    const url = new URL(route.request().url());
    const allowed = { 'index.html': 'text/html', 'style.css': 'text/css', 'tokens.css': 'text/css', 'install.js': 'application/javascript' };
    const name = url.pathname.split('/').pop() || 'index.html';
    if (!['pages.example', 'preview.local'].includes(url.hostname) || !Object.hasOwn(allowed, name)) return route.abort();
    await route.fulfill({ contentType: allowed[name], body: readFileSync(resolve(__dirname, '../site', name)) });
  });
  const page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('https://pages.example/joongi-skills/');
  const shell = page.locator('#shell-command');
  const windows = page.locator('#windows-command');
  assert.equal((await shell.innerText()).split('\n').length, 1);
  assert((await shell.innerText()).includes("curl -fsSL 'https://pages.example/joongi-skills/install.sh' | bash -s -- install"));
  assert(!(await shell.innerText()).includes('gh attestation'));
  const panel = page.locator('#panel-shell');
  assert.equal(await panel.locator('details').evaluate(node => node.open), false);
  await page.getByRole('button', { name: 'Bash 간편 설치 명령 복사', exact: true }).click();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), await shell.innerText());
  await panel.locator('summary').focus();
  await panel.locator('summary').press('Enter');
  const verified = page.locator('#shell-verified-command');
  assert((await verified.innerText()).includes('gh attestation verify'));
  assert((await verified.innerText()).includes('--source-digest "$revision"'));
  await page.getByRole('button', { name: 'Bash 서명 확인 설치 명령 복사', exact: true }).click();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), await verified.innerText());
  await page.getByRole('tab', { name: 'macOS · Linux · WSL', exact: true }).focus();
  await page.keyboard.press('ArrowRight');
  assert.equal(await page.getByRole('tab', { name: 'Windows', exact: true }).getAttribute('aria-selected'), 'true');
  assert.equal(await shell.isVisible(), false);
  assert((await windows.innerText()).includes('scriptblock'));
  assert((await windows.innerText()).includes('https://pages.example/joongi-skills/install.ps1'));
  assert((await page.locator('#windows-verified-command').textContent()).includes('Signature verification failed'));
  await page.getByRole('button', { name: 'PowerShell 간편 설치 명령 복사', exact: true }).click();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), await windows.innerText());
  // Returning to a panel retains the explicit verification disclosure state.
  await page.getByRole('tab', { name: 'Windows', exact: true }).press('Home');
  assert.equal(await panel.locator('details').evaluate(node => node.open), true);
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Installation overflow at ' + width);
    assert(await verified.evaluate(node => node.scrollWidth >= node.clientWidth));
    assert(await page.locator('.steps .step-num').evaluateAll(nodes => nodes.every(node => {
      const range = document.createRange(); range.selectNodeContents(node);
      return range.getClientRects().length === 1;
    })), 'Step labels wrap at ' + width);
    assert(await page.getByRole('button', { name: 'Bash 간편 설치 명령 복사', exact: true }).evaluate(node => node.getBoundingClientRect().height >= 44));
  }
  // Clipboard failure gives a selected command and a useful live instruction.
  await page.evaluate(() => { navigator.clipboard.writeText = async () => { throw Error('denied'); }; });
  await page.getByRole('button', { name: 'Bash 간편 설치 명령 복사', exact: true }).click();
  assert.equal(await page.evaluate(() => window.getSelection().toString()), await shell.innerText());
  assert((await page.locator('#copy-notice').textContent()).includes('키보드로 복사'));
  await page.goto('http://preview.local/joongi-skills/');
  assert((await shell.textContent()).includes('bash install.sh install'));
  assert.equal(await page.locator('[data-copy="shell-verified-command"]').isEnabled(), false);
  assert(!(await shell.textContent()).includes('curl'));
  assert.equal(errors.length, 0, errors.join('\n'));
  if (process.env.JOONGI_SCREENSHOT_DIR) {
    mkdirSync(process.env.JOONGI_SCREENSHOT_DIR, { recursive: true });
    await page.goto('https://pages.example/joongi-skills/');
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 1000 });
      await page.screenshot({ path: join(process.env.JOONGI_SCREENSHOT_DIR, `installation-${width}.png`), fullPage: true });
    }
  }
  console.log('Installation UX: short commands, optional provenance, clipboard/fallback, keyboard, panel state, preview and 320–1440 widths passed.');
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => { if (browser) await browser.close(); });
