'use strict';
const $ = (selector, parent = document) => parent.querySelector(selector);
const page = $('#page');
const notice = $('#notice');
let state = { skills: [], servers: [], tasks: [], compatibility: {} };
let currentView = 'overview';
let activeProfile = 'global';
let projects = [];
let workspaceStatus = 'loading';
let workspaceError = '';
let renderedView = '';
const viewDrafts = new Map();
const viewDisclosures = new Map();
let selectedSkill = '';
let selectedPath = 'SKILL.md';
let remoteSkill = null;
let searchQuery = '';
let csrfToken = '';
try {
  const handoff = new URLSearchParams(location.hash.slice(1)).get('session');
  if (handoff && /^[A-Za-z0-9_-]{43}$/.test(handoff)) {
    csrfToken = handoff;
    history.replaceState(null, '', location.pathname + location.search);
    sessionStorage.setItem('joongi-hub-session', handoff);
  } else csrfToken = sessionStorage.getItem('joongi-hub-session') || '';
} catch { /* A disabled browser store does not enable unauthenticated access. */ }
let activeCall = null;
let appView = null;
let searchTimer;
let loadCounter = 0;
let skillCounter = 0;
const expandedServers = new Set();
const toolQueries = new Map();
const skillPresentation = {
  'engineering-playbook': { label: '엔지니어링', summary: '개발·인프라·보안·테스트 규칙' },
  'applying-design-systems': { label: '디자인·UX', summary: '디자인 시스템과 제품 UX 원칙' },
  'usual-korean': { label: '자연스러운 한국어', summary: '문장 교정과 기술 용어 선택' }
};
function shortDescription(text = '', limit = 100) {
  const line = String(text).replace(/\s+/g, ' ').trim();
  const sentence = line.match(/^.*?[.!?。](?:\s|$)/)?.[0]?.trim() || line;
  return sentence.length > limit ? sentence.slice(0, limit - 1) + '…' : sentence;
}
function skillCopy(skill) {
  return skillPresentation[skill.name] || { label: skill.name, summary: shortDescription(skill.description) };
}
const labels = { settings: '연결 설정', projects: '프로젝트 범위', overview: '작업 공간', skills: '스킬 라이브러리', connections: 'MCP 연결', tasks: '실행 작업', compatibility: '지원 범위' };
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'text') node.textContent = value;
    else if (key === 'value') node.value = value;
    else if (key === 'hidden') node.hidden = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child !== undefined && child !== null) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}
function replacePage(...children) { page.replaceChildren(...children.filter(child => child !== null && child !== undefined)); }
function button(text, action, className = '') { return el('button', { type: 'button', class: className, onClick: action }, text); }
function showNotice(message, error = false) {
  notice.textContent = message;
  notice.hidden = !message;
  notice.className = error ? 'notice error' : 'notice';
  notice.setAttribute('role', error ? 'alert' : 'status');
}
async function api(path, options = {}) {
  const headers = { Accept: 'application/json', 'X-Hub-Profile': activeProfile, ...options.headers };
  if (!csrfToken) throw new Error('터미널에서 joongi-hub open으로 관리 화면을 다시 여세요.');
  headers['X-Hub-Token'] = csrfToken;
  if (options.method && options.method !== 'GET') {
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(path, { ...options, headers, cache: 'no-store' });
  if (response.status === 204) return null;
  let data;
  try { data = await response.json(); } catch { throw new Error('서버 응답을 읽을 수 없습니다. Hub가 실행 중인지 확인하세요.'); }
  if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : data.error?.message || data.detail || `요청 실패 (${response.status})`);
  return data;
}
async function run(action, pendingButton) {
  if (pendingButton) pendingButton.disabled = true;
  try { return await action(); } catch (error) { showNotice(error.message, true); }
  finally { if (pendingButton) pendingButton.disabled = false; }
}
function navigate(view) {
  if (appView) { appView.close().catch(() => {}); appView = null; }
  currentView = Object.hasOwn(labels, view) ? view : 'overview';
  location.hash = currentView;
  for (const node of document.querySelectorAll('[data-view]')) {
    if (node.dataset.view === currentView) node.setAttribute('aria-current', 'page');
    else node.removeAttribute('aria-current');
  }
  $('#crumb').textContent = labels[currentView];
  render();
}
async function load({ quiet = false } = {}) {
  const id = ++loadCounter;
  try {
    const [incoming, approvals] = await Promise.all([api('/api/v1/state'), api('/api/v1/approvals')]);
    if (id !== loadCounter) return;
    workspaceStatus = 'ready'; workspaceError = '';
    state = { skills: [], servers: [], tasks: [], compatibility: {}, ...incoming, approvals };
    state.skills = Array.isArray(state.skills) ? state.skills : [];
    state.servers = Array.isArray(state.servers) ? state.servers : [];
    state.tasks = Array.isArray(state.tasks) ? state.tasks : [];
    $('#hub-status').textContent = '로컬에서 실행 중';
    $('#hub-version').textContent = `v${state.version || '0.1.0'}`;
    $('#live-dot').style.background = 'var(--success)';
    if (!quiet) { render(); page.dataset.profile = activeProfile; }
    else if (currentView === 'tasks' && !['TEXTAREA', 'INPUT', 'SELECT'].includes(document.activeElement?.tagName)) renderTasks();
  } catch (error) {
    if (id !== loadCounter) return;
    $('#hub-status').textContent = '연결을 확인하세요';
    $('#live-dot').style.background = 'var(--danger)';
    showNotice(error.message, true);
    if (workspaceStatus !== 'ready') { workspaceStatus = 'error'; workspaceError = error.message; render(); }
  }
}
function title(name, description, action) {
  return el('div', { class: 'page-title' }, el('div', {}, el('h1', {}, name), el('p', {}, description)), action);
}
function badge(text, type = '') { return el('span', { class: `badge ${type}` }, text); }
function empty(heading, description, action) { return el('div', { class: 'empty' }, el('strong', {}, heading), el('p', {}, description), action); }
function statusBadge(server) {
  const status = server.status || 'registered';
  const good = ['connected', 'ready', 'online', 'ok'].includes(status);
  return badge(good ? '연결됨' : ['error', 'failed', 'offline'].includes(status) ? '연결 실패' : server.enabled === false ? '비활성' : '연결 확인 전', good ? 'success' : ['error', 'failed', 'offline'].includes(status) ? 'error' : '');
}
// Keep live editing nodes in memory only. Passwords never enter browser storage.
function rememberDrafts() {
  if (!renderedView) return;
  const previous = viewDrafts.get(renderedView) || new Map();
  for (const node of page.querySelectorAll('[data-preserve]')) {
    if (node.dataset.dirty === 'true' || node.dataset.keepDraft === 'always') previous.set(node.dataset.preserve, node);
    else previous.delete(node.dataset.preserve);
  }
  viewDrafts.set(renderedView, previous);
  viewDisclosures.set(renderedView, new Map([...page.querySelectorAll('details[data-disclosure]')].map(node => [node.dataset.disclosure, node.open])));
}
function render() {
  rememberDrafts();
  if (workspaceStatus !== 'ready') {
    renderedView = '';
    page.removeAttribute('data-profile');
    replacePage(title(workspaceStatus === 'error' ? '작업 공간을 불러올 수 없습니다' : '작업 공간을 불러오는 중',
      workspaceStatus === 'error' ? workspaceError : '선택한 범위의 연결과 스킬을 확인하고 있습니다.'),
      workspaceStatus === 'error' ? button('다시 연결', refreshWorkspace, 'primary') : el('p', { role: 'status' }, '연결 확인 중…'));
    return;
  }
  const key = `${activeProfile}/${currentView}`;
  ({ settings: renderConnectionSettings, projects: renderProjects, overview: renderOverview, skills: renderSkills, connections: renderConnections, tasks: renderTasks, compatibility: renderCompatibility }[currentView])();
  if (state.storage?.temporary) page.prepend(el('aside', { class: 'notice', role: 'status' }, '임시 저장소를 사용 중입니다. 등록 정보가 삭제될 수 있으므로 공용 사용에는 기본 영구 저장소를 사용하세요.', el('code', {}, state.storage.state_dir)));
  for (const [identity, node] of viewDrafts.get(key) || []) {
    const replacement = [...page.querySelectorAll('[data-preserve]')].find(item => item.dataset.preserve === identity);
    if (replacement) replacement.replaceWith(node);
  }
  for (const node of page.querySelectorAll('details[data-disclosure]')) {
    const open = viewDisclosures.get(key)?.get(node.dataset.disclosure); if (open !== undefined) node.open = open;
  }
  renderedView = key;
  page.dataset.profile = activeProfile;
}
async function refreshWorkspace() {
  try { await loadProjects(); await load(); }
  catch (error) {
    showNotice(error.message, true);
    if (workspaceStatus !== 'ready') { workspaceStatus = 'error'; workspaceError = error.message; render(); }
  }
}
function preserveEditor(node, identity, always = false) {
  node.dataset.preserve = identity;
  if (always) node.dataset.keepDraft = 'always';
  node.addEventListener('input', () => { node.dataset.dirty = 'true'; });
  node.addEventListener('change', () => { node.dataset.dirty = 'true'; });
  return node;
}
function discardDraft(identity) {
  for (const [key, drafts] of viewDrafts) if (key.startsWith(`${activeProfile}/`)) {
    const node = drafts.get(identity);
    if (node) { node.dataset.dirty = 'false'; delete node.dataset.keepDraft; }
    drafts.delete(identity);
  }
  for (const node of page.querySelectorAll('[data-preserve]')) if (node.dataset.preserve === identity) {
    node.dataset.dirty = 'false'; delete node.dataset.keepDraft;
  }
}
function renderOverview() {
  const connected = state.servers.filter(s => ['connected', 'ready', 'online', 'ok'].includes(s.status)).length;
  const toolCount = state.servers.reduce((n, server) => n + (server.tools?.length || 0), 0);
  const working = state.tasks.filter(t => ['working', 'input_required'].includes(t.status)).length;
  const skillRows = state.skills.slice(0, 4).map(skill => el('div', { class: 'item-row' }, el('div', {}, el('strong', {}, skillCopy(skill).label), el('p', {}, skillCopy(skill).summary)), button('읽기 →', () => { selectedSkill = skill.name; navigate('skills'); }, 'quiet small')));
  const serverRows = state.servers.slice(0, 4).map(server => el('div', { class: 'item-row' }, el('div', {}, el('strong', {}, server.name || server.id), el('p', {}, server.transport === 'stdio' ? '로컬 프로세스 · stdio' : server.url)), statusBadge(server)));
  replacePage(
    title('나의 도구를 연결하는 곳', '연결 상태를 확인하고 필요한 스킬과 도구를 찾으세요.'),
    hubSearch(),
    state.tasks.some(t => ['working', 'input_required'].includes(t.status)) ? el('section', { class: 'attention-line' }, el('strong', {}, '진행 중인 작업이 있습니다'), button('작업 확인', () => navigate('tasks'))) : null,
    state.servers.some(server => server.error || server.auth_status?.login_required) ? el('section', { class: 'attention-line' }, el('strong', {}, '연결 또는 로그인이 필요한 MCP가 있습니다'), button('연결 확인', () => navigate('connections'))) : null,
    !state.servers.length ? el('section', { class: 'intro-panel', 'aria-label': 'Hub 사용 흐름' },
      el('div', {}, el('div', { class: 'eyebrow' }, 'YOUR LOCAL WORKSPACE'), el('h2', {}, '익숙한 에이전트에,', el('br'), '나의 작업 방식을.'), el('p', {}, '클라이언트는 Hub 하나에 연결합니다. 스킬은 지침을 제공하고, 연결된 MCP는 실제 작업을 수행합니다.'), button(state.servers.length ? '연결 관리 →' : '첫 MCP 연결하기 →', () => { navigate('connections'); if (!state.servers.length) openConnectionForm(); }, 'primary')),
      el('div', { class: 'flow' }, el('div', { class: 'flow-node' }, '내가 사용하는', el('strong', {}, 'AI 에이전트')), el('span', { class: 'flow-arrow', 'aria-hidden': 'true' }, '→'), el('div', { class: 'flow-node flow-hub' }, '하나의 접점', el('strong', {}, 'Joongi Hub')), el('span', { class: 'flow-arrow', 'aria-hidden': 'true' }, '→'), el('div', { class: 'flow-tail' }, el('div', { class: 'flow-node' }, '스킬 · 작업 지침'), el('div', { class: 'flow-node' }, 'MCP · 실행 도구')))) : null,
    el('div', { class: 'summary-line' }, el('span', {}, el('strong', {}, `${state.skills.length}`), '스킬'), el('span', {}, el('strong', {}, `${connected}/${state.servers.length}`), 'MCP 연결됨'), el('span', {}, el('strong', {}, `${toolCount}`), '도구 발견됨'), el('span', {}, el('strong', {}, `${working}`), '진행 중인 작업')),
    el('div', { class: 'split-overview' },
      el('section', { class: 'section' }, el('div', { class: 'section-header' }, el('h2', {}, '스킬 라이브러리'), button('전체 보기 →', () => navigate('skills'), 'quiet small')), skillRows.length ? skillRows : empty('아직 등록된 스킬이 없습니다', 'skills/ 디렉터리에 SKILL.md가 포함된 스킬을 추가하세요.')),
      el('section', { class: 'section' }, el('div', { class: 'section-header' }, el('h2', {}, 'MCP 연결'), button('관리 →', () => navigate('connections'), 'quiet small')), serverRows.length ? serverRows : empty('첫 연결을 기다리고 있어요', '사용하는 MCP 서버를 등록하고 도구를 확인하세요.', button('MCP 등록', () => { navigate('connections'); openConnectionForm(); })))));
}
function hubSearch() {
  const input = el('input', { type: 'search', placeholder: '스킬·도구 검색', 'aria-label': '스킬과 도구 통합 검색', maxlength: '1000' });
  const results = el('div', { 'aria-live': 'polite' });
  const submit = el('button', { type: 'submit' }, '검색');
  return el('section', { class: 'hub-search', 'aria-label': '통합 검색' }, el('form', { class: 'hub-search-form', onSubmit: event => {
    event.preventDefault(); run(async () => {
      const data = await api(`/api/v1/search?q=${encodeURIComponent(input.value)}`);
      const rows = Array.isArray(data) ? data : data.results || [];
      results.replaceChildren(...(rows.length ? rows.map(item => el('div', { class: 'item-row' }, el('div', {}, el('div', { class: 'item-title' }, el('strong', {}, item.name), badge(item.kind === 'skill' ? '스킬' : 'MCP 도구')), el('p', { class: 'description-preview' }, shortDescription(item.description))), button(item.kind === 'skill' ? '읽기 →' : '실행 →', () => {
        if (item.kind === 'skill') { remoteSkill = item.server ? item : null; selectedSkill = item.name; selectedPath = 'SKILL.md'; navigate('skills'); }
        else {
          const server = state.servers.find(s => s.id === item.server || item.name.startsWith(`${s.id}__`));
          const short = server ? item.name.slice(server.id.length + 2) : item.name;
          const tool = server?.tools?.find(t => t.name === short);
          if (server && tool) { navigate('connections'); renderCallPanel({ server, tool }); }
          else showNotice('연결 상태를 새로고침한 뒤 다시 검색하세요.', true);
        }
      }, 'small'))) : [empty('검색 결과가 없습니다', '다른 검색어를 사용하거나 MCP 연결에서 도구를 먼저 확인하세요.')]));
    }, submit);
  } }, input, submit), results);
}
function matchingSkills() {
  const query = searchQuery.trim().toLowerCase();
  return [...state.skills, ...(remoteSkill ? [remoteSkill] : [])].filter(skill => `${skill.name} ${skill.description}`.toLowerCase().includes(query));
}
function renderSkills() {
  const input = el('input', { type: 'search', id: 'skill-search', placeholder: '이름이나 작업 내용으로 스킬 검색', 'aria-label': '스킬 검색', value: searchQuery, onInput: event => { searchQuery = event.target.value; clearTimeout(searchTimer); searchTimer = setTimeout(renderSkillList, 150); } });
  const searchIcon = el('span', { 'aria-hidden': 'true', class: 'search-glyph' }, '⌕');
  replacePage(title('스킬 라이브러리', '작업에 맞는 지침을 선택하세요.', button('설치 관리', openSkillManager)), el('div', { id: 'skill-manager', hidden: true, 'data-preserve': 'skill-manager' }), el('div', { class: 'search-wrap' }, searchIcon, input), el('div', { class: 'skill-layout' }, el('div', { class: 'skill-list', id: 'skill-list' }), el('section', { class: 'detail', id: 'skill-detail', 'aria-label': '스킬 상세' })));
  renderSkillList();
  if (selectedSkill && [...state.skills, ...(remoteSkill ? [remoteSkill] : [])].some(s => s.name === selectedSkill)) showSkill(selectedSkill, selectedPath);
  else $('#skill-detail').replaceChildren(el('div', { class: 'detail-placeholder' }, '왼쪽에서 스킬을 선택하면 지침을 읽을 수 있습니다.'));
}
function renderSkillList() {
  const list = $('#skill-list'); if (!list) return;
  const skills = matchingSkills();
  list.replaceChildren(...(skills.length ? skills.map(skill => el('button', { type: 'button', class: 'skill-button', 'aria-pressed': String(selectedSkill === skill.name), onClick: () => showSkill(skill.name) }, el('div', { class: 'item-title' }, el('strong', {}, skillCopy(skill).label), badge(skill.server ? '원격 스킬' : `${skill.files?.length || 1}개 문서`)), el('p', { class: 'description-preview' }, skillCopy(skill).summary), el('small', { class: 'skill-id' }, skill.name))) : [empty('검색 결과가 없습니다', '다른 이름이나 작업 내용으로 검색해보세요.')]));
}
async function showSkill(name, path = 'SKILL.md') {
  selectedSkill = name; selectedPath = path; renderSkillList();
  const id = ++skillCounter;
  const detail = $('#skill-detail'); if (!detail) return;
  const skill = [...state.skills, ...(remoteSkill ? [remoteSkill] : [])].find(s => s.name === name);
  const files = (skill?.files || ['SKILL.md']).map(file => typeof file === 'string' ? file : file.path).filter(Boolean);
  if (!files.includes(path)) files.unshift(path);
  const select = el('select', { 'aria-label': '참조 문서 선택', onChange: event => showSkill(name, event.target.value) }, files.map(file => el('option', { value: file }, file)));
  select.value = path;
  detail.replaceChildren(el('div', { class: 'detail-header' }, el('strong', {}, skillCopy(skill || { name }).label), select), el('div', { class: 'detail-body', id: 'skill-content' }, el('div', { class: 'loading-line' })));
  try {
    let data;
    if (skill?.server) {
      const result = await api('/api/v1/call', { method: 'POST', body: JSON.stringify({ name: 'hub_read_resource', arguments: { uri: skill.uri } }) });
      const encoded = result.content?.find(item => item.type === 'text')?.text || '{}';
      let resource; try { resource = JSON.parse(encoded); } catch { resource = { contents: [{ text: encoded }] }; }
      data = { content: (resource.contents || []).map(item => item.text || '[텍스트가 아닌 리소스]').join('\n\n') };
    } else data = await api(`/api/v1/skills/${encodeURIComponent(name)}?path=${encodeURIComponent(path)}`);
    if (id === skillCounter && $('#skill-content')) {
      if (data.blob) {
        const download = button('파일 내려받기', () => {
          const bytes = Uint8Array.from(atob(data.blob), char => char.charCodeAt(0));
          const url = URL.createObjectURL(new Blob([bytes], { type: data.mimeType || 'application/octet-stream' }));
          const link = el('a', { href: url, download: path.split('/').pop() }); link.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
        }, 'small');
        $('#skill-content').replaceChildren(el('p', {}, `바이너리 참조 파일 · ${data.mimeType || 'application/octet-stream'}`), download);
      } else {
        const content = data.content ?? '빈 문서입니다.';
        const metadata = path === 'SKILL.md' && content.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);
        const body = metadata ? content.slice(metadata[0].length).trimStart() : content;
        $('#skill-content').replaceChildren(...[
          metadata ? el('details', { class: 'document-meta' }, el('summary', {}, '스킬 정보'), el('pre', {}, metadata[1])) : null,
          documentView(body, name, path, files)].filter(Boolean));
      }
    }
  } catch (error) { if (id === skillCounter && $('#skill-content')) $('#skill-content').replaceChildren(el('p', { class: 'connection-error' }, error.message)); }
}
function documentView(body, name, path, files) {
  const content = el('div', { class: 'document-view' });
  const raw = el('pre', { class: 'document-body', hidden: true }, body);
  const formatted = window.JoongiMarkdown.render(body, { reference: target => {
    const parts = path.split('/').slice(0, -1);
    for (const part of target.split('#')[0].split('/')) {
      if (part === '..') { if (!parts.length) return; parts.pop(); }
      else if (part && part !== '.') parts.push(part);
    }
    const next = parts.join('/');
    if (files.includes(next)) showSkill(name, next);
    else showNotice('스킬에 포함된 참조 문서만 열 수 있습니다.', true);
  } });
  const toggle = button('원문 보기', () => {
    raw.hidden = !raw.hidden; formatted.hidden = !raw.hidden;
    toggle.textContent = raw.hidden ? '원문 보기' : '읽기 보기';
    toggle.setAttribute('aria-pressed', String(!raw.hidden));
  }, 'quiet small');
  toggle.setAttribute('aria-pressed', 'false');
  content.append(el('div', { class: 'document-toolbar' }, toggle), formatted, raw);
  return content;
}
function field(label, name, control, hint = '', full = false) {
  control.id = name; control.name = name;
  return el('div', { class: `form-field${full ? ' full' : ''}` }, el('label', { for: name }, label), control, hint ? el('small', {}, hint) : null);
}
function renderConnections() {
  replacePage(title('MCP 연결', '등록한 서버에서 도구를 찾고, 연결 상태와 지원 기능을 확인하세요.', button('+ MCP 등록', openConnectionForm, 'primary')), approvalPanel(), preserveEditor(el('div', { id: 'connection-form', hidden: true }), 'new-connection'), el('div', { id: 'connections-list' }), el('div', { id: 'call-area' }));
  const list = $('#connections-list');
  if (!state.servers.length) list.replaceChildren(empty('이 저장소에 등록된 MCP가 없습니다', `이전에 등록했다면 저장 경로가 같은지 확인하세요. 현재: ${state.storage?.state_dir || '연결 설정에서 확인'} · stdio와 HTTP는 같은 저장 경로에서 목록을 공유합니다.`, button('서버 등록하기', openConnectionForm)));
  else list.replaceChildren(...state.servers.map(connection));
  if (activeCall) renderCallPanel(activeCall);
}
function approvalPanel() {
  const rows = state.approvals || [];
  return el('section', { class: 'section', 'aria-label': '도구 호출 승인' },
    el('h2', {}, '도구 호출 승인'),
    el('p', {}, '서버·도구·인수를 확인하세요. 승인은 이 요청 한 번에만 적용되며, 승인 후 에이전트가 같은 호출을 다시 실행해야 합니다.'),
    button('승인 요청 새로고침', () => run(() => load()), 'small'),
    ...(rows.length ? rows.map(row => el('section', { class: 'form-panel' },
      el('h3', {}, `${row.server} · ${row.tool}`),
      el('p', {}, row.status === 'approved' ? '승인됨 · 동일한 요청을 다시 실행하세요.' : '검토 대기 · 5분 후 만료'),
      el('details', {}, el('summary', {}, '실행할 인수와 이어가기 입력'), el('pre', {}, JSON.stringify({ arguments: row.arguments, continuation: row.continuation }, null, 2))),
      row.status === 'pending' ? el('div', { class: 'form-actions' }, ...[true, false].map(approve => button(approve ? '이 호출 한 번 승인' : '거절', () => run(async () => { await api(`/api/v1/approvals/${encodeURIComponent(row.id)}`, { method: 'POST', body: JSON.stringify({ approve }) }); await load(); }), approve ? 'primary small' : 'quiet small'))) : null
    )) : [el('p', {}, '검토할 호출이 없습니다. 원격 도구를 실행하면 필요한 승인 요청이 여기에 표시됩니다.')])
  );
}
function connection(server) {
  const probe = button('연결 확인', async () => run(async () => { showNotice(`${server.name || server.id}에서 도구를 확인하고 있습니다.`); await api(`/api/v1/servers/${encodeURIComponent(server.id)}/probe`, { method: 'POST', body: '{}' }); await load(); showNotice('연결 정보를 갱신했습니다.'); }, probe), 'small');
  const remove = button('제거', async () => {
    const row = remove.closest('.connection');
    const confirmation = el('div', { class: 'notice mt-4' }, el('p', {}, `${server.name || server.id} 연결을 제거할까요? 서버 프로그램 자체는 삭제하지 않습니다.`), el('div', { class: 'form-actions' }, button('연결 제거', () => run(async () => { await api(`/api/v1/servers/${encodeURIComponent(server.id)}`, { method: 'DELETE' }); activeCall = null; await load(); showNotice('연결을 제거했습니다.'); }), 'danger'), button('취소', () => confirmation.remove())));
    remove.disabled = true; row.append(confirmation); confirmation.querySelector('button:last-child').addEventListener('click', () => { remove.disabled = false; });
  }, 'small quiet danger');
  const tools = server.tools || [];
  const configuration = server.transport === 'http' ? server.url : [server.command, ...(server.args || [])].join(' ');
  const policyIdentity = `tool-policy:${server.id}`;
  const settings = preserveEditor(el('details', { class: 'connection-settings', 'data-disclosure': `settings:${server.id}` }, el('summary', {}, '연결 설정'),
    el('pre', {}, configuration), el('p', { class: 'mono' }, `규격 ${server.protocol_version || '자동 감지'}`)), policyIdentity);
  const allowed = el('textarea', { rows: '3', 'aria-label': `${server.name || server.id} 허용 도구`, value: (server.policy?.allowed_tools || []).join('\n'), placeholder: '신뢰한 읽기 도구 이름을 한 줄에 하나씩' });
  const denied = el('textarea', { rows: '2', 'aria-label': `${server.name || server.id} 차단 도구`, value: (server.policy?.denied_tools || []).join('\n') });
  const savePolicy = button('도구 정책 저장', () => run(async () => {
    const keys = ['id', 'name', 'transport', 'command', 'args', 'env', 'url', 'headers', 'auth', 'protocol_version', 'enabled'];
    const payload = Object.fromEntries(Object.entries(server).filter(([key]) => keys.includes(key)));
    payload.policy = { allowed_tools: allowed.value.split(/\s+/).filter(Boolean), denied_tools: denied.value.split(/\s+/).filter(Boolean) };
    await api('/api/v1/servers', { method: 'POST', body: JSON.stringify(payload) }); discardDraft(policyIdentity); await load(); showNotice('도구 정책을 저장했습니다.');
  }), 'small');
  settings.append(el('p', {}, '인증을 쓰는 연결은 목록에 없는 도구 호출마다 승인이 필요합니다. 정책을 저장하면 인증 없는 연결에도 적용합니다. 읽기 표시만으로 자동 허용하지 않습니다. *는 모든 도구를 뜻하므로 신뢰 범위를 확인하세요.'), el('label', {}, '항상 허용할 도구', allowed), el('label', {}, '차단할 도구', denied), savePolicy);
  return el('section', { class: 'connection' }, el('div', { class: 'connection-head' },
    el('div', {}, el('div', { class: 'item-title' }, el('h3', {}, server.name || server.id), statusBadge(server), badge(server.transport || 'stdio'))),
    el('div', { class: 'connection-actions' }, probe, remove)),
    server.error ? el('p', { class: 'connection-error' }, typeof server.error === 'string' ? server.error : JSON.stringify(server.error)) : null,
    settings, authenticationPanel(server), tools.length ? serverTools(server, tools) : null);
}
function serverTools(server, tools) {
  const disclosure = el('details', { class: 'server-tools', 'data-server': server.id },
    el('summary', {}, `도구 ${tools.length}개`));
  disclosure.open = expandedServers.has(server.id);
  disclosure.addEventListener('toggle', () => {
    if (disclosure.open) expandedServers.add(server.id); else expandedServers.delete(server.id);
  });
  const rows = el('div', { class: 'tool-list' });
  const draw = query => {
    toolQueries.set(server.id, query);
    const matches = tools.filter(tool => `${tool.name} ${tool.description || ''}`.toLowerCase().includes(query.toLowerCase()));
    rows.replaceChildren(...matches.map(tool => el('div', { class: 'tool-row' },
      el('div', {}, el('code', {}, tool.name), el('p', { class: 'description-preview' }, shortDescription(tool.description))),
      button('실행', () => renderCallPanel({ server, tool }), 'small'))));
    if (!matches.length) rows.append(el('p', { class: 'muted' }, '일치하는 도구가 없습니다.'));
  };
  const input = el('input', { type: 'search', placeholder: '도구 검색',
    'aria-label': `${server.name || server.id} 도구 검색`, value: toolQueries.get(server.id) || '',
    onInput: event => draw(event.target.value) });
  draw(input.value);
  disclosure.append(input, rows);
  return disclosure;
}
function openConnectionForm() {
  const profile = activeProfile;
  const target = $('#connection-form'); if (!target) return;
  target.hidden = false; target.dataset.dirty = 'true';
  if (target.children.length) { $('#server-name').focus(); return; }
  const transport = el('select', {}, el('option', { value: 'stdio' }, '로컬 프로세스 (stdio)'), el('option', { value: 'http' }, 'HTTP 서버'));
  const stdioFields = el('div', { class: 'form-field full form-grid', id: 'stdio-fields' }, field('실행 명령', 'server-command', el('input', { placeholder: '예: uvx 또는 npx', autocomplete: 'off' }), '명령은 셸을 거치지 않고 실행됩니다.'), field('실행 인자', 'server-args', el('input', { value: '[]', placeholder: '["package-name"]' }), 'JSON 배열로 입력하세요.'));
  const httpField = field('MCP 주소', 'server-url', el('input', { type: 'url', placeholder: 'http://127.0.0.1:3000/mcp' }), '실제로 사용하는 MCP 접속 주소를 입력하세요.', true);
  httpField.hidden = true;
  transport.addEventListener('change', () => { stdioFields.hidden = transport.value !== 'stdio'; httpField.hidden = transport.value !== 'http'; });
  const submit = el('button', { type: 'submit', class: 'primary' }, '연결 등록');
  const form = el('form', { class: 'form-panel', onSubmit: event => { event.preventDefault(); run(async () => {
    let args = []; try { args = JSON.parse($('#server-args').value); } catch { throw new Error('실행 인자는 JSON 배열로 입력하세요. 예: ["package-name"]'); }
    if (!Array.isArray(args) || args.some(a => typeof a !== 'string')) throw new Error('실행 인자는 문자열로 이루어진 JSON 배열이어야 합니다.');
    const name = $('#server-name').value.trim();
    const id = $('#server-id').value.trim();
    const payload = { id, name, transport: transport.value, enabled: true, protocol_version: $('#server-version').value };
    if (transport.value === 'stdio') { payload.command = $('#server-command').value.trim(); payload.args = args; if (!payload.command) throw new Error('실행 명령을 입력하세요.'); }
    else { payload.url = $('#server-url').value.trim(); if (!payload.url) throw new Error('MCP 주소를 입력하세요.'); }
    await api('/api/v1/servers', { method: 'POST', headers: { 'X-Hub-Profile': profile }, body: JSON.stringify(payload) }); if (profile !== activeProfile) return; discardDraft('new-connection'); await load(); showNotice('서버를 등록했습니다. 연결 확인을 눌러 도구를 가져오세요.');
  }, submit); } }, el('h2', {}, '새 MCP 서버'), el('p', {}, '연결할 서버의 출처와 실행 명령을 확인하세요. 등록 후 연결 확인 시 로컬 프로세스가 실행될 수 있습니다.'), el('div', { class: 'form-grid' }, field('표시 이름', 'server-name', el('input', { required: true, maxlength: '100', placeholder: '예: 코드 그래프' })), field('고유 ID', 'server-id', el('input', { required: true, pattern: '[a-z0-9][a-z0-9\\-]*', maxlength: '48', placeholder: '예: codegraph' }), '영문 소문자, 숫자, 하이픈'), field('연결 방식', 'server-transport', transport), field('프로토콜 버전', 'server-version', el('select', {}, el('option', { value: 'auto' }, '자동 감지'), el('option', { value: '2026-07-28' }, '2026-07-28'), el('option', { value: '2025-11-25' }, '2025-11-25'), el('option', { value: '2025-06-18' }, '2025-06-18'))), stdioFields, httpField), el('div', { class: 'form-actions' }, submit, button('취소', () => { discardDraft('new-connection'); target.hidden = true; target.replaceChildren(); })));
  target.replaceChildren(form); $('#server-name').focus();
}
function renderCallPanel(selection) {
  if (appView) { appView.close().catch(() => {}); appView = null; }
  activeCall = selection;
  const { server, tool } = selection;
  const area = $('#call-area'); if (!area) return;
  const qualified = tool.name.startsWith(`${server.id}__`) ? tool.name : `${server.id}__${tool.name}`;
  const args = el('textarea', { id: 'tool-arguments', spellcheck: 'false', 'aria-label': '도구 입력 JSON', value: '{}' });
  const result = el('div', { id: 'tool-result', hidden: true, class: 'call-result', 'aria-live': 'polite' });
  const appArea = el('section', { class: 'app-area', 'aria-label': 'MCP App' });
  const openApp = (tool._meta?.ui?.resourceUri || tool._meta?.['ui/resourceUri']) ? button('App 열기', () => run(async () => {
    const input = JSON.parse(args.value);
    appView = await window.JoongiApps.mount(appArea, { server: server.id, tool: tool.name,
      arguments: input, api });
  }), 'small') : null;
  const taskToggle = el('input', { type: 'checkbox', id: 'tool-task', class: 'task-checkbox' });
  const execute = button('도구 실행', () => run(async () => {
    let parsed; try { parsed = JSON.parse(args.value); } catch { throw new Error('도구 입력이 올바른 JSON이 아닙니다.'); }
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') throw new Error('도구 입력은 JSON 객체여야 합니다.');
    result.hidden = false; result.replaceChildren(el('p', { class: 'muted' }, '실행 중입니다…'));
    try { const data = await api('/api/v1/call', { method: 'POST', body: JSON.stringify({ name: qualified, arguments: parsed, task: taskToggle.checked }) }); result.replaceChildren(el('pre', {}, JSON.stringify(data, null, 2))); if (appView && !data.taskId) await appView.updateResult(data); await load({ quiet: true }); }
    catch (error) { result.replaceChildren(el('p', { class: 'connection-error' }, error.message)); throw error; }
  }, execute), 'primary');
  area.replaceChildren(el('section', { class: 'form-panel call-panel' }, el('div', { class: 'section-header' }, el('h3', {}, qualified), button('닫기', () => { if (appView) { appView.close().catch(() => {}); appView = null; } activeCall = null; area.replaceChildren(); }, 'quiet small')), el('p', {}, server.name || server.id), el('details', {}, el('summary', {}, '도구 설명'), el('p', {}, tool.description || '등록된 설명이 없습니다.')), el('details', {}, el('summary', {}, '입력 스키마'), el('pre', {}, JSON.stringify(tool.inputSchema || {}, null, 2))), args, el('label', { for: 'tool-task', class: 'label-normal' }, taskToggle, '백그라운드 작업으로 실행'), execute, openApp, appArea, result));
  area.scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'start' }); args.focus();
}
function renderTasks() {
  const statuses = { working: ['실행 중', 'warning'], input_required: ['입력 대기', 'warning'], completed: ['완료', 'success'], failed: ['실패', 'error'], cancelled: ['취소됨', ''] };
  const rows = state.tasks.map(task => {
    const id = task.taskId || task.id;
    const [label, type] = statuses[task.status] || [task.status || '알 수 없음', ''];
    const cancel = button('취소', () => run(async () => { await api(`/api/v1/tasks/${encodeURIComponent(id)}/cancel`, { method: 'POST', body: '{}' }); await load(); }, cancel), 'small');
    const output = task.result ?? task.error;
    const inputs = task.status === 'input_required' ? taskInput(task) : null;
    return el('tr', {}, el('td', {}, el('code', {}, task.name || task.tool || id), el('small', { class: 'mono' }, id)), el('td', {}, badge(label, type)), el('td', {}, task.createdAt || task.created_at ? new Date(task.createdAt || task.created_at).toLocaleString('ko-KR') : '기록 없음'), el('td', {}, ['working', 'input_required'].includes(task.status) ? cancel : null, inputs, output !== undefined ? el('details', { class: 'task-details' }, el('summary', {}, '결과 보기'), el('pre', {}, typeof output === 'string' ? output : JSON.stringify(output, null, 2))) : task.statusMessage || task.message || ''));
  });
  replacePage(title('실행 작업', '백그라운드 실행 상태와 결과를 확인하세요. 실행 중에는 자동으로 갱신됩니다.'), rows.length ? el('div', { class: 'table-wrap' }, el('table', {}, el('thead', {}, el('tr', {}, ['작업', '상태', '생성 시간', '결과 / 동작'].map(s => el('th', { scope: 'col' }, s)))), el('tbody', {}, rows))) : empty('아직 실행 작업이 없습니다', 'MCP 도구를 백그라운드 작업으로 실행하면 진행 상태와 결과가 여기에 표시됩니다.', button('도구 찾기 →', () => navigate('connections'))));
}
function taskInput(task) {
  const requests = task.inputRequests || {};
  const sample = Object.fromEntries(Object.keys(requests).map(key => [key, { action: 'accept', content: {} }]));
  const input = el('textarea', { 'aria-label': '작업 입력 응답 JSON', value: JSON.stringify(sample, null, 2) });
  return el('details', { open: '', class: 'task-input' }, el('summary', {}, '작업에 필요한 입력'),
    el('pre', {}, JSON.stringify(requests, null, 2)), input,
    button('입력 보내기', () => run(async () => {
      const inputResponses = JSON.parse(input.value);
      await api(`/api/v1/tasks/${encodeURIComponent(task.taskId)}/input`, { method: 'POST', body: JSON.stringify({ inputResponses }) });
      await load();
    }), 'small'));
}
function renderCompatibility() {
  const matrix = [
    ['2025-06-18 / 2025-11-25', '초기화 기반', 'initialize로 기능을 협상하는 클라이언트와 서버'],
    ['2026-07-28', '요청별 메타데이터', 'server/discover와 요청별 버전·기능 정보를 사용하는 연결'],
    ['Skills', '지침 조회', '로컬 스킬 검색과 참조 파일 조회. 클라이언트의 자동 활성화는 별도'],
    ['MCP Apps', '로컬 샌드박스 · 리소스 전달', 'App 열기로 직접 조작. 외부 클라이언트에는 해당 호스트의 Apps 지원 필요'],
    ['Tasks', '비동기 실행 · 입력과 재개', '입력 요청을 제출하고 실행을 이어갑니다. 버전별 지원 범위를 확인하세요.']
  ];
  replacePage(title('지원 범위', '프로토콜 버전과 확장 기능을 구분해서 확인하세요.'), el('p', { class: 'protocol-intro' }, '클라이언트와 서버 양쪽의 지원 범위가 맞아야 기능을 사용할 수 있습니다. 지원하지 않는 기능은 연결했다고 자동으로 추가되지 않습니다.'), el('div', { class: 'table-wrap' }, el('table', {}, el('thead', {}, el('tr', {}, ['규격 / 기능', '연결 방식', '확인할 내용'].map(s => el('th', { scope: 'col' }, s)))), el('tbody', {}, matrix.map(row => el('tr', {}, row.map((cell, i) => el('td', {}, i === 0 ? el('strong', {}, cell) : cell))))))), el('details', { class: 'compat-detail', open: '' }, el('summary', {}, '현재 Hub가 보고하는 지원 정보'), el('pre', {}, JSON.stringify(state.compatibility || {}, null, 2))), el('section', { class: 'section' }, el('h2', {}, '연결별 실제 기능'), state.servers.length ? state.servers.map(server => el('details', { class: 'compat-detail' }, el('summary', {}, `${server.name || server.id} · ${server.protocol_version || '연결 확인 전'}`), el('pre', {}, JSON.stringify(server.capabilities || {}, null, 2)))) : el('p', { class: 'protocol-intro mt-4' }, 'MCP 서버를 등록하고 연결 확인을 하면 기능 협상 결과를 볼 수 있습니다.')));
}
for (const node of document.querySelectorAll('[data-view]')) node.addEventListener('click', () => navigate(node.dataset.view));
$('#refresh').addEventListener('click', event => run(refreshWorkspace, event.currentTarget));
window.addEventListener('hashchange', () => { const next = location.hash.slice(1); if (Object.hasOwn(labels, next) && next !== currentView) navigate(next); });
currentView = Object.hasOwn(labels, location.hash.slice(1)) ? location.hash.slice(1) : 'overview';
for (const node of document.querySelectorAll('[data-view]')) if (node.dataset.view === currentView) node.setAttribute('aria-current', 'page');
$('#crumb').textContent = labels[currentView];
refreshWorkspace();
setInterval(() => { if (workspaceStatus === 'ready' && !document.hidden && (currentView === 'tasks' || state.tasks.some(task => ['working', 'input_required'].includes(task.status)))) load({ quiet: true }); }, 4000);

async function loadProjects() {
  const data = await api('/api/v1/projects', { headers: { 'X-Hub-Profile': 'global' } });
  projects = data.projects || [];
  const select = $('#profile-select');
  select.replaceChildren(el('option', { value: 'global' }, '공용'), ...projects.map(p => el('option', { value: p.id }, p.name || p.id)));
  if (activeProfile !== 'global' && !projects.some(p => p.id === activeProfile)) resetProfile('global');
  select.value = activeProfile;
}
function resetProfile(profile) {
  activeProfile = profile;
  workspaceStatus = 'loading'; workspaceError = '';
  state = { skills: [], servers: [], tasks: [], compatibility: {} };
  viewDrafts.clear(); viewDisclosures.clear(); renderedView = '';
  ++loadCounter; ++skillCounter;
  if (appView) { appView.close().catch(() => {}); appView = null; }
  selectedSkill = ''; remoteSkill = null; activeCall = null; searchQuery = '';
  expandedServers.clear(); toolQueries.clear();
  render();
}
$('#profile-select').addEventListener('change', event => run(async () => {
  resetProfile(event.target.value);
  showNotice(''); await load();
}));
function choices(items, checked = []) {
  const node = el('div', { class: 'choice-list' }, items.map(item => {
    const value = typeof item === 'string' ? item : item.id;
    const control = el('input', { type: 'checkbox', value }); control.checked = checked.includes(value);
    return el('label', {}, control, typeof item === 'string' ? item : item.name || value);
  }));
  node.values = () => [...node.querySelectorAll('input:checked')].map(input => input.value);
  return node;
}
function renderProjects() {
  const target = preserveEditor(el('div', { id: 'project-form' }), 'project-form');
  replacePage(title('프로젝트 범위', '프로젝트마다 사용할 공용 스킬과 MCP를 선택하세요.', button('+ 프로젝트', () => run(() => editProject(target)))) , target,
    ...projects.map(project => el('section', { class: 'connection' }, el('div', { class: 'connection-head' }, el('div', {}, el('h2', {}, project.name || project.id), el('p', { class: 'mono' }, project.root)), el('div', { class: 'form-actions' }, button('설정', () => run(() => editProject(target, project))), button('등록 해제', () => run(async () => {
      await api(`/api/v1/projects/${encodeURIComponent(project.id)}`, { method: 'DELETE', headers: { 'X-Hub-Profile': 'global' } });
      await loadProjects(); await load(); showNotice('등록을 해제했습니다. 프로젝트 파일은 보존했습니다.');
    }), 'quiet'))), el('p', {}, `공용 스킬 ${project.common_skills.length}개 · 공용 MCP ${project.common_servers.length}개`),
    el('details', {}, el('summary', {}, '에이전트 연결 설정'), el('p', {}, '이 프로젝트의 MCP 설정에 아래 command와 args를 사용하세요. 다른 범위의 Hub 연결은 함께 등록하지 않는 것을 권장합니다.'), el('pre', {}, JSON.stringify(project.connection, null, 2))))),
    projects.length ? null : empty('등록한 프로젝트가 없습니다', '프로젝트 파일을 옮기지 않고, 선택한 공용 도구와 함께 사용할 수 있습니다.'));
}
async function editProject(target, project = {}) {
  const global = await api('/api/v1/state', { headers: { 'X-Hub-Profile': 'global' } });
  const id = el('input', { required: true, pattern: '[a-z0-9][a-z0-9\\-]*', maxlength: '48', value: project.id || '' });
  if (project.id) id.readOnly = true;
  const name = el('input', { required: true, value: project.name || '' });
  const root = el('input', { required: true, value: project.root || '', placeholder: '/mnt/d/Project/my-project' });
  const skills = choices(global.skills.map(s => s.name), project.common_skills);
  const servers = choices(global.servers, project.common_servers);
  const save = el('button', { type: 'submit', class: 'primary' }, '범위 저장');
  target.replaceChildren(el('form', { class: 'form-panel', onSubmit: event => { event.preventDefault(); run(async () => {
    const payload = { id: id.value, name: name.value, root: root.value, common_skills: skills.values(), common_servers: servers.values() };
    if (project.skill_paths) payload.skill_paths = project.skill_paths;
    await api('/api/v1/projects', { method: 'POST', headers: { 'X-Hub-Profile': 'global' }, body: JSON.stringify(payload) });
    discardDraft('project-form'); await loadProjects(); render(); showNotice('프로젝트 범위를 저장했습니다. 위의 작업 범위에서 선택하세요.');
  }, save); } }, el('h2', {}, project.id ? '프로젝트 설정' : '프로젝트 등록'), el('div', { class: 'form-grid' }, field('ID', 'project-id', id), field('이름', 'project-name', name), field('프로젝트 경로', 'project-root', root, '현재 컴퓨터에 있는 절대 경로', true)), el('h3', {}, '가져올 공용 스킬'), skills, el('h3', {}, '가져올 공용 MCP'), servers,
  el('p', { class: 'muted' }, '프로젝트의 .agents/skills 등에서 같은 이름의 스킬을 찾으면 프로젝트 스킬을 우선합니다. 에이전트가 직접 읽는 전역 스킬의 우선순위는 각 에이전트 설정을 따릅니다.'), el('div', { class: 'form-actions' }, save, button('닫기', () => { discardDraft('project-form'); target.replaceChildren(); }))));
  target.dataset.dirty = 'true'; id.focus();
}
async function openSkillManager() {
  const target = $('#skill-manager'); target.hidden = false;
  target.dataset.keepDraft = 'always';
  const profile = activeProfile;
  await run(async () => {
    const info = await api('/api/v1/skill-management/status');
    const names = choices([...new Set([...info.available, ...info.installed.map(item => item.name)])], info.available);
    const agents = choices(info.agents);
    const operation = el('select', { 'aria-label': '스킬 관리 작업' }, ...[['install', '설치'], ['update', '업데이트'], ['remove', '제거'], ['pin', '버전 고정'], ['unpin', '고정 해제']].map(([value, label]) => el('option', { value }, label)));
    const refresh = el('input', { type: 'checkbox' });
    const review = el('div', { 'aria-live': 'polite' });
    let revision = 0;
    const invalidate = () => {
      revision++;
      if (review.childNodes.length) review.replaceChildren(el('p', { role: 'status' }, '선택이 바뀌었습니다. 변경 계획을 다시 확인하세요.'));
    };
    for (const control of [names, agents, operation, refresh]) control.addEventListener('change', invalidate);
    const make = button('변경 계획 보기', () => run(async () => {
      const plannedRevision = ++revision;
      const plan = await api('/api/v1/skill-management/plan', { method: 'POST', headers: { 'X-Hub-Profile': profile }, body: JSON.stringify({ operation: operation.value, names: names.values(), agents: agents.values(), refresh: refresh.checked }) });
      if (revision !== plannedRevision || profile !== activeProfile) return;
      const blocked = plan.actions.some(action => action.action === 'blocked');
      const apply = button('이 계획 적용', () => run(async () => {
        if (revision !== plannedRevision || profile !== activeProfile || Date.now() >= plan.expires_at * 1000) {
          invalidate(); throw new Error('계획이 변경되었거나 만료되었습니다. 다시 확인하세요.');
        }
        for (const control of target.querySelectorAll('input, select, button')) control.disabled = true;
        try {
          await api('/api/v1/skill-management/apply', { method: 'POST', headers: { 'X-Hub-Profile': profile }, body: JSON.stringify({ plan_id: plan.id }) });
        } catch (error) { for (const control of target.querySelectorAll('input, select, button')) control.disabled = false; throw error; }
        if (profile !== activeProfile) return;
        showNotice('스킬 변경을 적용했습니다. 에이전트에서 새 세션을 시작하면 반영됩니다.'); await openSkillManager();
      }, apply), 'primary');
      apply.disabled = blocked || !plan.actions.length;
      review.replaceChildren(el('h3', {}, '적용할 변경'), ...plan.actions.map(action => el('div', { class: 'item-row' }, el('div', {}, el('strong', {}, `${action.agent} · ${action.name}`), el('p', { class: 'mono' }, action.path)), badge(({ install: '설치', update: '업데이트', remove: '제거', pin: '고정', unpin: '고정 해제', unchanged: '변경 없음', blocked: '보호됨' })[action.action] || action.action, action.action === 'blocked' ? 'error' : ''), action.reason ? el('small', {}, action.reason) : null)), el('p', { class: 'muted' }, '계획은 15분 동안 유효합니다. 직접 수정한 파일이나 다른 도구가 만든 파일은 덮어쓰지 않습니다.'), apply);
    }, make), 'primary');
    target.replaceChildren(el('section', { class: 'form-panel' }, el('div', { class: 'section-header' }, el('h2', {}, activeProfile === 'global' ? '내 에이전트에 설치' : '프로젝트에 설치'), button('닫기', () => { target.hidden = true; })), el('p', {}, activeProfile === 'global' ? '선택한 에이전트의 사용자 스킬 폴더에 설치합니다.' : '선택한 프로젝트에 복사하고 기본으로 버전을 고정합니다.'), el('h3', {}, '스킬'), names, el('h3', {}, '에이전트'), agents, el('div', { class: 'form-actions' }, operation, el('label', {}, refresh, ' 등록된 배포 출처 갱신'), make), review,
      el('details', {}, el('summary', {}, `설치 상태 ${info.installed.length}개`), ...info.installed.map(item => el('p', {}, `${item.agent} · ${item.name}${item.pinned ? ' · 고정' : ''}${item.modified ? ' · 직접 수정됨' : ''}`)))));
  });
}
function authenticationPanel(server) {
  const auth = server.auth || { type: server.auth_status?.type || 'none' };
  const status = server.auth_status || {};
  const profile = activeProfile;
  const identity = `auth:${server.id}`;
  const names = { none: '인증 없음', bearer: 'Bearer 토큰', api_key: 'API key', basic: '사용자 이름·비밀번호', oauth: 'OAuth 브라우저 로그인', device_code: 'Device Code', client_credentials: 'Client Credentials', external: '서버 자체 인증' };
  const panel = preserveEditor(el('details', { class: 'connection-settings', 'data-disclosure': identity }), identity);
  const summary = el('summary');
  const hint = el('p', { class: 'auth-hint', role: 'status' });
  const result = el('div', { 'aria-live': 'polite' });
  const types = server.transport === 'stdio' ? ['none', 'external'] : Object.keys(names);
  const type = el('select', { 'aria-label': `${server.id} 인증 방식` }, types.map(value => el('option', { value }, names[value])));
  type.value = auth.type;
  const config = el('div', { class: 'auth-fields' });
  const manual = el('div');
  const fields = {};
  const drafts = { ...auth, scopes: (auth.scopes || []).join(' ') };
  let dirty = false;
  const advanced = el('textarea', { 'aria-label': `${server.id} 고급 인증 설정 JSON`, spellcheck: 'false', value: JSON.stringify(Object.fromEntries(Object.entries(auth).filter(([key]) => !['type', 'token_env', 'username_env', 'password_env', 'header', 'prefix', 'client_id', 'issuer', 'client_secret_env', 'scopes'].includes(key))), null, 2) });
  const authCall = (action, body = {}) => api(`/api/v1/auth/${encodeURIComponent(server.id)}/${action}`, { method: 'POST', headers: { 'X-Hub-Profile': profile }, body: JSON.stringify(body) });
  const login = button('로그인 시작', () => run(async () => {
    if (dirty) throw new Error('인증 설정을 먼저 저장하세요.');
    const data = await authCall('login');
    panel.dataset.keepDraft = 'always';
    result.replaceChildren(data.url ? el('a', { href: data.url, target: '_blank', rel: 'noopener noreferrer' }, '브라우저에서 계속 →') : el('p', {}, '인증을 완료했습니다. 연결 확인을 눌러 주세요.'));
    if (data.user_code) {
      result.append(el('p', {}, '입력할 코드: ', el('strong', { class: 'mono' }, data.user_code)));
      const poll = button('로그인 완료 확인', () => run(async () => {
        const token = await authCall('poll', { login_id: data.login_id });
        if (token.status === 'pending') showNotice(`인증을 기다리고 있습니다. ${token.interval || data.interval || 5}초 뒤 다시 확인하세요.`);
        else if (profile === activeProfile) { discardDraft(identity); showNotice('로그인했습니다.'); await load(); }
      }, poll));
      result.append(poll);
    }
  }, login), 'small');
  const update = () => {
    panel.dataset.dirty = String(dirty);
    summary.textContent = `인증 · ${names[type.value]}${dirty ? ' · 저장 전' : status.login_required ? ' · 로그인 필요' : status.configured ? ' · 준비됨' : ''}`;
    hint.textContent = dirty ? '변경한 설정을 먼저 저장한 뒤 로그인하거나 비밀 값을 입력하세요.' : '인증 방식을 저장한 뒤 필요한 로그인 또는 비밀 값 입력을 진행하세요.';
    login.hidden = !['oauth', 'device_code', 'client_credentials'].includes(type.value);
    login.disabled = dirty;
    const fieldset = manual.querySelector('fieldset'); if (fieldset) fieldset.disabled = dirty;
  };
  const changed = () => { dirty = true; result.replaceChildren(); delete panel.dataset.keepDraft; update(); };
  const draw = () => {
    for (const [key, input] of Object.entries(fields)) drafts[key] = input.value;
    for (const key of Object.keys(fields)) delete fields[key];
    const kind = type.value;
    const definitions = kind === 'basic' ? [['username_env', '사용자 이름 환경변수'], ['password_env', '비밀번호 환경변수']] : ['bearer', 'api_key'].includes(kind) ? [['token_env', '토큰 환경변수'], ...(kind === 'api_key' ? [['header', '헤더 이름'], ['prefix', '접두사']] : [])] : ['oauth', 'device_code', 'client_credentials'].includes(kind) ? [['client_id', 'Client ID'], ['issuer', 'Issuer URL'], ['client_secret_env', 'Client secret 환경변수'], ['scopes', '요청 권한']] : [];
    config.replaceChildren(...definitions.map(([key, label]) => {
      fields[key] = el('input', { value: drafts[key] || '', autocomplete: 'off', onInput: changed });
      return field(label, `${server.id}-auth-${key}`, fields[key], key === 'scopes' ? '공백으로 구분하세요.' : '');
    }));
    manual.replaceChildren();
    if (['bearer', 'api_key', 'basic'].includes(kind)) {
      const token = el('input', { type: 'password', autocomplete: 'new-password', 'aria-label': `${server.id} 비밀 값` });
      const username = el('input', { autocomplete: 'off', 'aria-label': `${server.id} 사용자 이름` });
      const store = button('비밀 값 저장', () => run(async () => {
        if (dirty) throw new Error('인증 설정을 먼저 저장하세요.');
        await authCall('credentials', kind === 'basic' ? { username: username.value, password: token.value } : { token: token.value });
        token.value = ''; username.value = '';
        if (profile === activeProfile) { discardDraft(identity); await load(); showNotice('로컬 인증 정보를 저장했습니다.'); }
      }, store), 'small');
      const inputArea = el('fieldset', {}, el('legend', {}, '이 컴퓨터에 저장할 인증 정보'), kind === 'basic' ? field('사용자 이름', `${server.id}-manual-username`, username) : null, field(kind === 'basic' ? '비밀번호' : '토큰', `${server.id}-manual-secret`, token), store);
      manual.append(el('details', { 'data-disclosure': `manual:${server.id}` }, el('summary', {}, '환경변수 대신 이 컴퓨터에 저장'), el('p', {}, status.storage === 'windows-dpapi' ? 'Windows DPAPI로 저장합니다.' : '소유자 전용 권한의 로컬 파일에 저장합니다. OS 계정에 접근할 수 있는 사용자는 읽을 수 있습니다.'), inputArea));
    }
    update();
  };
  type.addEventListener('change', () => { dirty = true; draw(); changed(); });
  advanced.addEventListener('input', changed);
  const save = button('인증 설정 저장', () => run(async () => {
    let settings; try { settings = JSON.parse(advanced.value); } catch { throw new Error('고급 인증 설정은 JSON 객체로 입력하세요.'); }
    if (!settings || Array.isArray(settings) || typeof settings !== 'object') throw new Error('인증 설정은 객체여야 합니다.');
    settings.type = type.value;
    for (const [key, input] of Object.entries(fields)) if (input.value.trim()) settings[key] = key === 'scopes' ? input.value.trim().split(/\s+/) : input.value.trim();
    const allowed = ['id', 'name', 'transport', 'command', 'args', 'env', 'url', 'headers', 'protocol_version', 'enabled', 'policy'];
    const payload = Object.fromEntries(Object.entries(server).filter(([key]) => allowed.includes(key)));
    payload.auth = settings;
    await api('/api/v1/servers', { method: 'POST', headers: { 'X-Hub-Profile': profile }, body: JSON.stringify(payload) });
    if (profile === activeProfile) { discardDraft(identity); await load(); showNotice('인증 설정을 저장했습니다.'); }
  }, save), 'small');
  panel.append(summary, hint, el('div', { class: 'form-grid' }, field('인증 방식', `${server.id}-auth-type`, type), config), el('details', { 'data-disclosure': `advanced:${server.id}` }, el('summary', {}, '고급 설정'), el('p', {}, 'client_auth_method, client_metadata_url, 개별 endpoint를 JSON으로 지정할 수 있습니다.'), advanced), el('div', { class: 'form-actions' }, save, login,
    auth.type !== 'none' && auth.type !== 'external' ? button('저장된 인증 해제', () => run(async () => { const data = await authCall('logout'); if (profile === activeProfile) { discardDraft(identity); await load(); showNotice(data.revoked ? '서비스 토큰을 철회하고 로컬 인증을 지웠습니다.' : '로컬 인증을 지웠습니다. 환경변수와 서비스 계정 설정은 별도로 관리하세요.'); } }), 'quiet small') : null), result, manual);
  if (server.transport === 'stdio') panel.append(el('p', {}, 'stdio는 서버 자체 로그인이나 등록된 env 매핑을 사용합니다. 필요한 CLI 로그인은 터미널에서 진행하세요.'));
  draw();
  return panel;
}

async function renderConnectionSettings() {
  const profile = activeProfile;
  const target = preserveEditor(el('div', { 'data-preserve': 'connection-settings' }), 'connection-settings');
  replacePage(title('연결 설정', profile === 'global' ? '에이전트가 Hub에 연결하는 기본 방식을 선택하세요.' : '이 프로젝트의 연결 방식을 선택하세요. 스킬·인증 저장소는 유지됩니다.'), target);
  await run(async () => {
    const info = await api('/api/v1/connection');
    if (!target.isConnected || profile !== activeProfile) return;
    const mode = el('select', { 'aria-label': 'Hub 연결 방식' }, el('option', { value: 'stdio' }, 'stdio · 에이전트가 자동 실행'), el('option', { value: 'hybrid' }, 'stdio + HTTP · 실행 중인 Hub 공유'), el('option', { value: 'http' }, 'HTTP · 서버에 직접 연결'));
    mode.value = info.settings.mode;
    const url = el('input', { type: 'url', value: info.configured ? info.settings.url : info.runtime.url, placeholder: 'http://127.0.0.1:8765' });
    const fallback = el('select', {}, el('option', { value: 'stdio' }, 'stdio로 자체 실행'), el('option', { value: 'error' }, '오류를 표시하고 연결 중단'));
    fallback.value = info.settings.fallback;
    const inherit = el('input', { type: 'checkbox' }); inherit.checked = info.inherited;
    const explanation = el('p', { class: 'muted', role: 'status' });
    const fields = el('div', { class: 'form-grid' }, field('연결 방식', 'connection-mode', mode, '', true), field('HTTP Hub 주소', 'connection-url', url), field('HTTP Hub가 꺼져 있을 때', 'connection-fallback', fallback));
    const help = {
      stdio: 'HTTP 서버를 찾지 않습니다. 에이전트가 연결할 때 Hub를 실행하고 연결을 닫으면 종료합니다.',
      hybrid: '연결을 시작할 때 같은 저장소의 HTTP Hub를 찾습니다. 연결한 뒤에는 방식을 바꾸거나 도구 호출을 다시 실행하지 않습니다.',
      http: '에이전트가 HTTP 주소에 직접 연결합니다. 서버를 따로 시작해야 하며 꺼져 있으면 연결되지 않습니다.'
    };
    const update = () => {
      mode.disabled = profile !== 'global' && inherit.checked;
      url.disabled = mode.disabled || mode.value === 'stdio';
      fallback.disabled = mode.disabled || mode.value !== 'hybrid';
      url.closest('.form-field').hidden = mode.value === 'stdio';
      fallback.closest('.form-field').hidden = mode.value !== 'hybrid';
      explanation.textContent = help[mode.value];
    };
    mode.addEventListener('change', update); inherit.addEventListener('change', update); update();
    const preview = el('div');
    const save = button('연결 방식 저장', () => run(async () => {
      const payload = profile !== 'global' && inherit.checked ? { inherit: true } : { mode: mode.value, url: url.value, fallback: fallback.value };
      await api('/api/v1/connection', { method: 'POST', headers: { 'X-Hub-Profile': profile }, body: JSON.stringify(payload) });
      if (profile !== activeProfile) return;
      discardDraft('connection-settings'); await loadProjects(); await load();
      showNotice('연결 방식을 저장했습니다. 에이전트 등록을 반영한 뒤 MCP 연결이나 세션을 다시 시작하세요.');
    }, save), 'primary');
    const agents = choices(Object.keys(info.agents));
    const review = el('div', { 'aria-live': 'polite' });
    let generation = 0;
    agents.addEventListener('change', () => { generation++; review.replaceChildren(); });
    const plan = button('에이전트 등록 계획 보기', () => run(async () => {
      if (target.dataset.dirty === 'true') throw new Error('연결 방식을 먼저 저장하세요.');
      const id = ++generation;
      const result = await api('/api/v1/connection/plan', { method: 'POST', headers: { 'X-Hub-Profile': profile }, body: JSON.stringify({ agents: agents.values() }) });
      if (generation !== id || profile !== activeProfile) return;
      const apply = button('에이전트 등록 적용', () => run(async () => {
        if (id !== generation || profile !== activeProfile || target.dataset.dirty === 'true') throw new Error('연결 설정이 바뀌었습니다. 계획을 다시 확인하세요.');
        await api('/api/v1/connection/apply', { method: 'POST', headers: { 'X-Hub-Profile': profile }, body: JSON.stringify({ plan_id: result.id }) });
        review.replaceChildren(); showNotice('에이전트에 연결을 등록했습니다. 새 세션을 시작하세요.');
      }, apply), 'primary');
      review.replaceChildren(el('h3', {}, '변경할 설정 파일'), ...result.paths.map(path => el('p', { class: 'mono' }, path)), el('p', {}, '선택한 에이전트의 joongi-hub 항목을 등록합니다. 기존 또는 직접 수정한 같은 이름의 항목은 덮어쓰지 않습니다.'), apply);
    }, plan));
    // Registration selections are not unsaved transport edits.
    agents.addEventListener('input', event => event.stopPropagation());
    agents.addEventListener('change', event => event.stopPropagation());
    const editorChanged = () => { generation++; review.replaceChildren(); };
    fields.addEventListener('change', editorChanged); inherit.addEventListener('change', editorChanged);
    const client = el('select', { 'aria-label': '설정을 볼 에이전트' }, ...Object.keys(info.agents).map(name => el('option', { value: name }, name)));
    client.value = 'codex';
    client.addEventListener('input', event => event.stopPropagation());
    const code = el('pre');
    const drawCode = () => { code.textContent = JSON.stringify({ 'joongi-hub': info.agents[client.value] }, null, 2); };
    client.addEventListener('change', event => { event.stopPropagation(); drawCode(); }); drawCode();
    const copy = button('연결 설정 복사', () => run(async () => { await navigator.clipboard.writeText(code.textContent); showNotice('연결 설정을 복사했습니다. 선택한 에이전트의 MCP 설정 형식에 맞춰 넣으세요.'); }), 'small');
    const distro = el('input', { value: info.wsl_distribution || '', placeholder: '예: Ubuntu' });
    const windows = button('Windows용 WSL 연결 생성', () => run(async () => {
      const data = await api('/api/v1/connection?wsl=' + encodeURIComponent(distro.value), { headers: { 'X-Hub-Profile': profile } });
      preview.replaceChildren(el('p', {}, 'Windows 에이전트의 MCP 서버 항목에 넣으세요. 아래 자동 등록은 현재 환경의 설정을 변경하므로 Windows 설정에는 별도로 복사해야 합니다.'), el('pre', {}, JSON.stringify(data.agents[client.value], null, 2)));
    }), 'small');
    target.append(el('section', { class: 'form-panel' }, profile !== 'global' ? el('label', { class: 'checkbox-label' }, inherit, ' 공용 기본 설정 따르기') : null, fields, explanation, el('div', { class: 'form-actions' }, save)),
      el('details', { class: 'compat-detail' }, el('summary', {}, '이 범위의 상태 저장소'), el('pre', {}, info.state_dir), el('p', {}, '연결 방식이 달라져도 이 저장소의 설정·인증·기록을 사용합니다.')),
      el('section', { class: 'section' }, el('h2', {}, profile === 'global' ? '내 에이전트에 등록' : '이 프로젝트에 등록'), el('p', {}, '현재 환경에서 선택한 에이전트의 설정만 변경합니다. 설치할 스킬 선택은 스킬 라이브러리에서 관리합니다.'), agents, plan, review),
      el('details', { class: 'compat-detail' }, el('summary', {}, '수동 연결 설정'), client, code, copy,
        el('details', {}, el('summary', {}, 'Windows 에이전트에서 WSL 사용'), field('WSL 배포판 이름', 'wsl-distribution', distro), windows, preview)),
      el('details', { class: 'compat-detail' }, el('summary', {}, '웹 UI 실행·종료'), el('p', {}, '웹 탭을 닫아도 HTTP Hub는 계속 실행됩니다. 중지하면 HTTP로 연결된 에이전트와 진행 중인 작업도 영향을 받습니다.'),
        el('pre', {}, 'joongi-hub start\njoongi-hub stop\njoongi-hub restart\njoongi-hub status\njoongi-hub open'),
        button('HTTP Hub 중지 확인', () => {
          const confirm = el('div', { class: 'notice' }, el('p', {}, 'HTTP 연결과 실행 중인 작업이 종료됩니다. 다시 켜려면 터미널에서 joongi-hub start를 실행하세요.'), button('HTTP Hub 중지', () => run(async () => {
            await api('/api/v1/runtime/stop', { method: 'POST', body: JSON.stringify({ instance: info.runtime.instance }) });
            workspaceStatus = 'error'; workspaceError = 'HTTP Hub를 중지했습니다. joongi-hub start로 다시 실행하세요.'; render();
          }), 'danger'), button('취소', () => confirm.remove()));
          target.append(confirm);
        }, 'quiet small')));
    for (const group of target.querySelectorAll('details')) { group.addEventListener('input', event => event.stopPropagation()); group.addEventListener('change', event => event.stopPropagation()); }
  });
}
