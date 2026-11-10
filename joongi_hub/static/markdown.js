'use strict';
// A deliberately small reader: build DOM nodes, never interpret document HTML.
window.JoongiMarkdown = (() => {
  function node(tag, text) { const item = document.createElement(tag); if (text !== undefined) item.textContent = text; return item; }
  function render(source, { reference = () => {} } = {}) {
    const root = node('article'); root.className = 'markdown-body';
    const headings = new Map();
    function inline(parent, text) {
      const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|\*[^*\n]+\*|\[[^\]\n]+\]\([^\s)]+\))/g;
      let offset = 0;
      for (const match of text.matchAll(pattern)) {
        parent.append(document.createTextNode(text.slice(offset, match.index)));
        const value = match[0];
        if (value.startsWith('`')) parent.append(node('code', value.slice(1, -1)));
        else if (value.startsWith('**')) parent.append(node('strong', value.slice(2, -2)));
        else if (value.startsWith('*')) parent.append(node('em', value.slice(1, -1)));
        else {
          const [, label, target] = value.match(/^\[([^\]]+)\]\((.+)\)$/);
          const anchor = node('a', label);
          if (/^https?:\/\//i.test(target)) {
            try { const url = new URL(target); if (!['http:', 'https:'].includes(url.protocol)) throw Error(); anchor.href = url.href; anchor.target = '_blank'; anchor.rel = 'noopener noreferrer'; parent.append(anchor); }
            catch { parent.append(document.createTextNode(label)); }
          } else if (target.startsWith('#')) {
            anchor.href = target; anchor.addEventListener('click', event => { event.preventDefault(); let slug; try { slug = decodeURIComponent(target.slice(1)); } catch { return; } const heading = headings.get(slug); if (heading) { heading.scrollIntoView({ block: 'nearest' }); heading.focus({ preventScroll: true }); } }); parent.append(anchor);
          } else if (!/^[a-z][a-z0-9+.-]*:|^\/|\\/i.test(target)) {
            const link = node('button', label); link.type = 'button'; link.className = 'reference-link'; link.addEventListener('click', () => reference(target)); parent.append(link);
          } else parent.append(document.createTextNode(label));
        }
        offset = match.index + value.length;
      }
      parent.append(document.createTextNode(text.slice(offset)));
    }
    const lines = String(source).replace(/\r\n?/g, '\n').split('\n');
    const cells = line => line.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim());
    const special = line => /^(?:\s*$|#{1,6}\s|\s*```|\s*~~~|\s*[-*+]\s|\s*\d+\.\s|>\s?|\s*(?:---+|\*\*\*+)\s*$)/.test(line);
    for (let i = 0; i < lines.length;) {
      const line = lines[i];
      if (!line.trim()) { i++; continue; }
      const fence = line.match(/^\s*(`{3,}|~{3,})(.*)$/);
      if (fence) {
        const body = []; i++;
        while (i < lines.length && !lines[i].trim().startsWith(fence[1])) body.push(lines[i++]);
        if (i < lines.length) i++;
        const pre = node('pre'); pre.append(node('code', body.join('\n'))); root.append(pre); continue;
      }
      const heading = line.match(/^(#{1,6})\s+(.+?)\s*#*$/);
      if (heading) {
        const item = node(`h${Math.min(6, heading[1].length + 1)}`); inline(item, heading[2]); item.tabIndex = -1;
        const slug = heading[2].toLowerCase().replace(/[^\p{L}\p{N}\s-]/gu, '').trim().replace(/\s+/g, '-');
        if (!headings.has(slug)) headings.set(slug, item); root.append(item); i++; continue;
      }
      if (i + 1 < lines.length && line.includes('|') && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1]) && cells(lines[i + 1]).every(cell => /^:?-{3,}:?$/.test(cell))) {
        const wrap = node('div'); wrap.className = 'table-wrap'; wrap.tabIndex = 0; wrap.setAttribute('role', 'region'); wrap.setAttribute('aria-label', '문서 표');
        const table = node('table'); const head = node('thead'); const tr = node('tr');
        for (const value of cells(line)) { const th = node('th'); th.scope = 'col'; inline(th, value); tr.append(th); } head.append(tr); table.append(head); i += 2;
        const body = node('tbody'); while (i < lines.length && lines[i].includes('|') && lines[i].trim()) { const row = node('tr'); for (const value of cells(lines[i++])) { const td = node('td'); inline(td, value); row.append(td); } body.append(row); } table.append(body); wrap.append(table); root.append(wrap); continue;
      }
      if (/^\s*(?:---+|\*\*\*+)\s*$/.test(line)) { root.append(node('hr')); i++; continue; }
      const list = line.match(/^\s*(?:([-*+])|(\d+)\.)\s+(.+)$/);
      if (list) {
        const container = node(list[2] ? 'ol' : 'ul'); if (list[2]) container.start = Number(list[2]);
        while (i < lines.length) { const match = lines[i].match(/^\s*(?:([-*+])|(\d+)\.)\s+(.+)$/); if (!match || Boolean(match[2]) !== Boolean(list[2])) break; const item = node('li'); inline(item, match[3]); container.append(item); i++; } root.append(container); continue;
      }
      if (/^>/.test(line)) { const quote = node('blockquote'); const body = []; while (i < lines.length && /^>/.test(lines[i])) body.push(lines[i++].replace(/^>\s?/, '')); inline(quote, body.join(' ')); root.append(quote); continue; }
      const body = [line]; i++; while (i < lines.length && !special(lines[i]) && !(i + 1 < lines.length && lines[i].includes('|') && /^\s*\|?\s*:?-{3,}/.test(lines[i + 1]))) body.push(lines[i++]);
      const paragraph = node('p'); inline(paragraph, body.join(' ')); root.append(paragraph);
    }
    return root;
  }
  return { render };
})();
