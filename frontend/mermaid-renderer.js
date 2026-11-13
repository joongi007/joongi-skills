// Only executed in an isolated, network-blocked build browser, never on the site.
import mermaid from 'mermaid';
import DOMPurify from 'dompurify';

function safeStyle(value) {
  if (/@import|@font-face|expression\s*\(|javascript:|vbscript:|\\/i.test(value)) throw Error('Unsafe SVG CSS');
  for (const match of value.matchAll(/url\s*\(([^)]*)\)/gi)) {
    if (!/^#[A-Za-z_][\w:.-]*$/.test(match[1].trim().replace(/^["']|["']$/g, ''))) throw Error('External SVG resource');
  }
}

export function sanitizeSvg(source) {
  const clean = DOMPurify.sanitize(source, {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: ['script', 'foreignObject', 'iframe', 'image', 'feImage', 'handler', 'a', 'animate', 'animateMotion', 'animateTransform', 'set'],
    FORBID_ATTR: ['href', 'xlink:href', 'xml:base'],
    RETURN_DOM: true
  });
  const svg = clean.querySelector('svg');
  if (!svg) throw Error('No safe SVG root');
  for (const node of [svg, ...svg.querySelectorAll('*')]) {
    for (const attribute of [...node.attributes]) {
      if (/^on/i.test(attribute.name)) node.removeAttribute(attribute.name);
      if (attribute.name === 'style' || /url\s*\(/i.test(attribute.value)) safeStyle(attribute.value);
    }
    if (node.localName === 'style') safeStyle(node.textContent);
  }
  svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  const result = new XMLSerializer().serializeToString(svg);
  if (result.length > 2 * 1024 * 1024) throw Error('SVG exceeds size limit');
  return result;
}

export async function renderDiagram(source, identity) {
  if (typeof source !== 'string' || source.length > 16000 || /%%\s*\{|^\s*---|^\s*click\s/im.test(source)) throw Error('Mermaid directives, frontmatter and interactions are disabled');
  mermaid.initialize({
    startOnLoad: false, securityLevel: 'strict', htmlLabels: false,
    suppressErrorRendering: true, maxTextSize: 16000, maxEdges: 256,
    secure: ['securityLevel', 'startOnLoad', 'htmlLabels', 'maxTextSize', 'maxEdges', 'flowchart'],
    flowchart: { htmlLabels: false }, theme: 'neutral', fontFamily: 'system-ui, sans-serif'
  });
  const { svg } = await mermaid.render('diagram-' + identity, source);
  return sanitizeSvg(svg);
}
window.JoongiDiagram = { renderDiagram, sanitizeSvg };
