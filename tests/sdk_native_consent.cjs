'use strict';
const assert = require('node:assert/strict');
const { mkdtempSync, rmSync, existsSync, readFileSync } = require('node:fs');
const { join, resolve } = require('node:path');
const { tmpdir } = require('node:os');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');
const { ElicitRequestSchema } = require('@modelcontextprotocol/sdk/types.js');
const directory = mkdtempSync(join(tmpdir(),'joongi-native-consent-'));
async function main() {
  for (const bridged of [false,true]) for (const action of ['accept','decline','cancel','defer']) {
    const state = join(directory,`${bridged}-${action}`);
    const client = new Client({name:'host-form-test',version:'1'},{capabilities:{elicitation:{form:{}}}});
    let forms = 0;
    client.setRequestHandler(ElicitRequestSchema, async request => {
      forms++;
      assert.equal(request.params.mode,'form');
      assert.equal(request.params.requestedSchema.properties.request_0.default,false);
      assert(!JSON.stringify(request).includes('fake-sdk-credential'));
      if (action === 'defer') return {action:'accept',content:{}};
      return action === 'accept' ? {action,content:{request_0:true}} : {action};
    });
    const transport = new StdioClientTransport({command:process.env.PYTHON || 'python3',args:['-B','-m','tests.fixtures.approval_sdk',state,...(bridged?['--bridge']:[])],cwd:resolve(__dirname,'..'),env:{...process.env},stderr:'pipe'});
    try {
      await client.connect(transport);
      await client.listTools();
      const result = await client.callTool({name:'protected__echo',arguments:{message:'synthetic native consent'}});
      assert.equal(forms,1);
      assert(!existsSync(join(state,'browser-opened')),'A supported host must not open an approval browser');
      if (action === 'accept') {
        assert.equal(result.structuredContent.data,'synthetic native consent');
        assert.equal(readFileSync(join(state,'executed.jsonl'),'utf8').trim().split('\n').length,1);
      } else {
        assert.equal(result.isError,false);
        assert.equal(result.structuredContent.execution,'not_started');
        assert.equal(result.structuredContent.host_consent,action === 'defer' ? 'not_selected' : action);
        assert(!existsSync(join(state,'executed.jsonl')),'Declined/cancelled tool must not execute');
        if (action === 'defer') {
          const fallback = await client.callTool({name:'hub_approval_request',arguments:{approval_id:result.structuredContent.approval_id}});
          assert.equal(fallback.isError,undefined);
          assert(existsSync(join(state,'browser-opened')),'An explicit owner request must still open the fallback inbox');
        }
      }
    } finally { await client.close(); }
  }
  console.log('Official SDK native consent: pure stdio and local HTTP bridge; accept executes once, decline/cancel never execute, no browser or credential disclosure.');
}
main().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>rmSync(directory,{recursive:true,force:true}));
