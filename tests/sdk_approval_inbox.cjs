/* Official clients must accept approval waiting even for a typed native tool. */
'use strict';
const assert = require('node:assert/strict');
const { mkdtempSync, rmSync } = require('node:fs');
const { join, resolve } = require('node:path');
const { tmpdir } = require('node:os');
const { Client: Legacy } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport: LegacyStdio } = require('@modelcontextprotocol/sdk/client/stdio.js');
const { Client: Modern } = require('@modelcontextprotocol/client');
const { StdioClientTransport: ModernStdio } = require('@modelcontextprotocol/client/stdio');
const root = resolve(__dirname, '..');
const directory = mkdtempSync(join(tmpdir(), 'joongi-approval-sdk-'));
async function main() {
  for (const modern of [false, true]) {
    const Client = modern ? Modern : Legacy, Stdio = modern ? ModernStdio : LegacyStdio;
    const client = new Client({name:'approval-sdk-test',version:'1'}, modern ? {versionNegotiation:{mode:{pin:'2026-07-28'}},capabilities:{}} : {capabilities:{}});
    const transport = new Stdio({command:process.env.PYTHON || 'python3',args:['-B','-m','tests.fixtures.approval_sdk',join(directory,modern?'modern':'legacy')],cwd:root,env:{...process.env,PYTHONPATH:root},stderr:'pipe'});
    try {
      await client.connect(transport);
      const tools = await client.listTools();
      const tool = tools.tools.find(tool => tool.name === 'protected__echo');
      assert(tool?.outputSchema?.anyOf, 'Proxy must declare the consent-result alternative');
      for (let i=0;i<2;i++) {
        const result = await client.callTool({name:tool.name,arguments:{message:'synthetic-'+i}});
        assert.equal(result.isError,false);
        assert.equal(result.structuredContent.status,'approval_required');
        assert.equal(result.structuredContent.execution,'not_started');
        assert.equal(result.structuredContent.window_reused,i!==0);
        assert(!JSON.stringify(result).includes('#session='));
      }
    } finally { await client.close(); }
  }
  console.log('Official SDK consent contract: both protocol eras accept typed native approval waiting without errors.');
}
main().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>rmSync(directory,{recursive:true,force:true}));
