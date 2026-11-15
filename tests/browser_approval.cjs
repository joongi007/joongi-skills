/* Shared inbox preserves progress and recovers lost replies without duplicate decisions. */
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
  const fixture = await new Promise((accept, reject) => { let data=''; const timer=setTimeout(()=>reject(Error('Startup timeout')),15000); child.stdout.on('data',chunk=>{data+=chunk;if(data.includes('\n')){clearTimeout(timer);accept(JSON.parse(data.split('\n')[0]));}}); child.once('error',reject); });
  assert.equal(fixture.urls.length,1,'One approval window for three requests');
  browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
  const page=await browser.newPage({viewport:{width:320,height:720}}); const errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  const response=await page.goto(fixture.urls[0]);
  assert(response.headers()['content-security-policy'].includes("frame-ancestors 'none'"));
  await page.locator('#requests .request-row').nth(2).waitFor();
  assert.equal(new URL(page.url()).hash,'');
  await page.locator('#auto-close').uncheck();
  for(let index=0;index<3;index++) {
    const kind=['approve','deny','unknown'][index],action=index===1?'deny':'approve';
    await page.waitForFunction(kind=>document.querySelector('#arguments').textContent.includes(`"test": "${kind}"`),kind);
    assert.equal(await page.evaluate(()=>window.injected),undefined);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    let release; const gate=new Promise(resolve=>release=resolve); let writes=0,reads=0;
    await page.route('**/decision',async route=>{
      const body=route.request().postDataJSON();
      if(body.action==='status'){reads++;if(index===2&&reads===1){await route.abort('failed');return;}}
      if(body.action!==action){await route.continue();return;}
      writes++; const saved=await route.fetch(); assert.equal((await saved.json()).status,index===1?'denied':'approved');
      await gate; await route.abort('failed').catch(()=>{});
    });
    const target=page.locator(action==='approve'?'#approve':'#deny');
    await target.focus();const start=performance.now();await page.keyboard.press('Enter');
    await page.waitForTimeout(250);assert.match(await page.getByRole('status').first().innerText(),/저장하고 있습니다/);
    assert(await target.isDisabled());
    if(index!==1)release();
    if(index===2){await page.locator('#retry-status').waitFor();assert.match(await page.locator('#status').innerText(),/응답을 확인하지 못/);assert.equal(await page.locator('#close-status').isVisible(),false);await page.locator('#retry-status').click();}
    await page.waitForFunction(approved=>document.querySelector('#status').textContent.includes(approved?'한 번 승인했습니다.':'거절했습니다.'),index!==1);
    if(index===1){assert(performance.now()-start>=4500);release();}
    await page.unrouteAll({behavior:'wait'});
    await page.waitForFunction(count=>document.querySelectorAll('#requests .request-row').length===count,2-index);
    assert.equal(writes,1);assert.equal(reads,index===2?2:1);
  }
  assert.deepEqual(errors,[]);
  await browser.close();browser=null;child.stdin.end();await once(child,'exit');
  console.log('Approval inbox browser: one window, sequential requests, progress, timeout/lost response recovery, no duplicate writes, mobile, keyboard and XSS passed.');
}
main().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(child.exitCode===null)child.kill();rmSync(directory,{recursive:true,force:true});});
