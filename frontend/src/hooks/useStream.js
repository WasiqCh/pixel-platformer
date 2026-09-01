import { useState, useCallback, useRef } from 'react';

export default function useStream() {
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState(null);
  const controllerRef = useRef(null);

  const start = useCallback(async (url, body, { onDelta, onDone, onError } = {}) => {
    setStreaming(true);
    setError(null);
    controllerRef.current = new AbortController();
    try {
      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(body),
        signal: controllerRef.current.signal,
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        let idx;
        while ((idx = buffer.indexOf('\n\n')) !== -1) {
          const frame = buffer.slice(0, idx).trim();
          buffer = buffer.slice(idx + 2);
          if (!frame.startsWith('data:')) continue;
          const payload = frame.slice(5).trim();
          if (payload === '[DONE]') { onDone && onDone(); continue; }
          try {
            const msg = JSON.parse(payload);
            if (msg.error) { setError(msg.error); onError && onError(msg.error); }
            else if (msg.delta) onDelta && onDelta(msg.delta);
          } catch { /* partial frame — ignore */ }
        }
      }
      onDone && onDone();
    } catch (e) {
      if (e.name !== 'AbortError') { setError(String(e)); onError && onError(String(e)); }
    } finally {
      setStreaming(false);
    }
  }, []);

  const stop = useCallback(() => controllerRef.current?.abort(), []);

  return { start, stop, streaming, error };
}