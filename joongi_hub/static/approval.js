'use strict';
(() => {
  const fragment = new URLSearchParams(location.hash.slice(1));
  let session = fragment.get('session');
  const approvalId = fragment.get('approval_id');
  history.replaceState(null, '', location.pathname);
  const node = (id) => document.getElementById(id);
  let timer, pendingTimer, closeTimer;
  const message = (text, error = false) => {
    node('status').textContent = text;
    node('status').classList.toggle('error', error);
  };
  const disable = () => {
    node('approve').disabled = true;
    node('deny').disabled = true;
    node('scope').disabled = true;
  };
  async function request(action, timeout = 5000) {
    const controller = new AbortController();
    const deadline = setTimeout(() => controller.abort(), timeout);
    try {
      const response = await fetch('/decision', {
        method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${session}`},
        body: JSON.stringify({approval_id: approvalId, action, ...(action === 'approve' ? {scope: node('scope').value} : {})}), credentials: 'omit', cache: 'no-store',
        signal: controller.signal,
      });
      if (!response.ok) throw new Error('승인 요청의 상태를 확인하지 못했습니다.');
      return await response.json();
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('Hub 응답이 지연되고 있습니다. 에이전트에서 연결 상태를 확인하세요.');
      throw error;
    } finally { clearTimeout(deadline); }
  }
  function finished(row) {
    if (!['approved', 'denied'].includes(row.status)) return false;
    clearInterval(timer);
    clearInterval(pendingTimer);
    disable();
    node('actions').removeAttribute('aria-busy');
    node('approve').textContent = '이 호출 한 번 승인';
    node('deny').textContent = '거절';
    node('retry-status').hidden = true;
    node('actions').hidden = true;
    node('title').textContent = row.status === 'approved' ? '승인 완료' : '요청 거절';
    const approved = {once: '한 번 승인했습니다.', hour: '이 도구를 1시간 허용했습니다.', always: '이 도구를 항상 허용했습니다.'}[row.scope || 'once'];
    message(row.status === 'approved'
      ? `${approved} 이 창은 닫아도 됩니다. 이제 에이전트가 같은 요청을 다시 실행합니다. 서비스의 실행 결과는 에이전트에서 확인하세요.`
      : '거절했습니다. 이 호출은 실행되지 않습니다. 이 창을 닫아도 됩니다.');
    session = null;
    if (row.status === 'approved' && node('auto-close').checked) {
      node('close-status').hidden = false;
      node('keep-open').hidden = false;
      node('close-status').textContent = '3초 후 이 승인 창을 닫습니다.';
      closeTimer = setTimeout(() => {
        node('keep-open').hidden = true;
        window.close();
        node('close-status').textContent = '승인은 완료됐습니다. 자동으로 닫히지 않으면 브라우저의 탭 닫기를 사용하세요.';
      }, 3000);
    }
    return true;
  }
  async function checkStatus() {
    node('retry-status').hidden = true;
    message('승인 저장 여부를 확인하고 있습니다…');
    try {
      if (finished(await request('status', 3000))) return;
      message('아직 승인 완료를 확인하지 못했습니다. 에이전트에서 승인 상태를 확인하세요. 요청을 자동으로 다시 보내지는 않습니다.', true);
    } catch {
      message('Hub 응답을 확인하지 못했습니다. 승인이 저장됐을 수도 있으므로 다시 승인하기 전에 상태를 확인하세요.', true);
    }
    node('actions').removeAttribute('aria-busy');
    node('retry-status').hidden = false;
  }
  async function decide(action) {
    disable();
    clearInterval(timer);
    node('actions').setAttribute('aria-busy', 'true');
    const label = action === 'approve' ? '승인을 저장' : '거절을 저장';
    node(action === 'approve' ? 'approve' : 'deny').textContent = '저장 중…';
    const start = performance.now();
    message(`${label}하고 있습니다…`);
    pendingTimer = setInterval(() => {
      message(`${label}하고 있습니다… (${Math.floor((performance.now() - start) / 1000)}초) 아직 서비스 호출을 실행하는 단계는 아닙니다.`);
    }, 1000);
    try {
      const row = await request(action);
      if (!finished(row)) throw new Error('Unconfirmed decision');
    } catch {
      clearInterval(pendingTimer);
      await checkStatus(); // Read-only recovery. Never repeat a decision POST.
    }
  }
  node('keep-open').addEventListener('click', () => { clearTimeout(closeTimer); node('keep-open').hidden = true; node('close-status').textContent = '승인 완료 화면을 유지합니다. 필요할 때 이 탭을 닫으세요.'; });
  node('auto-close').addEventListener('change', () => { if (!node('auto-close').checked) { clearTimeout(closeTimer); node('keep-open').hidden = true; node('close-status').hidden = true; } });
  node('scope').addEventListener('change', () => {
    node('approve').textContent = {once: '이 호출 한 번 승인', hour: '이 도구 1시간 허용', always: '이 도구 항상 허용'}[node('scope').value];
    node('scope-note').textContent = node('scope').value === 'once' ? '현재 도구와 인수 조합에 한 번 적용합니다.' : '같은 프로젝트 범위·연결의 이 도구를 반복 허용합니다. 다른 인수와 페이지도 포함하며 MCP 연결 화면에서 취소할 수 있습니다.';
  });
  node('approve').addEventListener('click', () => decide('approve'));
  node('deny').addEventListener('click', () => decide('deny'));
  node('retry-status').addEventListener('click', checkStatus);
  (async () => {
    try {
      if (!session || !approvalId) throw new Error('로컬 Hub가 연 승인창을 사용하세요. 에이전트에서 승인 요청을 다시 보낼 수 있습니다.');
      const row = await request('view');
      for (const key of ['server', 'tool', 'profile']) node(key).textContent = row[key];
      node('endpoint').textContent = row.review?.endpoint || row.review?.transport || '이전 요청에는 주소 정보가 없습니다. 필요하면 관리 화면에서 연결 설정을 확인하세요.';
      node('arguments').textContent = JSON.stringify(row.arguments, null, 2);
      if (Object.values(row.continuation || {}).some((value) => value != null)) {
        node('extra').hidden = false;
        node('continuation').textContent = JSON.stringify(row.continuation, null, 2);
      }
      const expires = row.expires_at * 1000;
      node('expiry').textContent = new Date(expires).toLocaleTimeString();
      node('review').hidden = false;
      const checkExpiry = () => {
        if (Date.now() >= expires) {
          disable(); session = null; clearInterval(timer);
          message('승인 요청이 만료됐습니다. 에이전트에서 원래 요청을 다시 실행하세요.', true);
        }
      };
      timer = setInterval(checkExpiry, 1000);
      checkExpiry();
      if (session) message('요청 인수를 확인한 뒤 승인하거나 거절하세요.');
    } catch (error) { disable(); message(error.message, true); }
  })();
})();
