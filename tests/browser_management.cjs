/* Isolated real-browser OAuth + scoped installation acceptance. */
'use strict';
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { mkdtempSync, rmSync, existsSync, readFileSync } = require('node:fs');
const { join, resolve } = require('node:path');
const { tmpdir } = require('node:os');
const { once } = require('node:events');
const { chromium } = require('playwright');
const directory = mkdtempSync(join(tmpdir(), 'joongi-management-'));
const processHub = spawn(process.env.PYTHON || 'python3', ['-m', 'tests.fixtures.managed_hub', directory], { cwd: resolve(__dirname, '..'), stdio: ['ignore', 'pipe', 'pipe'] });
let browser;
async function main() {
  const fixture = await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('Fixture startup timed out')), 15000);
    processHub.stdout.once('data', data => { clearTimeout(timer); resolve(JSON.parse(String(data))); });
    processHub.once('exit', code => reject(new Error(`Fixture exited ${code}`)));
    processHub.stderr.on('data', data => process.stderr.write(data));
  });
  browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}), args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto(fixture.url);
  await page.getByRole('button', { name: 'MCP 연결', exact: true }).click();
  await page.getByText('인증 · OAuth 브라우저 로그인', { exact: false }).click();
  await page.screenshot({ path: join(directory, 'authentication-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 900 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Authentication form overflow');
  await page.screenshot({ path: join(directory, 'authentication-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: '로그인 시작', exact: true }).click();
  const popupPromise = page.waitForEvent('popup');
  await page.getByRole('link', { name: '브라우저에서 계속 →' }).click();
  const popup = await popupPromise;
  await popup.getByText('로그인을 마쳤습니다.', { exact: false }).waitFor();
  await popup.close();
  await page.getByRole('button', { name: '연결 확인', exact: true }).click();
  await page.getByText('연결됨', { exact: true }).waitFor();
  await page.getByRole('button', { name: '스킬 라이브러리', exact: true }).click();
  await page.getByRole('button', { name: '설치 관리', exact: true }).click();
  const manager = page.locator('#skill-manager');
  await manager.getByLabel('codex', { exact: true }).check();
  await manager.getByRole('button', { name: '변경 계획 보기' }).click();
  await manager.getByRole('heading', { name: '적용할 변경', exact: true }).waitFor();
  await page.screenshot({ path: join(directory, 'install-plan-desktop.png'), fullPage: true });
  await page.setViewportSize({ width: 390, height: 900 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Installation plan overflow');
  await page.screenshot({ path: join(directory, 'install-plan-mobile.png'), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  assert(!existsSync(join(directory, 'home/.agents/skills/usual-korean')));
  await manager.getByRole('button', { name: '이 계획 적용' }).click();
  await page.getByText('스킬 변경을 적용했습니다.', { exact: false }).waitFor();
  assert(existsSync(join(directory, 'home/.agents/skills/usual-korean/SKILL.md')));
  await page.getByRole('button', { name: '프로젝트 범위', exact: true }).click();
  await page.getByRole('button', { name: '+ 프로젝트', exact: true }).click();
  await page.getByLabel('ID', { exact: true }).fill('browser-project');
  await page.getByLabel('이름', { exact: true }).fill('브라우저 프로젝트');
  await page.getByLabel('프로젝트 경로', { exact: true }).fill(fixture.project);
  await page.getByLabel('usual-korean', { exact: true }).check();
  await page.getByRole('button', { name: '범위 저장', exact: true }).click();
  await page.getByText('프로젝트 범위를 저장했습니다.', { exact: false }).waitFor();
  await page.getByLabel('작업 범위', { exact: true }).selectOption('browser-project');
  await page.waitForFunction(() => document.querySelector('#page').dataset.profile === 'browser-project');
  await page.getByRole('button', { name: '스킬 라이브러리', exact: true }).click();
  await page.locator('.skill-button').filter({ hasText: 'usual-korean' }).waitFor();
  assert.equal(await page.locator('.skill-button').count(), 1);
  await page.getByRole('button', { name: '설치 관리', exact: true }).click();
  await manager.getByLabel('codex', { exact: true }).check();
  await manager.getByRole('button', { name: '변경 계획 보기' }).click();
  await manager.getByRole('button', { name: '이 계획 적용' }).click();
  await page.getByText('스킬 변경을 적용했습니다.', { exact: false }).waitFor();
  const lock = JSON.parse(readFileSync(join(fixture.project, 'joongi-skills.lock.json')));
  assert.equal(lock.skills[0].pinned, true);
  await page.getByRole('button', { name: 'MCP 연결', exact: true }).click();
  await page.getByText('이 저장소에 등록된 MCP가 없습니다', { exact: true }).waitFor();
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Overflow at ${width}`);
    await page.screenshot({ path: join(directory, `management-${width}.png`), fullPage: true });
  }
  assert.deepEqual(errors, []);
  console.log('Browser management: OAuth popup/callback, user install, project selection/isolation, pinned install, mobile passed');
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  if (processHub.exitCode === null) { const done = once(processHub, 'exit'); processHub.kill('SIGINT'); await done; }
  if (!process.env.KEEP_MANAGEMENT_FIXTURE) rmSync(directory, { recursive: true, force: true });
  else console.log(`Fixture retained: ${directory}`);
});
