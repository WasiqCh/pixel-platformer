import { useState, useEffect, useRef } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import { playSfx } from '../lib/sfx';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

export default function S11_Library({ currentProject }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [pendingLib, setPendingLib] = useState(null);
  const fileRef = useRef(null);

  const [gens, setGens] = useState([]);
  const [running, setRunning] = useState(false);
  const [showCfg, setShowCfg] = useState(false);
  const [cfg, setCfg] = useState({ provider: 'manual', model: 'gemini-2.5-flash-image', api_key: '' });
  const [keyDraft, setKeyDraft] = useState('');
  const [autoFor, setAutoFor] = useState(null);
  const [autoResults, setAutoResults] = useState([]);
  const [autoLoading, setAutoLoading] = useState(false);
  const [vaultCount, setVaultCount] = useState(0);

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/library`)
        .then(r => r.json()).then(setItems).catch(() => {});
  };
  useEffect(refresh, [currentProject]);

  const refreshGens = () => {
    if (!currentProject) return;
    fetch(`/api/v1/projects/${currentProject.id}/generations`)
      .then(r => r.json())
      .then(d => { setGens(d.rows || []); setRunning(d.running); })
      .catch(() => {});
  };
  useEffect(refreshGens, [currentProject]);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(refreshGens, 3000);
    return () => clearInterval(t);
  }, [running]);
  useEffect(() => {
    fetch('/api/v1/settings/image').then(r => r.json()).then(setCfg).catch(() => {});
  }, []);

  useEffect(() => {
    if (currentProject)
      fetch(`/api/v1/channels/${currentProject.channel_id}/vault`)
        .then(r => r.json()).then(d => setVaultCount((d || []).length)).catch(() => {});
  }, [currentProject]);

  const saveCfg = async () => {
    const body = { provider: cfg.provider, model: cfg.model };
    if (keyDraft.trim()) body.api_key = keyDraft.trim();
    const res = await fetch('/api/v1/settings/image', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    const d = await safeJson(res);
    if (!res.ok) alert('Save failed: ' + (d.detail || 'Unknown'));
    else {
      alert('Image settings saved.');
      setKeyDraft('');
      fetch('/api/v1/settings/image').then(r => r.json()).then(setCfg);
    }
  };

  const genOne = async (g) => {
    const res = await fetch(`/api/v1/projects/${currentProject.id}/generate/${g.id}`, { method: 'POST' });
    const d = await safeJson(res);
    if (!res.ok) { alert('Generate failed:\n\n' + (d.detail || 'Unknown')); return; }
    if (d.status === 'error') alert('Gemini error:\n' + d.error);
    refreshGens(); refresh();
  };

  const genAll = async () => {
    const res = await fetch(`/api/v1/projects/${currentProject.id}/generate/all`, { method: 'POST' });
    const d = await safeJson(res);
    if (!res.ok) { alert('Start failed:\n\n' + (d.detail || 'Unknown')); return; }
    setRunning(true);
  };

  const scaffold = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/library/scaffold`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) alert('Scaffold failed:\n\n' + (data.detail || 'Unknown error'));
      else { alert(`Library scaffolded: ${data.created} new slots (${data.reused || 0} reused from channel vault).`); refresh(); }
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

  const autoSearch = async (it) => {
    if (autoFor === it.id) { setAutoFor(null); return; }
    setAutoFor(it.id); setAutoResults([]); setAutoLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/world/${it.asset_ref}/autosearch`);
      const d = await safeJson(res);
      if (!res.ok) alert('Auto-search failed: ' + (d.detail || 'Unknown'));
      else setAutoResults(d.results || []);
    } catch (e) { alert('Network error: ' + e.message); }
    setAutoLoading(false);
  };

  const pickAuto = async (c) => {
    if (!confirm(`Download this image into the slot?\nLicense: ${c.license}\nAuthor: ${c.author || 'unknown'}\nSource: ${c.source_url}`)) return;
    const res = await fetch(`/api/v1/projects/${currentProject.id}/library/${autoFor}/download`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: c.file_url, source_url: c.source_url, license: c.license, author: c.author }) });
    const d = await safeJson(res);
    if (!res.ok) alert('Download failed: ' + (d.detail || 'Unknown'));
    else { setAutoFor(null); refresh(); }
  };

  const autoPanel = () => (
    <div className="mt-1 p-2 border-2 border-info/40 bg-info/10 rounded">
      {autoLoading ? <p className="text-xs font-body">Searching Wikimedia Commons (free licenses only)…</p> :
        autoResults.length === 0 ? <p className="text-xs font-body">No free-license results — use 🔎 manual search instead.</p> :
        <div className="grid grid-cols-4 gap-2">
          {autoResults.map((c, i) => (
            <button key={i} onClick={() => pickAuto(c)}
              className="text-left bg-white border-2 border-ink/30 rounded p-1 hover:border-info">
              <img src={c.thumb} alt={c.title} className="w-full h-20 object-cover rounded" />
              <p className="text-[10px] font-bold truncate">{c.license}</p>
              <p className="text-[10px] text-ink/60 truncate">{c.author || 'unknown author'}</p>
            </button>
          ))}
        </div>}
    </div>
  );

  // You generate images outside the app, so the checkpoint's "n/m ready" gate would
  // otherwise nag forever. This records that an asset exists without uploading it.
  const setStatus = async (libId, status) => {
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/library/${libId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status })
      });
      if (!res.ok) { const d = await safeJson(res); alert('Update failed: ' + (d.detail || 'Unknown')); return; }
      playSfx('save');
      refresh();
    } catch (e) { alert('Network error: ' + e.message); }
  };

  const markAllReady = async () => {
    const empty = items.filter(i => i.status !== 'ready');
    if (!empty.length) return;
    if (!confirm(`Mark all ${empty.length} remaining slots ready?\nUse this when you generated them outside the app.`)) return;
    for (const it of empty) {
      await fetch(`/api/v1/projects/${currentProject.id}/library/${it.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'ready' })
      });
    }
    playSfx('success');
    refresh();
  };

  const downloadPack = async () => {
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/work-pack`);
      const d = await safeJson(res);
      if (!res.ok) { alert('Work pack failed: ' + (d.detail || 'Unknown')); playSfx('error'); return; }
      const url = URL.createObjectURL(new Blob([d.content], { type: 'text/markdown' }));
      const a = document.createElement('a');
      a.href = url; a.download = d.filename; a.click();
      URL.revokeObjectURL(url);
      playSfx('save');
    } catch (e) { alert('Network error: ' + e.message); playSfx('error'); }
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
  const gensReady = gens.filter(g => g.status === 'ready').length;

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
      {it.source === 'channel' && <span className="text-xs font-bold text-info" title="Reused from channel vault">🌐</span>}
      {it.kind === 'world' && (
        <BlockButton variant="secondary" onClick={() => openSearch(it)} title="Open image search">🔎</BlockButton>
      )}
      {it.kind === 'world' && (
        <BlockButton variant="secondary" onClick={() => autoSearch(it)} title="Auto-search free-license images">✨</BlockButton>
      )}
      <BlockButton variant="secondary" onClick={() => setStatus(it.id, it.status === 'ready' ? 'empty' : 'ready')}
        title={it.status === 'ready' ? 'Mark as not ready' : 'Mark ready without uploading'}>
        {it.status === 'ready' ? '↩' : '✓'}
      </BlockButton>
      <BlockButton variant="secondary" onClick={() => pickFile(it.id)}>📤</BlockButton>
      <button onClick={() => remove(it.id)} className="text-xs font-heading font-bold text-danger hover:underline">🗑</button>
    </div>
  );

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="font-display text-2xl text-ink">Asset Library + Download Desk</h2>
        <div className="flex gap-2">
          <BlockButton variant="secondary" onClick={downloadPack}
            title="One file with every prompt in generation order, for working outside the app">
            ⬇ Work pack
          </BlockButton>
          <BlockButton onClick={scaffold} disabled={loading}>
            {loading ? 'Scaffolding...' : '🧱 Scaffold Library'}
          </BlockButton>
        </div>
      </div>

      <input ref={fileRef} type="file" accept="image/*,.png,.jpg,.jpeg,.webp" onChange={onFile} className="hidden" />

      {items.length > 0 && (
        <div className="p-3 border-2 border-ink rounded-md bg-panel">
          <div className="flex justify-between text-xs font-heading font-bold mb-1">
            <span>PRODUCTION READINESS</span>
            <span>{ready} / {items.length} assets ready ({pct}%)</span>
            <span>🌐 vault: {vaultCount} reusable</span>
          </div>
          <div className="flex justify-end mb-1">
            <BlockButton variant="secondary" onClick={markAllReady}
              disabled={ready === items.length}
              title="Generated everything outside the app? Mark the rest ready.">
              ✓ Mark all remaining ready
            </BlockButton>
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
              <div className="space-y-2 max-h-[28rem] overflow-y-auto pr-1">
                {worlds.map(w => (
                  <div key={w.id}>
                    {row(w)}
                    {autoFor === w.id && autoPanel()}
                  </div>
                ))}
              </div>
            </Card>
          </div>
        </div>
      )}

      <Card title={`Generation Queue — ${gensReady}/${gens.length} ready${running ? ' · RUNNING…' : ''}`}>
        <div className="flex flex-wrap gap-2 mb-3 items-center">
          <BlockButton onClick={genAll} disabled={running}>{running ? 'Generating…' : '▶ Generate All'}</BlockButton>
          <BlockButton variant="secondary" onClick={() => setShowCfg(!showCfg)}>⚙️ Nano Banana settings</BlockButton>
          <span className="text-xs font-body text-ink/60">provider: {cfg.provider} · key: {cfg.api_key || 'none'}</span>
        </div>

        {showCfg && (
          <div className="p-3 border-2 border-ink/30 rounded-md bg-white mb-3 space-y-2">
            <label className="text-xs font-heading font-bold block">Provider
              <select value={cfg.provider} onChange={e => setCfg({ ...cfg, provider: e.target.value })}
                className="ml-2 border-2 border-ink rounded px-2 py-1 text-xs">
                <option value="manual">manual (copy-paste)</option>
                <option value="gemini">gemini (Nano Banana)</option>
              </select>
            </label>
            <label className="text-xs font-heading font-bold block">Gemini API key (free at aistudio.google.com/apikey)
              <input type="password" value={keyDraft} onChange={e => setKeyDraft(e.target.value)}
                placeholder={cfg.api_key || 'paste key…'}
                className="mt-1 w-full border-2 border-ink rounded px-2 py-1 text-xs" name="gemini_key" />
            </label>
            <label className="text-xs font-heading font-bold block">Model
              <input value={cfg.model} onChange={e => setCfg({ ...cfg, model: e.target.value })}
                className="mt-1 w-full border-2 border-ink rounded px-2 py-1 text-xs" name="gemini_model" />
            </label>
            <div className="flex justify-end">
              <BlockButton variant="secondary" onClick={saveCfg}>💾 save</BlockButton>
            </div>
          </div>
        )}

        <div className="space-y-2 max-h-[30rem] overflow-y-auto pr-1">
          {gens.length === 0 && (
            <p className="text-xs font-body text-ink/60">Queue empty — click 🧩 Compose Prompts on the Beat Board first.</p>
          )}
          {gens.map(g => (
            <div key={g.id} className="p-2 border-2 border-ink/20 rounded-md bg-white flex items-center gap-3">
              {g.status === 'ready' ? (
                <img src={`/api/v1/projects/${currentProject.id}/generations/${g.id}/image`} alt={g.gen_label}
                  className="w-14 h-14 object-cover rounded border border-ink/30" />
              ) : (
                <div className="w-14 h-14 rounded border border-ink/20 bg-panel flex items-center justify-center text-lg">
                  {g.kind === 'master' ? '🖼️' : '🎭'}
                </div>
              )}
              <div className="flex-1 min-w-0">
                <p className="font-heading text-xs font-bold">
                  {g.gen_label} · {g.title} <span className="text-ink/50">({g.kind})</span>
                </p>
                <p className="text-xs font-body text-ink/60 truncate">{g.prompt}</p>
                {g.status === 'error' && <p className="text-xs text-danger truncate" title={g.error}>⚠ {g.error}</p>}
              </div>
              <span className={`text-xs font-bold px-2 py-1 rounded border-2 ${
                g.status === 'ready' ? 'border-success text-success bg-success/10'
                : g.status === 'error' ? 'border-danger text-danger bg-danger/10'
                : 'border-ink/30 text-ink/50'}`}>
                {g.status.toUpperCase()}
              </span>
              <BlockButton variant="secondary" onClick={() => genOne(g)} disabled={running}>▶</BlockButton>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
