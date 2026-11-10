// Interoperability view using the official App SDK, built into examples/apps/demo-view.js.
import { App } from '@modelcontextprotocol/ext-apps';
import { CreateTaskResultSchema, GetTaskResultSchema,
  CallToolResultSchema } from '@modelcontextprotocol/sdk/types.js';
const app = new App({ name: 'joongi-interop-view', version: '1.0.0' }, {}, { autoResize: true });
const status = document.getElementById('app-status');
app.ontoolinput = () => { status.textContent = 'App 연결됨'; };
app.ontoolresult = result => { document.getElementById('app-result').textContent = JSON.stringify(result); };
document.getElementById('app-echo').addEventListener('click', async () => {
  status.textContent = 'App 호출 요청 중';
  const result = await app.callServerTool({ name: 'echo', arguments: { message: 'app-sdk-roundtrip' } });
  const resource = await app.readServerResource({ uri: 'file:///fixture/notes.txt' });
  document.getElementById('app-result').textContent = JSON.stringify(result) + '\n' + resource.contents[0].text;
});
app.connect().catch(error => { status.textContent = error.message; });
document.getElementById('app-task')?.addEventListener('click', async () => {
  const output = document.getElementById('app-task-result');
  try {
    const created = await app.request({ method: 'tools/call', params: {
      name: 'delay', arguments: { seconds: 0.05, message: 'app-task-roundtrip' },
      task: { ttl: 60000 }
    } }, CreateTaskResultSchema);
    let task;
    for (let attempt = 0; attempt < 40; attempt++) {
      task = await app.request({ method: 'tasks/get', params: { taskId: created.task.taskId } }, GetTaskResultSchema);
      if (['completed', 'failed', 'cancelled'].includes(task.status)) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    if (task.status !== 'completed') throw new Error(`Task ${task.status}`);
    const result = await app.request({ method: 'tasks/result', params: { taskId: task.taskId } }, CallToolResultSchema);
    output.textContent = `Task 완료: ${JSON.stringify(result)}`;
  } catch (error) { output.textContent = `Task 오류: ${error.message}`; }
});
