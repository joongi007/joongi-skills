'use strict';
(() => {
  const fragment = new URLSearchParams(location.hash.slice(1));
  const session = fragment.get('session');
  let activeId = fragment.get('approval_id');
  history.replaceState(null, '', location.pathname);
  const node = id => document.getElementById(id);
  const selected = new Set();
  let snapshot = {requests: [], receipts: [], profile: ''};
  let busy = false, uncertain = null, signature = '', detailSignature = '';
  let idleSince = null, canClose = false, stopped = false, pollBusy = false;
  const labels = {once: '이 호출 한 번 승인', hour: '이 도구 1시간 허용', always: '이 도구 항상 허용'};
  const message = (text, error = false) => {
    node('status').textContent = text;
    node('status').classList.toggle('error', error);
  };
  async function post(path, body, timeout = 5000) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch(path, {method: 'POST', headers: {
        'Content-Type': 'application/json', Authorization: `Bearer ${session}`},
        body: JSON.stringify(body), credentials: 'omit', cache: 'no-store', signal: controller.signal});
      if (!response.ok) throw new Error('승인함 응답을 확인하지 못했습니다.');
      return await response.json();
    } finally { clearTimeout(timer); }
  }
  function controls() {
    node('approve').disabled = busy || !activeId;
    node('deny').disabled = busy || !activeId;
    node('scope').disabled = busy;
    node('select-all').disabled = busy || !snapshot.requests.length;
    for (const input of node('requests').querySelectorAll('input')) input.disabled = busy;
    node('batch-approve').disabled = busy || !selected.size;
    node('batch-deny').disabled = busy || !selected.size;
    node('batch-approve').textContent = `선택 ${selected.size}개 이번 호출 허용`;
    node('batch-deny').textContent = `선택 ${selected.size}개 거절`;
  }
  function detail() {
    const row = snapshot.requests.find(row => row.id === activeId);
    node('review').hidden = !row;
    if (!row) { activeId = null; detailSignature = ''; controls(); return; }
    const next = JSON.stringify(row);
    if (next !== detailSignature) {
      detailSignature = next;
      for (const key of ['server', 'tool']) node(key).textContent = row[key];
      node('profile').textContent = snapshot.profile;
      node('endpoint').textContent = row.review?.endpoint || row.review?.transport || '연결 설정에서 확인하세요.';
      node('arguments').textContent = JSON.stringify(row.arguments, null, 2);
      node('continuation').textContent = JSON.stringify(row.continuation || {}, null, 2);
      node('extra').hidden = !Object.values(row.continuation || {}).some(v => v != null);
      node('expiry').textContent = new Date(row.expires_at * 1000).toLocaleTimeString();
      node('scope').value = 'once'; node('approve').textContent = labels.once;
      node('scope-note').textContent = '현재 도구와 인수 조합에 한 번 적용합니다.';
    }
    for (const button of node('requests').querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.id === activeId));
    controls();
  }
  function render() {
    const ids = new Set(snapshot.requests.map(row => row.id));
    for (const id of selected) if (!ids.has(id)) selected.delete(id);
    if (!ids.has(activeId)) activeId = snapshot.requests[0]?.id || null;
    node('queue-status').textContent = `대기 ${snapshot.requests.length}개 · MCP ${new Set(snapshot.requests.map(row => row.server)).size}개 · ${snapshot.profile}`;
    node('empty').hidden = !!snapshot.requests.length;
    const next = JSON.stringify(snapshot.requests);
    if (signature !== next) {
      signature = next;
      node('requests').replaceChildren();
      const groups = new Map();
      for (const row of snapshot.requests) {
        if (!groups.has(row.server)) {
          const group = document.createElement('section');
          const heading = document.createElement('h3'); heading.textContent = row.server;
          group.append(heading); node('requests').append(group); groups.set(row.server, group);
        }
        const card = document.createElement('div'); card.className = 'request-row';
        const check = document.createElement('input'); check.type = 'checkbox'; check.checked = selected.has(row.id);
        check.setAttribute('aria-label', `요청 선택: ${row.server} · ${row.tool} · ${row.id.slice(-6)}`);
        check.addEventListener('change', () => { if (check.checked) selected.add(row.id); else selected.delete(row.id); controls(); });
        const button = document.createElement('button'); button.type = 'button'; button.dataset.id = row.id;
        button.textContent = `${row.tool} · ${row.id.slice(-6)} · 요청 확인`;
        button.addEventListener('click', () => { if (!busy) { activeId = row.id; detail(); } });
        card.append(check, button); groups.get(row.server).append(card);
      }
    }
    detail();
    if (snapshot.requests.length || uncertain || !canClose || !node('auto-close').checked) {
      idleSince = null; node('close-status').hidden = true; node('keep-open').hidden = true;
    } else {
      idleSince ??= performance.now();
      node('close-status').hidden = false; node('keep-open').hidden = false;
      node('close-status').textContent = `대기 요청이 없습니다. ${Math.max(0, Math.ceil(30 - (performance.now() - idleSince) / 1000))}초 후 닫습니다.`;
    }
  }
  async function refresh() {
    snapshot = await post('/inbox', {action: 'view'});
    render();
  }
  function confirmed(decisions) {
    const approved = decisions.every(row => row.status === 'approved');
    const text = decisions.length > 1 ? `선택한 ${decisions.length}개 요청을 ${approved ? '승인' : '거절'}했습니다.` :
      approved ? {once: '한 번 승인했습니다.', hour: '이 도구를 1시간 허용했습니다.', always: '이 도구를 항상 허용했습니다.'}[decisions[0].scope || 'once'] : '거절했습니다.';
    for (const row of decisions) selected.delete(row.approval_id);
    uncertain = null; canClose = approved;
    node('retry-status').hidden = true;
    message(`${text} ${approved ? '에이전트가 허용된 요청을 이어서 실행합니다.' : '거절한 호출은 실행되지 않습니다.'} 새 요청은 이 승인함에 모입니다.`);
  }
  async function recover() {
    if (!uncertain) return;
    busy = true; controls(); node('retry-status').hidden = true;
    message('승인 저장 여부를 확인하고 있습니다…');
    try {
      let decisions;
      if (uncertain.ids.length === 1) {
        decisions = [await post('/decision', {approval_id: uncertain.ids[0], action: 'status'}, 3000)];
      } else {
        const value = await post('/inbox', {action: 'view'}, 3000);
        decisions = uncertain.ids.map(id => value.receipts.find(row => row.approval_id === id));
      }
      const expected = uncertain.action === 'approve' ? 'approved' : 'denied';
      if (!decisions.every(row => row?.status === expected)) throw new Error('Unconfirmed');
      confirmed(decisions);
    } catch {
      message('Hub 응답을 확인하지 못했습니다. 저장됐을 수도 있으므로 상태를 확인하세요. 요청을 자동으로 다시 보내지 않습니다.', true);
      node('retry-status').hidden = false;
    } finally { busy = false; controls(); }
  }
  async function decide(action, batch = false) {
    const ids = batch ? [...selected] : activeId ? [activeId] : [];
    if (busy || !ids.length) return;
    busy = true; canClose = false; idleSince = null; controls();
    uncertain = {ids, action};
    message(`${action === 'approve' ? '승인을 저장' : '거절을 저장'}하고 있습니다…`);
    const start = performance.now();
    const progress = setInterval(() => message(`결정을 저장하고 있습니다… (${Math.floor((performance.now() - start) / 1000)}초)`), 1000);
    try {
      const value = batch ? await post('/inbox', {action, approval_ids: ids}) : await post('/decision', {
        action, approval_id: ids[0], ...(action === 'approve' ? {scope: node('scope').value} : {})});
      confirmed(batch ? value.decisions : [value]);
    } catch {
      clearInterval(progress); await recover();
    } finally {
      clearInterval(progress); busy = false;
      try { await refresh(); } catch { controls(); }
    }
  }
  node('approve').addEventListener('click', () => decide('approve'));
  node('deny').addEventListener('click', () => decide('deny'));
  node('batch-approve').addEventListener('click', () => decide('approve', true));
  node('batch-deny').addEventListener('click', () => decide('deny', true));
  node('select-all').addEventListener('click', () => { for (const row of snapshot.requests) selected.add(row.id); signature = ''; render(); });
  node('retry-status').addEventListener('click', async () => { await recover(); try { await refresh(); } catch {} });
  node('scope').addEventListener('change', () => {
    node('approve').textContent = labels[node('scope').value];
    node('scope-note').textContent = node('scope').value === 'once' ? '현재 도구와 인수 조합에 한 번 적용합니다.' : '같은 프로젝트·MCP 연결의 이 도구를 반복 허용합니다. 다른 인수와 페이지도 포함하며 관리 화면에서 취소할 수 있습니다.';
  });
  node('keep-open').addEventListener('click', () => { node('auto-close').checked = false; render(); });
  node('auto-close').addEventListener('change', render);
  window.addEventListener('pagehide', () => {
    if (!stopped && session) fetch('/inbox', {method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${session}`},
      body: JSON.stringify({action: 'close'}), keepalive: true}).catch(() => {});
    stopped = true;
  });
  setInterval(async () => {
    if (stopped || pollBusy || busy) return;
    pollBusy = true;
    try {
      await refresh();
      if (idleSince !== null && performance.now() - idleSince >= 30000) {
        const value = await post('/inbox', {action: 'close_if_empty'});
        if (value.closed) {
          stopped = true; node('keep-open').hidden = true; window.close();
          node('close-status').textContent = '처리가 끝났습니다. 자동으로 닫히지 않으면 브라우저의 탭 닫기를 사용하세요.';
        } else { idleSince = null; await refresh(); }
      }
    } catch { message('승인함 연결을 확인하지 못했습니다. 기존 요청은 자동 재전송하지 않습니다. 에이전트에서 상태를 확인하세요.', true); }
    finally { pollBusy = false; }
  }, 1000);
  (async () => {
    try {
      if (!session) throw new Error('로컬 Hub가 연 승인함을 사용하세요.');
      await refresh(); message('요청을 확인하고 개별 승인하거나 선택한 요청을 함께 처리하세요.');
    } catch { message('승인함을 열지 못했습니다. 에이전트에서 상태를 확인하세요.', true); }
  })();
})();
