'use strict';
(() => {
  const fragment = new URLSearchParams(location.hash.slice(1));
  let session = fragment.get('session');
  const approvalId = fragment.get('approval_id');
  history.replaceState(null, '', location.pathname);
  const node = (id) => document.getElementById(id);
  let timer;
  const message = (text, error = false) => {
    node('status').textContent = text;
    node('status').classList.toggle('error', error);
  };
  const disable = () => {
    node('approve').disabled = true;
    node('deny').disabled = true;
  };
  async function request(action) {
    const response = await fetch('/decision', {
      method: 'POST', headers: {'Content-Type': 'application/json', Authorization: `Bearer ${session}`},
      body: JSON.stringify({approval_id: approvalId, action}), credentials: 'omit', cache: 'no-store',
    });
    if (!response.ok) throw new Error('요청이 만료되었거나 이미 처리됐습니다. 에이전트에서 상태를 확인하세요.');
    return response.json();
  }
  async function decide(action) {
    disable();
    clearInterval(timer);
    try {
      await request(action);
      message(action === 'approve' ? '한 번 승인했습니다. 에이전트가 원래 요청을 다시 실행할 수 있습니다. 이 창을 닫아도 됩니다.' : '거절했습니다. 이 호출은 실행되지 않습니다. 이 창을 닫아도 됩니다.');
    } catch (error) { message(error.message, true); }
    session = null;
  }
  node('approve').addEventListener('click', () => decide('approve'));
  node('deny').addEventListener('click', () => decide('deny'));
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
