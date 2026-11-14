/* Optional real-browser contract check.
 * npm install --prefix /tmp/joongi-browser playwright
 * PLAYWRIGHT_MODULE_PATH=/tmp/joongi-browser/node_modules/playwright node tests/browser_smoke.cjs
 * Uses a disposable state directory and random localhost port; never touches personal settings.
 */
'use strict';
const { spawn } = require('node:child_process');
const { mkdtempSync, rmSync, readFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { resolve, join } = require('node:path');
const { once } = require('node:events');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const python = process.env.PYTHON || 'python3';
const stateDir = mkdtempSync(join(tmpdir(), 'joongi-browser-'));
const server = spawn(python, ['-m', 'joongi_hub', 'serve', '--port', '0', '--state-dir', stateDir], { cwd: resolve(__dirname, '..'), stdio: ['ignore', 'ignore', 'pipe'] });
let browser;
async function main() {
  const address = await new Promise((accept, reject) => {
    const timeout = setTimeout(() => reject(new Error('Hub startup timed out')), 15000);
    server.once('error', error => { clearTimeout(timeout); reject(error); });
    server.once('exit', code => { clearTimeout(timeout); reject(new Error(`Hub exited (${code})`)); });
    server.stderr.on('data', data => {
      const match = String(data).match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timeout); accept(match[0]); }
    });
  });
  browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}), args: ['--no-sandbox'] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto(address + '/#session=' + JSON.parse(readFileSync(join(stateDir, 'http-auth.json'), 'utf8')).tokens.management.current);
  await page.getByRole('heading', { name: '나의 도구를 연결하는 곳' }).waitFor();
  await page.getByRole('button', { name: '스킬 라이브러리', exact: true }).click();
  await page.getByRole('button', { name: /engineering-playbook/ }).click();
  await page.locator('.skill-button').filter({ hasText: 'engineering-playbook' }).getByText('개발·인프라·보안·테스트 규칙', { exact: true }).waitFor();
  if (await page.locator('.document-meta').evaluate(node => node.open)) throw new Error('Skill metadata should start collapsed');
  await page.locator('#skill-content .markdown-body').getByText('엔지니어링 플레이북', { exact: false }).waitFor();
  await page.getByLabel('참조 문서 선택').selectOption('references/frontend.md');
  await page.locator('#skill-content .markdown-body').getByText('프론트엔드 (React + TypeScript)', { exact: false }).waitFor();
  await page.getByRole('button', { name: 'MCP 연결', exact: true }).click();
  await page.getByRole('button', { name: '+ MCP 등록', exact: true }).click();
  await page.getByLabel('표시 이름').fill('브라우저 검증 서버');
  await page.getByLabel('고유 ID').fill('browser-check');
  await page.getByLabel('실행 명령', { exact: true }).fill(python);
  await page.getByLabel('실행 인자', { exact: true }).fill(JSON.stringify([resolve(__dirname, 'fixtures/mcp_server.py')]));
  await page.getByRole('button', { name: '연결 등록', exact: true }).click();
  await page.getByRole('heading', { name: '브라우저 검증 서버', exact: true }).waitFor();
  await page.getByRole('button', { name: '연결 확인', exact: true }).click();
  await page.getByText('연결됨', { exact: true }).waitFor();
  const toolsDisclosure = page.locator('.server-tools[data-server="browser-check"]');
  if (await toolsDisclosure.evaluate(node => node.open)) throw new Error('Tool list should start collapsed');
  await toolsDisclosure.locator('summary').focus();
  await toolsDisclosure.locator('summary').press('Enter');
  const toolSearch = page.getByRole('searchbox', { name: '브라우저 검증 서버 도구 검색' });
  await toolSearch.fill('echo');
  if (await page.locator('.tool-row').count() !== 1) throw new Error('Tool filter did not narrow the list');
  await toolSearch.fill('');
  await page.locator('.connection-settings').first().locator(':scope > summary').click();
  await page.locator('.connection-settings').first().getByText('mcp_server.py', { exact: false }).waitFor();
  await page.locator('.connection-settings').first().locator(':scope > summary').click();
  await page.locator('.tool-row').filter({ hasText: 'Echo a message' }).getByRole('button', { name: '실행', exact: true }).click();
  await page.getByRole('textbox', { name: '도구 입력 JSON', exact: true }).fill('{"message":"browser-e2e"}');
  await page.getByRole('button', { name: '도구 실행', exact: true }).click();
  await page.locator('#tool-result').getByText('browser-e2e', { exact: false }).waitFor();
  await page.getByLabel('백그라운드 작업으로 실행', { exact: true }).check();
  await page.getByRole('button', { name: '도구 실행', exact: true }).click();
  await page.locator('#tool-result').getByText('taskId', { exact: false }).waitFor();
  await page.getByRole('button', { name: '실행 작업', exact: true }).click();
  await page.getByText('완료', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'MCP 연결', exact: true }).click();
  await page.locator('.tool-row').filter({ hasText: 'Interactive task' }).getByRole('button', { name: '실행', exact: true }).click();
  await page.getByLabel('백그라운드 작업으로 실행', { exact: true }).check();
  await page.getByRole('button', { name: '도구 실행', exact: true }).click();
  await page.locator('#tool-result').getByText('taskId', { exact: false }).waitFor();
  await page.getByRole('button', { name: '실행 작업', exact: true }).click();
  await page.getByText('입력 대기', { exact: true }).waitFor();
  await page.getByRole('textbox', { name: '작업 입력 응답 JSON', exact: true }).fill('{"name":{"action":"accept","content":{"name":"Browser"}}}');
  await page.getByRole('button', { name: '입력 보내기', exact: true }).click();
  await page.locator('tr').filter({ hasText: 'browser-check__ask' }).getByText('완료', { exact: true }).waitFor();
  await page.getByRole('button', { name: 'MCP 연결', exact: true }).click();
  await page.locator('.tool-row').filter({ hasText: 'An interactive app' }).getByRole('button', { name: '실행', exact: true }).click();
  await page.getByRole('button', { name: 'App 열기', exact: true }).click();
  const appFrame = page.frameLocator('.app-frame').frameLocator('#mcp-origin-view');
  await appFrame.getByText('App 연결됨', { exact: true }).waitFor();
  await appFrame.getByRole('button', { name: 'App에서 도구 호출', exact: true }).click();
  try { await appFrame.locator('#app-result').getByText('app-sdk-roundtrip', { exact: false }).waitFor({ timeout: 10000 }); }
  catch (error) { console.error('Apps diagnostic:', await appFrame.locator('body').innerText(), errors); throw error; }
  await appFrame.locator('#app-result').getByText('App resource content', { exact: false }).waitFor();
  await appFrame.getByRole('button', { name: 'App에서 Task 실행', exact: true }).click();
  await appFrame.locator('#app-task-result').getByText('Task 완료:', { exact: false }).waitFor();
  await appFrame.locator('#app-task-result').getByText('app-task-roundtrip', { exact: false }).waitFor();
  const parentBlocked = await page.frames().find(frame => frame.url().includes('/apps/')).evaluate(() => {
    try { return !window.parent.document.body; } catch { return true; }
  });
  if (!parentBlocked) throw new Error('MCP App accessed host DOM');
  await page.getByRole('button', { name: '작업 공간', exact: true }).click();
  await page.getByRole('searchbox', { name: '스킬과 도구 통합 검색', exact: true }).fill('remote-review');
  await page.getByRole('button', { name: '검색', exact: true }).click();
  await page.locator('.hub-search .item-row').filter({ hasText: 'browser-check__remote-review' }).getByRole('button', { name: '읽기 →', exact: true }).click();
  await page.locator('#skill-content .markdown-body').getByText('Review carefully.', { exact: false }).waitFor();
  await page.getByRole('button', { name: 'MCP 연결', exact: true }).click();
  await page.getByRole('button', { name: '제거', exact: true }).click();
  await page.getByRole('button', { name: '연결 제거', exact: true }).click();
  await page.getByText('이 저장소에 등록된 MCP가 없습니다', { exact: true }).waitFor();
  await page.getByRole('button', { name: '지원 범위', exact: true }).click();
  await page.getByRole('heading', { name: '지원 범위', exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '작업 공간', exact: true }).click();
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Mobile horizontal overflow');
  if (process.env.JOONGI_SCREENSHOT_DIR) {
    await page.screenshot({ path: join(process.env.JOONGI_SCREENSHOT_DIR, 'hub-mobile.png'), fullPage: true });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.screenshot({ path: join(process.env.JOONGI_SCREENSHOT_DIR, 'hub-desktop.png'), fullPage: true });
  }
  // Fulfil the actual static files at a project Pages path without network access.
  for (const origin of ['https://pages.example', 'http://preview.local']) {
    await page.route(`${origin}/joongi-skills/**`, async route => {
      const name = new URL(route.request().url()).pathname.split('/').pop() || 'index.html';
      const allowed = { 'index.html': 'text/html', 'tokens.css': 'text/css', 'style.css': 'text/css', 'install.js': 'application/javascript' };
      if (!Object.hasOwn(allowed, name)) return route.fulfill({ status: 404, body: '' });
      return route.fulfill({ contentType: allowed[name], body: readFileSync(resolve(__dirname, '../site', name)) });
    });
  }
  await page.goto('https://pages.example/joongi-skills/');
  await page.getByRole('tab', { name: 'macOS · Linux · WSL', exact: true }).waitFor();
  if (!(await page.locator('#shell-command').textContent()).includes('https://pages.example/joongi-skills/install.sh')) throw new Error('Pages project installation URL is incorrect');
  await page.getByRole('tab', { name: 'Windows', exact: true }).click();
  if (!(await page.locator('#windows-command').textContent()).includes('https://pages.example/joongi-skills/install.ps1')) throw new Error('Windows Pages URL is incorrect');
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Pages mobile horizontal overflow');
  await page.goto('http://preview.local/joongi-skills/');
  await page.getByText('로컬 미리보기입니다.', { exact: false }).waitFor();
  if ((await page.locator('#shell-command').textContent()).includes('curl')) throw new Error('Local preview must show clone installation');
  if (errors.length) throw new Error(errors.join('\n'));
  console.log('Browser smoke passed: local/remote skills, MCP lifecycle, interactive Tasks, official Apps iframe roundtrip/isolation, mobile layout, Pages, console.');
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  if (server.exitCode === null) { server.kill('SIGTERM'); await once(server, 'exit'); }
  rmSync(stateDir, { recursive: true, force: true });
});
