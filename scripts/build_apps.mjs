// Developer-only bundling; the installer ships the resulting static file.
import { createRequire } from 'node:module';
import { resolve } from 'node:path';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
const require = createRequire(import.meta.url);
const esbuild = process.env.JOONGI_NODE_MODULES
  ? require(resolve(process.env.JOONGI_NODE_MODULES, 'esbuild'))
  : require('esbuild');
const hostBuild = await esbuild.build({
  entryPoints: ['frontend/apps-host.js'],
  outfile: 'joongi_hub/static/apps-host.js',
  bundle: true,
  format: 'iife',
  platform: 'browser',
  minify: true,
  legalComments: 'linked',
  metafile: true,
  nodePaths: process.env.JOONGI_NODE_MODULES ? [process.env.JOONGI_NODE_MODULES] : []
});
const packages = new Map();
for (const input of Object.keys(hostBuild.metafile.inputs)) {
  const normalized = input.replaceAll('\\', '/');
  const marker = normalized.lastIndexOf('node_modules/');
  if (marker < 0) continue;
  const parts = normalized.slice(marker + 13).split('/');
  const name = parts[0].startsWith('@') ? parts.slice(0, 2).join('/') : parts[0];
  const directory = resolve(normalized.slice(0, marker + 13), name);
  const metadata = JSON.parse(readFileSync(resolve(directory, 'package.json'), 'utf8'));
  const license = ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'license'].find(file => existsSync(resolve(directory, file)));
  if (!license) throw new Error(`License file missing: ${name}`);
  packages.set(`${name} ${metadata.version}`, `${name} ${metadata.version} (${metadata.license})\n${'-'.repeat(60)}\n${readFileSync(resolve(directory, license), 'utf8')}\n`);
}
writeFileSync('joongi_hub/static/NOTICE-sdk.txt', 'Official MCP Apps browser bundle dependency notices\n\n' + [...packages].sort(([a], [b]) => a.localeCompare(b)).map(([, value]) => value).join('\n'));
await esbuild.build({
  entryPoints: ['frontend/demo-view.js'],
  outfile: 'examples/apps/demo-view.js',
  bundle: true,
  format: 'iife',
  platform: 'browser',
  minify: true,
  legalComments: 'linked',
  nodePaths: process.env.JOONGI_NODE_MODULES ? [process.env.JOONGI_NODE_MODULES] : []
});
