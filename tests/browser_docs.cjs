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
  const diagrams = spawnSync(process.execPath, ['scripts/render_mermaid.mjs', output], { cwd: resolve(__dirname, '..'), encoding: 'utf8' });
  assert.equal(diagrams.status, 0, diagrams.stderr);
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ javaScriptEnabled: false });
  await context.route('https://pages.example/joongi-skills/**', route => {
    const name = decodeURIComponent(new URL(route.request().url()).pathname.slice('/joongi-skills/'.length)) || 'index.html';
    const file = resolve(output, name);
    if (!file.startsWith(resolve(output) + sep)) return route.fulfill({ status: 404, body: '' });
    try {
      const type = file.endsWith('.css') ? 'text/css' : file.endsWith('.html') ? 'text/html' : file.endsWith('.svg') ? 'image/svg+xml' : 'application/octet-stream';
      return route.fulfill({ contentType: type, body: readFileSync(file) });
    } catch { return route.fulfill({ status: 404, body: '' }); }
  });
  const page = await context.newPage();
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto('https://pages.example/joongi-skills/read/docs/00-index.html');
  await page.getByRole('heading', { name: '문서 안내', exact: true }).waitFor();
  await page.goto('https://pages.example/joongi-skills/read/docs/architecture/01-components.html');
  const image = page.locator('.mermaid-diagram img');
  await image.waitFor();
  assert(await image.evaluate(node => node.complete && node.naturalWidth > 0));
  assert.equal(await page.locator('script').count(), 0, 'Document reader must not execute Mermaid');
  await page.goto('https://pages.example/joongi-skills/read/docs/00-index.html');
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
  await page.getByRole('heading', { name: /요청에서 결과까지/ }).waitFor();
  const examples = page.locator('#examples');
  await examples.getByText('에이전트의 도구 사용 예시', { exact: true }).click();
  await examples.getByText('앱 안에서 승인하려면?', { exact: true }).click();
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.locator('html').evaluate(el => el.scrollWidth > innerWidth), false, 'Examples overflow at ' + width);
  }
  assert((await examples.textContent()).includes('실행하거나 개인 데이터에 접근하지 않습니다'));
  await examples.getByRole('link', { name: '작업 절차와 검사 범위 보기 →' }).click();
  await page.getByRole('heading', { name: '3D 작업과 GUI 호스트 승인 사용 예시', exact: true }).waitFor();
  await page.goto('https://pages.example/joongi-skills/');
  await page.getByRole('navigation', { name: '주 메뉴' }).getByRole('link', { name: '문서', exact: true }).click();
  await page.getByRole('heading', { name: /에이전트가 바뀌어도/ }).waitFor();
  const guide = page.locator('#guide-content');
  await page.getByRole('navigation', { name: '제공 기능 탐색' }).getByRole('link', { name: 'MCP', exact: true }).click();
  await guide.getByRole('link', { name: 'Code Review Graph', exact: true }).click();
  await page.getByRole('heading', { name: 'Code Review Graph 선택 연결', exact: true }).waitFor();
  await page.getByRole('navigation', { name: '사이트 메뉴' }).getByRole('link', { name: '문서 안내', exact: true }).click();
  await page.getByRole('navigation', { name: '제공 기능 탐색' }).getByRole('link', { name: 'Prompts', exact: true }).click();
  await page.locator('#prompts summary').click();
  assert((await page.locator('#prompts').innerText()).includes('prompts/get'));
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.locator('html').evaluate(el => el.scrollWidth > innerWidth), false, 'Guide overflow at ' + width);
  }
  await page.getByRole('navigation', { name: '제공 기능 탐색' }).getByRole('link', { name: '스킬', exact: true }).click();
  assert.equal(await page.locator('#skills dt a').count(), 5);
  await page.locator('#skills').getByRole('link', { name: '엔지니어링 플레이북', exact: true }).click();
  await page.getByRole('heading', { name: '엔지니어링 가이드', exact: true }).waitFor();
  await page.goto('https://pages.example/joongi-skills/');
  const security = page.locator('#security-example');
  await security.getByRole('heading', { name: '“이 보안 문제를 Codex Security로 확인해줘.”', exact: true }).waitFor();
  assert((await security.innerText()).includes('CLI 설치·서비스 접근 권한이 별도로 필요'));
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.locator('html').evaluate(el => el.scrollWidth > innerWidth), false, 'Security example overflow at ' + width);
  }
  await security.getByRole('link', { name: '보안 검수 가이드와 실행 조건 →', exact: true }).click();
  await page.getByRole('heading', { name: 'Hub에서 검수 가이드 찾기', exact: true }).waitFor();
  assert((await page.locator('main').innerText()).includes('MCP 서버가 아니다'));
  await page.goto('https://pages.example/joongi-skills/read/skills/engineering-playbook/references/wsl-development.html');
  await page.getByRole('heading', { name: 'WSL 개발 환경과 저장 공간', exact: true }).waitFor();
  assert((await page.locator('main').innerText()).includes('compact를 실행하라는 규칙은 아니다'));
  await page.goto('https://pages.example/joongi-skills/');
  await page.locator('#browser-example').getByRole('link', { name: '브라우저 준비와 보안 경계 →', exact: true }).click();
  await page.getByRole('heading', { name: 'Playwright로 브라우저 확인·조작하기', exact: true }).waitFor();
  assert((await page.locator('main').innerText()).includes('기본 Hub 설치는 브라우저 이미지나 MCP를 설치·등록하지 않는다'));
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.locator('html').evaluate(el => el.scrollWidth > innerWidth), false, 'Browser guide overflow at ' + width);
  }
  const production = join(directory, 'production');
  const taggedBuild = spawnSync(process.env.PYTHON || 'python3', ['-B', 'scripts/build_pages.py', '--out', production, '--base-url', 'https://joongi007.github.io/joongi-skills'], { cwd: resolve(__dirname, '..'), encoding: 'utf8' });
  assert.equal(taggedBuild.status, 0, taggedBuild.stderr);
  const tagged = await browser.newContext();
  let loads = 0, beacons = 0;
  await tagged.route('**/*', route => {
    const url = new URL(route.request().url());
    if (url.href === 'https://www.googletagmanager.com/gtm.js?id=GTM-MCHLMHRF') {
      loads++;
      return route.fulfill({contentType: 'text/javascript', body: "window.googleTagFixture=true;fetch('https://www.google-analytics.com/g/collect?fixture=1').then(()=>window.gaFixtureSent=true);"});
    }
    if (url.origin === 'https://www.google-analytics.com') {
      beacons++;
      return route.fulfill({status: 204, headers: {'access-control-allow-origin': '*'}});
    }
    if (url.origin !== 'https://joongi007.github.io' || !url.pathname.startsWith('/joongi-skills/')) return route.abort();
    const file = resolve(production, decodeURIComponent(url.pathname.slice('/joongi-skills/'.length)) || 'index.html');
    if (!file.startsWith(resolve(production) + sep)) return route.abort();
    try {
      const contentType = file.endsWith('.css') ? 'text/css' : file.endsWith('.js') ? 'text/javascript' : file.endsWith('.html') ? 'text/html' : 'application/octet-stream';
      return route.fulfill({contentType, body: readFileSync(file)});
    } catch { return route.fulfill({status: 404, body: ''}); }
  });
  const taggedPage = await tagged.newPage();
  const scriptErrors = [];
  taggedPage.on('pageerror', e => scriptErrors.push(e.message));
  for (const path of ['', 'read/docs/00-index.html', 'guide.html']) {
    await taggedPage.goto('https://joongi007.github.io/joongi-skills/' + path);
    await taggedPage.waitForFunction(() => window.googleTagFixture === true && window.gaFixtureSent === true);
    assert(await taggedPage.evaluate(() => window.dataLayer.some(item => item[0] === 'js')));
    assert.equal(await taggedPage.locator('script[src*="GTM-MCHLMHRF"]').count(), 1);
  }
  await taggedPage.evaluate(() => {
    const script = document.createElement('script');
    script.textContent = 'window.untrustedMarkdownScript=true';
    document.body.append(script);
  });
  assert.equal(await taggedPage.evaluate(() => window.untrustedMarkdownScript), undefined, 'CSP must still block untrusted inline code');
  assert.equal(loads, 3);
  assert.equal(beacons, 3, 'Document CSP must allow GA transport');
  assert.deepEqual(scriptErrors, []);
  await tagged.close();
  console.log('Static documentation: no-JS navigation, mobile layout, production GTM initialization/GA transport and CSP injection rejection passed (all Google requests mocked).');
}
main().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  if (browser) await browser.close();
  rmSync(directory, { recursive: true, force: true });
});
