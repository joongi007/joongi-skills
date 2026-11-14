/* Owner-browser real consent: CSP, script injection, mobile, keyboard and denial. */
'use strict';
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { mkdtempSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, resolve } = require('node:path');
const { once } = require('node:events');
const { chromium } = require('playwright');
const directory = mkdtempSync(join(tmpdir(), 'joongi-owner-review-'));
const child = spawn(process.env.PYTHON || 'python3', ['-B', '-m', 'tests.fixtures.approval_hub', directory], { cwd: resolve(__dirname, '..'), stdio: ['pipe', 'pipe', 'pipe'] });
let browser;
async function main() {
  const fixture = await new Promise((accept, reject) => {
    let output = '';
    const timer = setTimeout(() => reject(Error('Startup timeout')), 15000);
    child.stdout.on('data', data => { output += data; if (output.includes('\n')) { clearTimeout(timer); accept(JSON.parse(output.split('\n')[0])); } });
    child.once('error', reject);
  });
  browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}), args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 320, height: 720 } });
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  for (const [index, url] of fixture.urls.entries()) {
    await page.goto('about:blank');
    const response = await page.goto(url);
    assert(response.headers()['content-security-policy'].includes("frame-ancestors 'none'"));
    await page.getByRole('button', { name: '이 호출 한 번 승인', exact: true }).waitFor();
    assert.equal(new URL(page.url()).hash, '');
    assert.equal(await page.locator('#arguments').innerText(), JSON.stringify({page: '<img src=x onerror="window.injected=true">', test: index === 0 ? 'approve' : 'deny'}, null, 2));
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const target = page.getByRole('button', { name: index === 0 ? '이 호출 한 번 승인' : '거절', exact: true });
    await target.focus();
    const decision = page.waitForResponse(r => r.url().endsWith('/decision') && r.request().postDataJSON().action !== 'view');
    await page.keyboard.press('Enter');
    assert.equal((await (await decision).json()).status, index === 0 ? 'approved' : 'denied');
    await page.getByRole('status').getByText(index === 0 ? /한 번 승인했습니다/ : /거절했습니다/).waitFor();
    assert(await target.isDisabled());
  }
  assert.deepEqual(errors, []);
  await browser.close(); browser = null;
  child.stdin.end();
  await once(child, 'exit');
  console.log('Owner approval browser: approve/deny, keyboard, mobile, CSP and XSS passed.');
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  if (child.exitCode === null) child.kill();
  rmSync(directory, { recursive: true, force: true });
});
