(() => {
      const frame = document.getElementById('mcp-origin-view');
      const prefix = __JOONGI_SOURCE__;
      const route = value => {
        const parsed = value.match(/^([a-zA-Z][a-zA-Z0-9+.-]*:)(?:\/\/([^/?#]*))?([\s\S]*)$/);
        if (!parsed) throw new Error('Invalid resource URI');
        const origin = parsed[1] === 'skill:' ? 'skill://' : parsed[1] + (parsed[2] === undefined ? '' : '//' + parsed[2]);
        const tail = (parsed[1] === 'skill:' ? parsed[2] : '') + parsed[3];
        let binary = ''; for (const byte of new TextEncoder().encode(origin)) binary += String.fromCharCode(byte);
        const encoded = btoa(binary).replaceAll('+','-').replaceAll('/','_').replaceAll('=','');
        const path = encodeURIComponent(tail).replace(/%2F/gi,'/').replace(/[!'()*]/g, char => '%' + char.charCodeAt(0).toString(16).toUpperCase());
        return (parsed[1] === 'ui:' ? 'ui' : 'mcp-resource') + '://hub/' + prefix + '/' + encoded + '/' + path;
      };
      const restore = value => {
        const match = typeof value === 'string' && value.match(/^(?:ui|mcp-resource):\/\/hub\/([^/]+)\/([^/]+)\/(.*)$/);
        if (!match || match[1] !== prefix) return value;
        const bytes = Uint8Array.from(atob(match[2].replaceAll('-','+').replaceAll('_','/')), char => char.charCodeAt(0));
        return new TextDecoder().decode(bytes) + decodeURIComponent(match[3]);
      };
      const resource = item => { if (item && typeof item.uri === 'string') item.uri = restore(item.uri); return item; };
      const block = item => {
        if (item?.type === 'resource_link') resource(item);
        if (item?.type === 'resource') resource(item.resource);
      };
      const unmap = message => {
        const result = message?.result || (message?.method === 'ui/notifications/tool-result' ? message.params : null);
        if (!result) return;
        for (const key of ['contents','resources']) if (Array.isArray(result[key])) result[key].forEach(resource);
        if (Array.isArray(result.content)) result.content.forEach(block);
      };
      window.addEventListener('message', event => {
        if (event.source === frame.contentWindow) {
          const message = structuredClone(event.data);
          if (message && message.method === 'tools/call' && message.params && typeof message.params.name === 'string') {
            message.params.name = prefix + '__' + message.params.name;
          }
          if (message?.method === 'resources/read' && typeof message.params?.uri === 'string') message.params.uri = route(message.params.uri);
          window.parent.postMessage(message, '*');
        } else if (event.source === window.parent) {
          const message = structuredClone(event.data); unmap(message);
          frame.contentWindow.postMessage(message, '*');
        }
      });
    })();
