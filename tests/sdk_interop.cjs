/* Interoperability against unmodified official SDK clients, both protocol eras.
 * npm ci, then npm run test:sdk
 * Or JOONGI_NODE_MODULES=/tmp/joongi-mcp-sdk/node_modules node tests/sdk_interop.cjs
 * Runtime dependencies are development-only. All state and skills use temporary paths.
 */
'use strict';

const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const { once } = require('node:events');
const { mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } = require('node:fs');
const { createRequire } = require('node:module');
const { tmpdir } = require('node:os');
const { join, resolve } = require('node:path');

const root = resolve(__dirname, '..');
const modules = process.env.JOONGI_NODE_MODULES || join(root, 'node_modules');
const dependency = createRequire(join(modules, 'package.json'));
const { Client: LegacyClient } = dependency('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport: LegacyStdio } = dependency('@modelcontextprotocol/sdk/client/stdio.js');
const { StreamableHTTPClientTransport: LegacyHttp } = dependency('@modelcontextprotocol/sdk/client/streamableHttp.js');
const modern = dependency('@modelcontextprotocol/client');
const { StdioClientTransport: ModernStdio } = dependency('@modelcontextprotocol/client/stdio');
const { SkillsClient } = dependency('@modelcontextprotocol/client/ext/skills');
const versions = {
  legacy: JSON.parse(readFileSync(join(modules, '@modelcontextprotocol/sdk/package.json'), 'utf8')).version,
  modern: JSON.parse(readFileSync(join(modules, '@modelcontextprotocol/client/package.json'), 'utf8')).version
};
assert.equal(versions.legacy, '1.32.2', 'Run against the pinned official legacy SDK');
assert.equal(versions.modern, '2.4.0', 'Run against the pinned official modern client');

const python = process.env.PYTHON || 'python3';
const temporary = mkdtempSync(join(tmpdir(), 'joongi-sdk-interop-'));
const skills = join(temporary, 'skills');
const skillRoot = join(skills, 'sdk-review');
mkdirSync(join(skillRoot, 'references'), { recursive: true });
mkdirSync(join(skillRoot, 'assets'), { recursive: true });
writeFileSync(join(skillRoot, 'SKILL.md'), '---\nname: sdk-review\ndescription: >\n  Verify SDK interoperability\n  with native skills.\nmetadata:\n  owner: "SDK team"\n  tier: verification\n---\n\n# SDK verification\n\nRead `references/check.md`.\n');
writeFileSync(join(skillRoot, 'references', 'check.md'), '# Checks\n\nRead only the selected file.\n');
const assetBytes = Buffer.from([0x00, 0xff, 0x10, 0x7f, 0x80, 0x42]);
writeFileSync(join(skillRoot, 'assets', 'sample.bin'), assetBytes);

function createState(name) {
  const directory = join(temporary, name);
  mkdirSync(directory, { recursive: true });
  writeFileSync(join(directory, 'servers.json'), JSON.stringify([{
    id: 'sdk-upstream', name: 'SDK upstream fixture', transport: 'stdio',
    command: python, args: [join(root, 'tests', 'fixtures', 'mcp_server.py')],
    enabled: true, protocol_version: 'auto'
  }]));
  return directory;
}

async function startHttp(state) {
  const child = spawn(python, ['-B', '-m', 'joongi_hub', 'serve', '--port', '0', '--state-dir', state, '--skills-dir', skills], {
    cwd: root, env: { ...process.env, PYTHONPATH: root }, stdio: ['ignore', 'ignore', 'pipe']
  });
  let diagnostic = '';
  const address = await new Promise((accept, reject) => {
    const timeout = setTimeout(() => reject(new Error(`HTTP Hub startup timeout: ${diagnostic}`)), 15000);
    child.once('error', error => { clearTimeout(timeout); reject(error); });
    child.once('exit', code => { clearTimeout(timeout); reject(new Error(`HTTP Hub exited ${code}: ${diagnostic}`)); });
    child.stderr.on('data', data => {
      diagnostic += String(data);
      const match = diagnostic.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) { clearTimeout(timeout); accept(match[0]); }
    });
  });
  return { child, address };
}

async function commonChecks(client, label) {
  const tools = await client.listTools();
  assert(tools.tools.some(tool => tool.name === 'hub_search'), `${label}: missing search tool`);
  const search = await client.callTool({ name: 'hub_search', arguments: { query: 'SDK' } });
  assert.match(search.content[0].text, /sdk-review/, `${label}: search result`);
  const resources = await client.listResources();
  const entry = resources.resources.find(item => item.name === 'sdk-review');
  assert(entry, `${label}: missing local skill resource`);
  const read = await client.readResource({ uri: entry.uri });
  assert.match(read.contents[0].text, /SDK verification/, `${label}: resource contents`);
  const reference = await client.readResource({ uri: 'skill://sdk-review/references/check.md' });
  assert.match(reference.contents[0].text, /Read only the selected file/, `${label}: reference read`);

  const connect = await client.callTool({ name: 'hub_connect', arguments: { server: 'sdk-upstream' } });
  assert(!connect.isError, `${label}: upstream connection`);
  const echo = await client.callTool({ name: 'hub_call', arguments: { name: 'sdk-upstream__echo', arguments: { message: label } } });
  const nativeTools = await client.listTools();
  const nativeEcho = nativeTools.tools.find(tool => tool.name === 'sdk-upstream__echo');
  assert(nativeEcho?.inputSchema?.type === 'object', `${label}: native tool schema missing`);
  const direct = await client.callTool({ name: nativeEcho.name, arguments: { message: 'native-proxy' } });
  assert.match(direct.content[0].text, /native-proxy/, `${label}: direct native tool call`);
  assert(echo.content[0].text.includes(label), `${label}: upstream result`);
  const prompts = await client.listPrompts();
  assert(prompts.prompts.some(prompt => prompt.name === 'sdk-upstream__review'), `${label}: prompt listing`);
  const prompt = await client.getPrompt({ name: 'sdk-upstream__review' });
  assert.equal(prompt.messages[0].role, 'user', `${label}: prompt role`);
  assert.match(prompt.messages[0].content.text, /Review this code/, `${label}: prompt content`);
  if (label.startsWith('2025')) {
    const ping = await client.ping();
    assert.equal(typeof ping, 'object', `${label}: ping`);
  } else {
    // The modern SDK deliberately rejects the removed legacy ping method.
    await assert.rejects(client.ping(), { code: 'METHOD_NOT_SUPPORTED_BY_PROTOCOL_VERSION' });
  }
}

async function skillChecks(client, label) {
  const extension = new SkillsClient(client);
  assert(extension.supported, `${label}: native skills extension not discovered`);
  assert(extension.directoryRead, `${label}: directoryRead capability missing`);
  const listing = await extension.list();
  assert.equal(listing.invalid.length, 0, `${label}: invalid native entries`);
  const entry = listing.skills.find(item => item.frontmatter.name === 'sdk-review');
  assert(entry, `${label}: missing native skill`);
  assert.equal(entry.frontmatter.metadata.owner, 'SDK team', `${label}: nested YAML mapping`);
  assert.equal(entry.frontmatter.metadata.tier, 'verification', `${label}: metadata preserved`);
  const direct = await extension.get(entry.uri);
  assert.equal(direct.skill.uri, entry.uri, `${label}: direct native lookup`);
  const document = await extension.read(direct.skill);
  assert.equal(document.verified, true, `${label}: skill manifest not verified`);
  assert.match(document.body, /SDK verification/, `${label}: verified skill body`);
  const remote = listing.skills.find(item => item.frontmatter.name === 'remote-review');
  assert(remote, `${label}: proxied native skill missing`);
  const remoteDocument = await extension.read(remote);
  assert.equal(remoteDocument.verified, true, `${label}: proxied skill manifest verification`);
  assert.match(remoteDocument.body, /Review carefully/, `${label}: proxied skill contents`);
  const reference = await extension.read(entry, 'references/check.md');
  assert.equal(reference.verified, true, `${label}: reference digest`);
  const binary = await extension.read(entry, 'assets/sample.bin');
  assert.equal(binary.verified, true, `${label}: binary digest`);
  assert.deepEqual(Buffer.from(binary.bytes), assetBytes, `${label}: binary bytes changed`);
  const directory = await extension.readDirectory('skill://sdk-review/references');
  assert.equal(directory.resources.length, 1, `${label}: directory children`);
  assert.equal(directory.resources[0].name, 'check.md', `${label}: directory entry name`);
}

async function runCase(era, transportKind) {
  const label = `${era}-${transportKind}`;
  const state = createState(label);
  const modernEra = era === '2026';
  const Client = modernEra ? modern.Client : LegacyClient;
  const options = modernEra ? {
    versionNegotiation: { mode: { pin: '2026-07-28' } },
    capabilities: { extensions: { 'io.modelcontextprotocol/skills': {} } }
  } : { capabilities: {} };
  const client = new Client({ name: `joongi-interop-${label}`, version: '1.0.0' }, options);
  let http;
  let transport;
  try {
    if (transportKind === 'stdio') {
      const Stdio = modernEra ? ModernStdio : LegacyStdio;
      transport = new Stdio({ command: python,
        args: ['-B', '-m', 'joongi_hub', 'stdio', '--state-dir', state, '--skills-dir', skills],
        cwd: root, env: { ...process.env, PYTHONPATH: root }, stderr: 'pipe' });
    } else {
      http = await startHttp(state);
      const Http = modernEra ? modern.StreamableHTTPClientTransport : LegacyHttp;
      transport = new Http(new URL(http.address + '/mcp'));
    }
    await client.connect(transport, { timeout: 10000 });
    assert.equal(client.getServerVersion().name, 'joongi-hub', `${label}: server identity`);
    if (modernEra) {
      assert.equal(client.getProtocolEra(), 'modern', `${label}: fallback would hide failure`);
      assert.equal(client.getNegotiatedProtocolVersion(), '2026-07-28', `${label}: wrong version`);
    }
    await commonChecks(client, label);
    if (modernEra) await skillChecks(client, label);
    console.log(`PASS ${label}: official SDK connect/tools/search/resources/upstream/prompts${modernEra ? '/native Skills verified' : ''}`);
  } finally {
    if (http && http.child.exitCode === null) {
      try {
        const session = await (await fetch(http.address + '/api/v1/session')).json();
        await fetch(http.address + '/api/v1/servers/sdk-upstream', { method: 'DELETE', headers: { 'X-Hub-Token': session.token } });
      } catch { /* Preserve the original SDK failure while cleanup remains best effort. */ }
    }
    await client.close().catch(() => {});
    if (http && http.child.exitCode === null) {
      const stopped = once(http.child, 'exit');
      http.child.kill('SIGTERM');
      await stopped;
    }
  }
}

async function main() {
  for (const era of ['2025', '2026']) {
    for (const transport of ['stdio', 'http']) await runCase(era, transport);
  }
  console.log(`Official SDK interoperability passed: 4 era/transport combinations. Versions: legacy ${versions.legacy}, modern ${versions.modern}.`);
}

main().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => {
  rmSync(temporary, { recursive: true, force: true });
});
