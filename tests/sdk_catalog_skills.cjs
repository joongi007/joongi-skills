/* Unmodified official SkillsClient must accept, separate and verify source-qualified skills. */
'use strict';
const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { createRequire } = require('node:module');
const { join, resolve } = require('node:path');
const root = resolve(__dirname, '..');
const dependency = createRequire(join(process.env.JOONGI_NODE_MODULES || join(root, 'node_modules'), 'package.json'));
const { Client } = dependency('@modelcontextprotocol/client');
const { StdioClientTransport } = dependency('@modelcontextprotocol/client/stdio');
const { SkillsClient } = dependency('@modelcontextprotocol/client/ext/skills');

async function main() {
  const client = new Client({ name: 'source-catalog-skills-audit', version: '1' }, {
    versionNegotiation: { mode: { pin: '2026-07-28' } },
    capabilities: { extensions: { 'io.modelcontextprotocol/skills': {} } }
  });
  const transport = new StdioClientTransport({
    command: process.env.PYTHON || 'python3',
    args: ['-B', join(root, 'tests/fixtures/catalog_skills_stdio.py')],
    cwd: root,
    env: { ...process.env, PYTHONPATH: root },
    stderr: 'pipe'
  });
  let diagnostic = '';
  transport.stderr?.on('data', data => { diagnostic += String(data); });
  try {
    await client.connect(transport, { timeout: 10000 });
    assert.equal(client.getProtocolEra(), 'modern');
    assert.equal(client.getNegotiatedProtocolVersion(), '2026-07-28');
    const skills = new SkillsClient(client);
    const listing = await skills.list();
    assert.equal(listing.invalid.length, 0);
    assert.equal(listing.skills.length, 2);
    const bySource = new Map(listing.skills.map(entry => [entry.frontmatter.metadata.owner, entry]));
    assert.deepEqual([...bySource.keys()].sort(), ['company', 'personal']);
    assert.notEqual(bySource.get('company').uri, bySource.get('personal').uri);
    for (const identity of ['company', 'personal']) {
      const entry = bySource.get(identity);
      assert.equal(entry.frontmatter.name, 'same-guide', 'Source frontmatter must not be rewritten');
      assert.equal(entry.uri, `skill://${identity}__same-guide/same-guide/SKILL.md`);
      const direct = await skills.get(entry.uri);
      assert.equal(direct.skill.uri, entry.uri);
      const read = await skills.read(direct.skill);
      assert.equal(read.verified, true);
      const expectedText = `---\nname: same-guide\ndescription: Same name, different source.\nmetadata:\n  owner: ${identity}\n---\n\n# ${identity} source guide\n`;
      assert.equal(Buffer.from(read.bytes).toString('utf8'), expectedText);
      const manifest = entry.resources.find(resource => resource.uri === entry.uri);
      assert.equal(manifest.size, Buffer.byteLength(expectedText));
      assert.equal(manifest.digest, 'sha256:' + createHash('sha256').update(expectedText).digest('hex'));
      const reference = await skills.read(entry, 'references/check.md');
      assert.equal(reference.verified, true);
      assert.equal(Buffer.from(reference.bytes).toString('utf8'), `# ${identity} source reference\n`);
      const binary = await skills.read(entry, 'assets/sample.bin');
      assert.equal(binary.verified, true);
      assert.deepEqual(Buffer.from(binary.bytes), Buffer.concat([Buffer.from([0, 255, 17]), Buffer.from(identity)]));
      const directory = await skills.readDirectory(new URL('./references', entry.uri).href);
      assert.equal(directory.resources.length, 1);
      assert.equal(directory.resources[0].uri, new URL('./references/check.md', entry.uri).href);
    }
    await assert.rejects(skills.read(bySource.get('company'), bySource.get('personal').uri), /not a file|unlisted/i);
    const configured = await client.callTool({ name: 'hub_catalog_configure', arguments: { patch: { disabled: { source: ['company'] } } } });
    assert(!configured.isError);
    const hidden = await skills.list();
    assert.equal(hidden.skills.length, 1);
    assert.equal(hidden.skills[0].frontmatter.metadata.owner, 'personal');
    await assert.rejects(skills.get(bySource.get('company').uri), /disabled|unknown|unavailable/i);
    await assert.rejects(client.readResource({ uri: bySource.get('company').uri }, { cacheMode: 'refresh' }), /disabled|unknown|unavailable/i);
    const restored = await client.callTool({ name: 'hub_catalog_configure', arguments: { patch: { disabled: { source: [] } } } });
    assert(!restored.isError);
    assert.equal((await skills.list()).skills.length, 2);
    const grouped = await client.callTool({ name: 'hub_catalog_configure', arguments: { patch: { disabled: { category: ['design'] } } } });
    assert(!grouped.isError);
    const categoryListing = await skills.list();
    assert.equal(categoryListing.skills.length, 1);
    assert.equal(categoryListing.skills[0].frontmatter.metadata.owner, 'personal');
    console.log('Official Skills SDK: same-name sources, native list/get, byte/digest/reference/binary/directory verification, cross-source rejection and selection changes passed.');
  } catch (error) {
    if (diagnostic) console.error('Isolated source fixture diagnostic:', diagnostic);
    throw error;
  } finally {
    await client.close().catch(() => {});
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
