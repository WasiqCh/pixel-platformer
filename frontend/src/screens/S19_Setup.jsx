import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

// D5+D10-T02 — Setup screen (first-run green ticks + one-click fix).
// Probes (never typed paths): Python packages, Inkscape (existing probe),
// ffmpeg (existing probe), Kokoro deps + weights (D4-T01 findings), Ollama
// connection. Each missing item gets ONE Fix button (winget for binaries,
// pip for packages, download for weights). Status re-probes after every fix.
// App.jsx auto-opens this screen on launch while anything is red — free
// navigation still holds (leave and come back anytime, nothing is blocked).
const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

export default function S19_Setup({ onNavigate }) {
  const [checks, setChecks] = useState(null);
  const [allOk, setAllOk] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [msg, setMsg] = useState({});
  const [loadErr, setLoadErr] = useState('');

  const load = async () => {
    setLoading(true); setLoadErr('');
    try {
      const res = await fetch('/api/v1/setup/status');
      const data = await safeJson(res);
      if (!res.ok) { setLoadErr(data.detail || 'Status failed'); return; }
      setChecks(data.checks || []);
      setAllOk(!!data.all_ok);
    } catch (e) { setLoadErr('Network error: ' + e.message); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const fix = async (id) => {
    if (busy) return;
    setBusy(id);
    setMsg(m => ({ ...m, [id]: 'Fixing… (this can take minutes for installs/downloads)' }));
    try {
      const res = await fetch(`/api/v1/setup/fix/${id}`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) { setMsg(m => ({ ...m, [id]: 'Fix failed: ' + (data.detail || 'Unknown error') })); return; }
      const tail = (data.output || '').split('\n').slice(-3).join(' / ').slice(0, 220);
      setMsg(m => ({ ...m, [id]: `${data.fixed ? '✓' : '•'} ${data.detail}${tail ? ' — ' + tail : ''}` }));
      await load();
    } catch (e) { setMsg(m => ({ ...m, [id]: 'Network error: ' + e.message })); }
    setBusy(null);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex justify-between items-center flex-wrap gap-2">
        <h2 className="font-display text-2xl text-ink">Setup — machine checks</h2>
        <div className="flex gap-2">
          <BlockButton variant="secondary" onClick={load} disabled={loading || busy !== null}>
            {loading ? 'Checking…' : '↻ Re-check'}
          </BlockButton>
          {onNavigate && (
            <BlockButton variant="secondary" onClick={() => onNavigate('home')}>
              ← Home
            </BlockButton>
          )}
        </div>
      </div>

      {allOk === true && (
        <Card title="All green ✓">
          <p className="font-body text-sm text-ink/70">
            Your machine can run the whole road — art, voice, render. Pick a project and walk it top to bottom.
          </p>
        </Card>
      )}

      {allOk === false && (
        <Card title="Needs attention">
          <p className="font-body text-sm text-ink/70">
            Each red row gets <span className="font-bold">one Fix button</span> (one click each).
            Nothing asks you to type a path or install anything by hand. You can leave and come back anytime —
            this screen opens itself on launch while anything is red.
          </p>
        </Card>
      )}

      {loadErr && (
        <Card title="Status failed">
          <p className="font-body text-sm text-danger">{loadErr}</p>
        </Card>
      )}

      {loading && !checks && (
        <Card title="Checking…">
          <p className="font-body text-sm text-ink/60">Probing packages, binaries, voice, and AI…</p>
        </Card>
      )}

      {(checks || []).map(c => (
        <Card key={c.id} title={`${c.ok ? '✅' : '❌'} ${c.label}`}>
          <p className="font-mono text-xs text-ink/70 whitespace-pre-wrap break-words">{c.detail}</p>
          <p className="mt-1 font-mono text-xs text-ink/40 break-words">fix runs: {c.fix_command}</p>
          {msg[c.id] && <p className="mt-2 text-xs font-heading text-primary whitespace-pre-wrap break-words">{msg[c.id]}</p>}
          {!c.ok && (
            <div className="mt-3">
              <BlockButton onClick={() => fix(c.id)} disabled={busy !== null}>
                {busy === c.id ? 'Fixing…' : `🔧 ${c.fix_label}`}
              </BlockButton>
            </div>
          )}
        </Card>
      ))}
    </div>
  );
}
