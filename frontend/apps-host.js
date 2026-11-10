// Built with the official MCP Apps AppBridge. See scripts/build_apps.mjs.
import { AppBridge, PostMessageTransport } from '@modelcontextprotocol/ext-apps/app-bridge';
import { GetTaskRequestSchema, GetTaskPayloadRequestSchema,
  ListTasksRequestSchema, CancelTaskRequestSchema } from '@modelcontextprotocol/sdk/types.js';

window.JoongiApps = {
  async mount(container, { server, tool, arguments: args, result, api }) {
    const view = await api('/api/v1/apps', { method: 'POST', body: JSON.stringify({ server, tool }) });
    const frame = document.createElement('iframe');
    frame.className = 'app-frame';
    frame.title = `${tool} MCP App`;
    frame.setAttribute('sandbox', 'allow-scripts');
    frame.setAttribute('referrerpolicy', 'no-referrer');
    const status = document.createElement('p');
    status.className = 'muted';
    status.textContent = 'App을 연결하고 있습니다…';
    container.replaceChildren(status, frame);
    let ready = false;
    let currentResult = result;
    const bridge = new AppBridge(null, { name: 'joongi-hub', version: '0.1.0' },
      { serverTools: {}, serverResources: {}, logging: {} },
      { hostContext: { theme: matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
        displayMode: 'inline', locale: 'ko-KR', platform: 'web' } });
    const forward = (method, params) => api(`/api/v1/apps/${view.token}/rpc`,
      { method: 'POST', body: JSON.stringify({ method, params }) });
    bridge.oncalltool = async params => {
      status.textContent = 'App 도구 실행 중';
      const response = await forward('tools/call', params);
      status.textContent = 'MCP App 연결됨';
      return response;
    };
    for (const [schema, method] of [
      [GetTaskRequestSchema, 'tasks/get'], [GetTaskPayloadRequestSchema, 'tasks/result'],
      [ListTasksRequestSchema, 'tasks/list'], [CancelTaskRequestSchema, 'tasks/cancel']
    ]) bridge.setRequestHandler(schema, request => forward(method, request.params || {}));
    bridge.onreadresource = params => forward('resources/read', params);
    bridge.onlistresources = params => forward('resources/list', params);
    bridge.onlistresourcetemplates = params => forward('resources/templates/list', params);
    bridge.onlistprompts = params => forward('prompts/list', params);
    bridge.onloggingmessage = () => {};
    bridge.onsizechange = ({ height }) => {
      if (Number.isFinite(height)) frame.height = String(Math.min(1600, Math.max(160, height)));
    };
    bridge.oninitialized = async () => {
      ready = true;
      status.textContent = 'MCP App 연결됨';
      frame.scrollIntoView({ block: 'center', behavior: 'instant' });
      await bridge.sendToolInput({ arguments: args });
      if (currentResult) await bridge.sendToolResult(currentResult);
    };
    bridge.onerror = error => { status.textContent = `App 연결 오류: ${error.message}`; };
    await bridge.connect(new PostMessageTransport(frame.contentWindow, frame.contentWindow));
    frame.src = view.url;
    return {
      async updateResult(value) {
        currentResult = value;
        if (ready) await bridge.sendToolResult(value);
      },
      async close() {
        try { if (ready) await bridge.teardownResource({}, { timeout: 1500 }); } catch { /* View may already be gone. */ }
        await bridge.close();
        frame.remove();
      }
    };
  }
};
