'use strict';
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join, resolve } = require('node:path');
const { chromium } = require('playwright');
const directory = mkdtempSync(join(tmpdir(), 'joongi-catalog-preferences-'));
const source = join(directory, 'company-skills');
mkdirSync(join(source, 'company-theme'), { recursive: true });
writeFileSync(join(source, 'company-theme', 'SKILL.md'), '---\nname: company-theme\ndescription: Company supplied design rules\n---\n# Company theme\nUse the project design tokens.\n');
const child = spawn(process.env.PYTHON || 'python3', ['-B', '-m', 'tests.fixtures.catalog_hub', directory], { cwd: resolve(__dirname, '..'), stdio: ['ignore', 'pipe', 'pipe'] });
let browser, diagnosticPage;
async function main() {
  const fixture = await new Promise((accept, reject) => {
    const timeout = setTimeout(() => reject(Error('Catalog fixture startup timeout')), 15000);
    child.stdout.once('data', data => { clearTimeout(timeout); accept(JSON.parse(String(data))); });
    child.once('error', reject);
    child.once('exit', code => { clearTimeout(timeout); reject(Error('Fixture exited: ' + code)); });
  });
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } }); diagnosticPage = page;
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  let probes = 0, details = 0, calls = 0;
  page.on('request', request => {
    const path = new URL(request.url()).pathname;
    if (path.endsWith('/probe')) probes++;
    if (path === '/api/v1/catalog/item') details++;
    if (path === '/api/v1/call') calls++;
  });
  await page.goto(fixture.ui_url);
  await page.getByRole('heading', { name: '나의 도구를 연결하는 곳' }).waitFor();
  const search = page.getByRole('region', { name: '통합 검색', exact: true });
  const input = search.getByRole('searchbox');
  async function find(query) {
    await input.fill(query);
    const response = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/search');
    await search.getByRole('button', { name: '검색', exact: true }).click();
    const reply = await response;
    assert(reply.ok(), await reply.text());
    return reply.json();
  }
  await search.getByLabel('통합 검색 종류').selectOption('tool');
  const hits = await find('catalog__app');
  const items = Array.isArray(hits) ? hits : hits.results;
  assert(items.length <= 5);
  assert(items.every(item => !Object.hasOwn(item, 'inputSchema')));
  assert.equal(details, 0, 'Searching must not fetch every schema');
  const appRow = search.locator('.item-row').filter({ hasText: 'catalog__app' });
  await appRow.getByRole('button', { name: '상세', exact: true }).click();
  const detail = search.getByRole('region', { name: '검색 항목 상세', exact: true });
  await detail.getByRole('heading', { name: 'catalog__app', exact: true }).waitFor();
  assert.equal(details, 1);
  assert.equal(calls, 0, 'Inspecting metadata must not execute a tool');
  await detail.getByRole('button', { name: '도구 입력 열기 →', exact: true }).click();
  await page.getByRole('button', { name: 'App 열기', exact: true }).click();
  await page.frameLocator('.app-frame').frameLocator('#mcp-origin-view').getByText('App 연결됨', { exact: true }).waitFor();
  const frame = await page.locator('.app-frame').elementHandle();
  await find('catalog__echo');
  await search.locator('.item-row').filter({ hasText: 'catalog__echo' }).getByRole('button', { name: '상세', exact: true }).click();
  await detail.getByRole('heading', { name: 'catalog__echo', exact: true }).waitFor();
  assert(await frame.evaluate(node => node === document.querySelector('.app-frame')), 'Metadata detail must preserve the active App iframe');
  assert.equal(calls, 0);
  assert.equal(probes, 0);
  // A late exact-definition response cannot replace the new profile's selection.
  let release;
  const gate = new Promise(resolve => { release = resolve; });
  let finished; const routeFinished = new Promise(resolve => { finished = resolve; });
  const delayed = async route => { await gate; try { await route.continue(); } finally { finished(); } };
  await page.route('**/api/v1/catalog/item?*', delayed);
  await find('catalog__echo');
  const requested = page.waitForRequest(request => new URL(request.url()).pathname === '/api/v1/catalog/item');
  await search.locator('.item-row').filter({ hasText: 'catalog__echo' }).getByRole('button', { name: '상세', exact: true }).click();
  await requested;
  await page.getByLabel('작업 범위', { exact: true }).selectOption('isolated');
  await page.locator('#page[data-profile=isolated]').waitFor();
  release(); await routeFinished;
  await page.unroute('**/api/v1/catalog/item?*', delayed);
  assert.equal(await page.getByRole('heading', { name: 'catalog__echo', exact: true }).count(), 0);
  await page.getByLabel('작업 범위', { exact: true }).selectOption('global');
  await page.locator('#page[data-profile=global]').waitFor();
  async function openPreferences() {
    await page.getByRole('navigation', { name: '주 메뉴', exact: true }).getByRole('button', { name: '검색 설정', exact: true }).click();
    await page.getByRole('button', { name: '검색 설정 저장', exact: true }).waitFor();
  }
  async function save() {
    const previousEditor = await page.getByRole('region', { name: '검색 설정 편집', exact: true }).elementHandle();
    const response = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/catalog/settings' && response.request().method() === 'POST');
    await page.getByRole('button', { name: '검색 설정 저장', exact: true }).click();
    assert.equal((await response).ok(), true);
    await page.waitForFunction(node => !node.isConnected, previousEditor);
    await page.getByRole('button', { name: '검색 설정 저장', exact: true }).waitFor();
  }
  await openPreferences();
  const preferences = page.getByRole('region', { name: '검색 설정 편집', exact: true });
  await preferences.getByRole('checkbox', { name: '디자인', exact: true }).uncheck();
  let releaseSave, saveArrived;
  const saveGate = new Promise(resolve => { releaseSave = resolve; });
  const saveRequested = new Promise(resolve => { saveArrived = resolve; });
  const holdSave = async route => {
    if (route.request().method() !== 'POST') return route.continue();
    saveArrived(); await saveGate; await route.continue();
  };
  await page.route('**/api/v1/catalog/settings', holdSave);
  const saving = save(); saving.catch(() => {}); await saveRequested;
  assert.equal(await preferences.getByRole('checkbox', { name: '디자인', exact: true }).isEnabled(), false);
  assert.equal(await page.getByRole('navigation', { name: '주 메뉴', exact: true }).getByRole('button', { name: '스킬 라이브러리', exact: true }).isEnabled(), true);
  releaseSave(); await saving;
  await page.unroute('**/api/v1/catalog/settings', holdSave);
  const designHits = await find('applying-design-systems');
  assert.deepEqual(Array.isArray(designHits) ? designHits : designHits.results, []);
  // Raw inventory still offers disabled items so owners can restore them.
  await preferences.getByText('스킬별 검색과 묶음', { exact: true }).click();
  assert(await preferences.getByRole('checkbox', { name: /applying-design-systems/ }).count());
  const beforeReset = await preferences.elementHandle();
  const reset = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/catalog/reset');
  await preferences.getByRole('button', { name: '이 범위의 검색 설정 초기화', exact: true }).click();
  assert.equal((await reset).ok(), true);
  await page.waitForFunction(node => !node.isConnected, beforeReset);
  await preferences.getByRole('button', { name: '검색 설정 저장', exact: true }).waitFor();
  await preferences.getByText('출처 폴더 추가', { exact: true }).click();
  await preferences.getByLabel('스킬 출처 ID', { exact: true }).fill('company');
  await preferences.getByLabel('스킬 출처 이름', { exact: true }).fill('회사 지침');
  await preferences.getByLabel('스킬 출처 폴더', { exact: true }).fill(source);
  await preferences.getByLabel('스킬 출처 묶음', { exact: true }).selectOption('design');
  await preferences.getByRole('button', { name: '추가 목록에 넣기', exact: true }).click();
  await save();
  await page.getByRole('region', { name: '통합 검색', exact: true }).getByLabel('통합 검색 종류').selectOption('skill');
  const companyHits = await find('company-theme');
  assert((Array.isArray(companyHits) ? companyHits : companyHits.results).some(item => item.name === 'company__company-theme'), JSON.stringify(companyHits));
  await preferences.getByText('회사 디자인과 기본 지침 구분하기', { exact: true }).click();
  await preferences.getByRole('button', { name: '기본 디자인 지침만 제외', exact: true }).click();
  await save();
  const retainedCompany = await find('company-theme');
  assert((Array.isArray(retainedCompany) ? retainedCompany : retainedCompany.results).some(item => item.name === 'company__company-theme'));
  const excludedBuiltin = await find('applying-design-systems');
  assert(!(Array.isArray(excludedBuiltin) ? excludedBuiltin : excludedBuiltin.results).some(item => item.name === 'applying-design-systems'));

  await preferences.getByRole('checkbox', { name: /이 범위의 로컬 사용 통계 수집/ }).check();
  await save();
  await find('company-theme');
  await page.getByRole('button', { name: '변경 취소·다시 읽기', exact: true }).click();
  await preferences.getByText('수집 중', { exact: false }).waitFor();
  await preferences.getByRole('button', { name: '로컬 통계 삭제', exact: true }).click();
  await preferences.getByText('아직 기록된 사용 통계가 없습니다.', { exact: true }).waitFor();
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false, 'Preferences overflow at ' + width);
  }
  await preferences.getByRole('checkbox', { name: '디자인', exact: true }).uncheck();
  const failSave = route => route.request().method() === 'POST' ? route.fulfill({ status: 503, json: { error: 'temporary catalog failure' } }) : route.continue();
  await page.route('**/api/v1/catalog/settings', failSave);
  await preferences.getByRole('button', { name: '검색 설정 저장', exact: true }).click();
  await preferences.getByText('변경을 적용하지 못했습니다. 입력을 확인하고 다시 시도하세요.', { exact: true }).waitFor();
  assert.equal(await preferences.getByRole('checkbox', { name: '디자인', exact: true }).isChecked(), false);
  assert.equal(await preferences.getByRole('checkbox', { name: '디자인', exact: true }).isEnabled(), true);
  await page.unroute('**/api/v1/catalog/settings', failSave);
  assert(existsSync(join(source, 'company-theme', 'SKILL.md')), 'Source registration must preserve original files');
  assert.deepEqual(errors, []);
  console.log('Catalog preferences: three-stage detail, App preservation, stale profile detail, category disable/reset, source registration, opt-in usage and mobile passed.');
}
main().catch(async error => { console.error(error); if (diagnosticPage && !diagnosticPage.isClosed()) console.error('UI diagnostic:', await diagnosticPage.locator('#notice').textContent(), await diagnosticPage.locator('#page').innerText()); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  if (child.exitCode === null) { const ended = once(child, 'exit'); child.kill('SIGTERM'); await ended; }
  rmSync(directory, { recursive: true, force: true });
});
