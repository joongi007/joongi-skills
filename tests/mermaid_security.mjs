import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { renderSources } from '../scripts/render_mermaid.mjs';

const source = 'flowchart TD\n  A["사용자"] --> B["Hub"]\n  B --> C["서비스"]';
const identity = createHash('sha256').update(source).digest('hex');
const images = await renderSources({ [identity]: source }, async (page, svg) => {
  assert(svg.startsWith('<svg'));
  assert(!/<(?:script|foreignObject|iframe)\b/i.test(svg));
  const malicious = '<svg xmlns="http://www.w3.org/2000/svg" onload="window.__pwned=true"><script>window.__pwned=true</script><foreignObject><img src="x" onerror="window.__pwned=true"/></foreignObject><a href="javascript:alert(1)"><text>label</text></a><path onmouseover="alert(1)" d="M0,0"/></svg>';
  const clean = await page.evaluate(value => window.JoongiDiagram.sanitizeSvg(value), malicious);
  assert(!/<(?:script|foreignObject|iframe|image|a)\b|\son[a-z]+\s*=|javascript:/i.test(clean));
  for (const input of [
    '%%{init: {"securityLevel": "loose"}}%%\nflowchart TD\nA-->B',
    '---\nconfig:\n  securityLevel: loose\n---\nflowchart TD\nA-->B',
    'flowchart TD\nA-->B\nclick A "javascript:alert(1)"'
  ]) {
    const rejected = await page.evaluate(async value => {
      try { await window.JoongiDiagram.renderDiagram(value, 'blocked'); return false; }
      catch { return true; }
    }, input);
    assert(rejected, 'Untrusted renderer configuration must be rejected');
  }
  const rejectedCss = await page.evaluate(() => {
    try { window.JoongiDiagram.sanitizeSvg('<svg xmlns="http://www.w3.org/2000/svg"><style>@import url(https://example.invalid/x);</style></svg>'); return false; }
    catch { return true; }
  });
  assert(rejectedCss);
  assert.equal(await page.evaluate(() => Boolean(window.__pwned)), false);
});
assert(images[identity]);
console.log('Mermaid security passed: static SVG, configuration override rejection, SVG sanitization and external CSS/resource rejection.');
