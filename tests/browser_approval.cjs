/* Real owner consent, slow/lost responses, bounded recovery, CSP and XSS. */
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
    if (index === 0) await page.locator('#auto-close').uncheck();
    assert.equal(await page.locator('#arguments').innerText(), JSON.stringify({page: '<img src=x onerror="window.injected=true">', test: ['approve', 'deny', 'unknown'][index]}, null, 2));
    assert.equal(await page.evaluate(() => window.injected), undefined);
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    const action = index === 1 ? 'deny' : 'approve';
    const target = page.locator(action === 'approve' ? '#approve' : '#deny');
    let releaseDecision;
    const gate = new Promise(resolve => { releaseDecision = resolve; });
    let writes = 0, statusReads = 0;
    await page.route('**/decision', async route => {
      const body = route.request().postDataJSON();
      if (body.action === 'status') {
        statusReads++;
        if (index === 2 && statusReads === 1) { await route.abort('failed'); return; }
      }
      if (body.action !== action) { await route.continue(); return; }
      writes++;
      const saved = await route.fetch();
      assert.equal((await saved.json()).status, action === 'approve' ? 'approved' : 'denied');
      await gate;
      await route.abort('failed').catch(() => {}); // Lost response or client deadline.
    });
    await target.focus();
    const started = performance.now();
    await page.keyboard.press('Enter');
    await page.waitForTimeout(250);
    assert.match(await page.getByRole('status').innerText(), /저장하고 있습니다/, 'Click must show a saving state before the delayed POST returns');
    assert(await target.isDisabled());
    if (index !== 1) releaseDecision(); // Lost acknowledgement after commit.
    // For denial, withhold acknowledgement past the real 5s browser deadline.
    if (index === 2) {
      await page.getByRole('button', { name: '승인 상태 다시 확인' }).waitFor();
      assert.match(await page.getByRole('status').innerText(), /응답을 확인하지 못/);
      assert.equal(await page.locator('#title').innerText(), '이 요청을 허용할까요?');
      assert.equal(await page.locator('#close-status').isVisible(), false, 'Unconfirmed outcomes must never start auto-close');
      await page.locator('#auto-close').uncheck();
      await page.getByRole('button', { name: '승인 상태 다시 확인' }).click();
    }
    await page.getByRole('heading', { name: action === 'approve' ? '승인 완료' : '요청 거절', exact: true }).waitFor();
    if (index === 1) { assert.equal(await page.locator('#close-status').isVisible(), false, 'Denial must remain visible'); assert(performance.now() - started >= 4500, `Deadline elapsed ${performance.now() - started}ms`); releaseDecision(); }
    await page.unrouteAll({ behavior: 'wait' });
    assert.equal(writes, 1, 'Recovery must never send a second decision');
    assert.equal(statusReads, index === 2 ? 2 : 1, 'Lost response is recovered with a read-only status check');
    assert(await target.isDisabled());
    assert.equal(await page.locator('#retry-status').isVisible(), false);
    assert.equal(await page.locator('#actions').isVisible(), false, 'Completed review must not retain loading-looking disabled controls');
  }
  assert.deepEqual(errors, []);
  await browser.close(); browser = null;
  child.stdin.end();
  await once(child, 'exit');
  console.log('Owner approval browser: instant progress, lost response/deadline recovery without duplicate writes, mobile, keyboard, CSP and XSS passed.');
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  if (child.exitCode === null) child.kill();
  rmSync(directory, { recursive: true, force: true });
});
