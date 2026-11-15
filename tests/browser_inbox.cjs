/* Batch selection is a snapshot; another stdio process joins the existing inbox. */
'use strict';
const assert=require('node:assert/strict');
const {spawn}=require('node:child_process');
const {mkdtempSync,rmSync}=require('node:fs');
const {join,resolve}=require('node:path');
const {tmpdir}=require('node:os');
const {once}=require('node:events');
const {chromium}=require('playwright');
const dir=mkdtempSync(join(tmpdir(),'joongi-inbox-browser-'));
const child=spawn(process.env.PYTHON||'python3',['-B','-m','tests.fixtures.inbox_hub',dir],{cwd:resolve(__dirname,'..'),stdio:['pipe','pipe','pipe']});
const rows=[], readers=[];let buffer='';
child.stdout.on('data',data=>{buffer+=data;while(buffer.includes('\n')){const i=buffer.indexOf('\n'),row=JSON.parse(buffer.slice(0,i));buffer=buffer.slice(i+1);if(readers.length)readers.shift()(row);else rows.push(row);}});
const read=()=>rows.length?Promise.resolve(rows.shift()):new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Fixture timeout')),15000);readers.push(value=>{clearTimeout(timer);resolve(value);});});
let browser;
async function main(){
 const fixture=await read();
 browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:390,height:850}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto(fixture.url);await page.locator('#requests .request-row').nth(1).waitFor();
 assert.equal(await page.locator('#requests h3').count(),2);
 assert.equal(await page.evaluate(()=>window.injected),undefined);
 await page.locator('#select-all').click();
 assert.equal(await page.locator('#requests input:checked').count(),2);
 child.stdin.write('enqueue\n');const later=await read();assert.equal(later.reused,true);assert.equal(later.launches,1);
 await page.locator('#requests .request-row').nth(2).waitFor();
 assert.equal(await page.locator('#requests input:checked').count(),2,'New arrivals must never be selected automatically');
 let writes=0;
 await page.route('**/inbox',async route=>{
  const body=route.request().postDataJSON();if(body.action!=='approve'){await route.continue();return;}
  writes++;assert.deepEqual(new Set(body.approval_ids),new Set(fixture.ids));
  const saved=await route.fetch();assert.equal((await saved.json()).decisions.length,2);
  await route.abort('failed');
 });
 await page.locator('#batch-approve').click();
 await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('2개 요청을 승인했습니다.'));
 await page.unrouteAll({behavior:'wait'});
 child.stdin.write('status\n');assert.deepEqual(await read(),{statuses:['approved','approved','pending'],launches:1});
 assert.equal(writes,1,'Lost batch reply must only trigger status recovery');
 assert.equal(await page.locator('#close-status').isVisible(),false,'Pending requests keep the shared window open');
 await page.locator('#deny').click();await page.waitForFunction(()=>document.querySelector('#status').textContent.includes('거절했습니다.'));
 assert.equal(await page.locator('#close-status').isVisible(),false);
 assert.deepEqual(errors,[]);
 await browser.close();browser=null;child.stdin.end();await once(child,'exit');
 console.log('Inbox browser: two MCP groups, cross-process window reuse, snapshot batch, lost reply recovery and no automatic approval of new arrivals passed.');
}
main().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();if(child.exitCode===null)child.kill();rmSync(dir,{recursive:true,force:true});});
