import { useState, useEffect, useRef } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

export default function S11_Library({ currentProject }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [pendingLib, setPendingLib] = useState(null);
  const fileRef = useRef(null);

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/library`)
        .then(r => r.json()).then(setItems).catch(() => {});
  };
  useEffect(refresh, [currentProject]);

  const scaffold = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/library/scaffold`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) alert('Scaffold failed:\n\n' + (data.detail || 'Unknown error'));
      else { alert(`Library scaffolded: ${data.created} new slots.`); refresh(); }
    } catch (e) { alert('Network error: ' + e.message); }
    setLoading(false);
  };

  const pickFile = (libId) => { setPendingLib(libId); fileRef.current.click(); };

  const onFile = async (e) => {
    const f = e.target.files && e.target.files[0];
    e.target.value = '';
    if (!f || !pendingLib) return;
    const fd = new FormData();
    fd.append('file', f);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/library/${pendingLib}/upload`,
        { method: 'POST', body: fd });
      const data = await safeJson(res);
      if (!res.ok) alert('Upload failed: ' + (data.detail || 'Unknown error'));
      refresh();
    } catch (err) { alert('Network error: ' + err.message); }
    setPendingLib(null);
  };

  const openSearch = (it) => {
    const q = (it.search_query || it.title) + ' ' + (it.era_hint || '');
    window.open('https://www.google.com/search?q=' + encodeURIComponent(q.trim()) + '&tbm=isch', '_blank');
  };

  const remove = async (libId) => {
    if (!confirm('Delete this library slot?')) return;
    await fetch(`/api/v1/projects/${currentProject.id}/library/${libId}`, { method: 'DELETE' });
    refresh();
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
      </div>
    );
  }

  const ready = items.filter(i => i.status === 'ready').length;
  const pct = items.length ? Math.round((ready / items.length) * 100) : 0;
  const chars = items.filter(i => i.kind === 'character');
  const envs = items.filter(i => i.kind === 'environment');
  const worlds = items.filter(i => i.kind === 'world');

  const row = (it) => (
    <div key={it.id} className={`p-3 border-2 rounded-md flex items-center gap-3 ${
      it.status === 'ready' ? 'border-success bg-success/10' : 'border-ink/20 bg-white'}`}>
      <span className="font-mono text-xs text-ink/50 w-14">{it.id}</span>
      <div className="flex-1">
        <p className="font-heading text-sm font-bold">{it.title}</p>
        <p className="text-xs font-body text-ink/60">
          {it.asset_ref} · {it.status === 'ready' ? it.file_path.split('/').pop() : 'no asset yet'}
        </p>
      </div>
      <span className={`text-xs font-bold px-2 py-1 rounded border-2 ${
        it.status === 'ready' ? 'border-success text-success bg-success/20' : 'border-ink/30 text-ink/50'}`}>
        {it.status === 'ready' ? 'READY' : 'EMPTY'}
      </span>
      {it.kind === 'world' && (
        <BlockButton variant="secondary" onClick={() => openSearch(it)} title="Open image search">🔎</BlockButton>
      )}
      <BlockButton variant="secondary" onClick={() => pickFile(it.id)}>📤</BlockButton>
      <button onClick={() => remove(it.id)} className="text-xs font-heading font-bold text-danger hover:underline">🗑</button>
    </div>
  );

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="font-display text-2xl text-ink">Asset Library + Download Desk</h2>
        <BlockButton onClick={scaffold} disabled={loading}>
          {loading ? 'Scaffolding...' : '🧱 Scaffold Library'}
        </BlockButton>
      </div>

      <input ref={fileRef} type="file" accept="image/*,.png,.jpg,.jpeg,.webp" onChange={onFile} className="hidden" />

      {items.length > 0 && (
        <div className="p-3 border-2 border-ink rounded-md bg-panel">
          <div className="flex justify-between text-xs font-heading font-bold mb-1">
            <span>PRODUCTION READINESS</span>
            <span>{ready} / {items.length} assets ready ({pct}%)</span>
          </div>
          <div className="h-4 border-2 border-ink rounded overflow-hidden bg-white">
            <div className="h-full bg-success transition-all" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      {items.length === 0 ? (
        <Card title="No Library Yet">
          <p className="font-body text-sm text-ink/70">Click "Scaffold Library" to create slots for cast, locations and world assets.</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Card title={`Characters (${chars.length})`}>
            <div className="space-y-2 max-h-[28rem] overflow-y-auto pr-1">{chars.map(row)}</div>
          </Card>
          <Card title={`Environments (${envs.length})`}>
            <div className="space-y-2 max-h-[28rem] overflow-y-auto pr-1">{envs.map(row)}</div>
          </Card>
          <div className="md:col-span-2">
            <Card title={`World / Real Assets (${worlds.length}) — 🔎 opens the exact image search`}>
              <div className="space-y-2 max-h-[28rem] overflow-y-auto pr-1">{worlds.map(row)}</div>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
