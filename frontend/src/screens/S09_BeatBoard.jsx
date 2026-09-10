import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

const clean = (s) => (s || '')
  .replace(/â€¢/g, '•').replace(/â†’/g, '→').replace(/â†/g, '←')
  .replace(/â€”/g, '—').replace(/â€“/g, '–')
  .replace(/â€˜/g, "'").replace(/â€™/g, "'")
  .replace(/â€œ/g, '"').replace(/â€/g, '"');

const refColor = (ref) => {
  if (ref.startsWith('MT')) return 'bg-info/20 border-info text-info';
  if (ref.startsWith('RW')) return 'bg-warn/20 border-warn text-ink';
  if (ref.startsWith('E')) return 'bg-success/20 border-success text-success';
  return 'bg-danger/20 border-danger text-danger';
};

export default function S09_BeatBoard({ currentProject }) {
  const [beats, setBeats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [openBeat, setOpenBeat] = useState(null);
  const [manifest, setManifest] = useState(null);
  const [noteOpen, setNoteOpen] = useState(null);
  const [noteDraft, setNoteDraft] = useState('');

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/beats`)
        .then(r => r.json()).then(setBeats).catch(() => {});
  };
  useEffect(refresh, [currentProject]);

  const extract = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/beats/extract`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) alert('Extract failed:\n\n' + (data.detail || 'Unknown error'));
      else { alert(`Success! ${data.beats} beats, ${data.elements} elements, ${data.unmapped} unmapped.`); refresh(); }
    } catch (e) { alert('Network error: ' + e.message); }
    setLoading(false);
  };

  const collect = async (beatId, force = false) => {
    if (!force && openBeat === beatId) { setOpenBeat(null); setManifest(null); return; }
    setOpenBeat(beatId); setManifest(null);
    const res = await fetch(`/api/v1/projects/${currentProject.id}/beats/${beatId}/assets`);
    const data = await safeJson(res);
    if (!res.ok) { alert('Collect failed: ' + (data.detail || 'Unknown error')); setOpenBeat(null); return; }
    setManifest(data);
  };

  const composeAll = async () => {
    const res = await fetch(`/api/v1/projects/${currentProject.id}/prompts/compose`, { method: 'POST' });
    const data = await safeJson(res);
    if (!res.ok) { alert('Compose failed:\n\n' + (data.detail || 'Unknown error')); return; }
    alert(`Composed ${data.generations} generations (${data.masters} masters + ${data.dynamic} poses).\nLocked/skipped: ${data.skipped} · overlays cleaned: ${data.cleaned_overlays}`);
    if (openBeat) collect(openBeat, true);
  };

  const exportPack = async () => {
    const res = await fetch(`/api/v1/projects/${currentProject.id}/prompts/pack`);
    const data = await safeJson(res);
    if (!res.ok) { alert('Pack failed: ' + (data.detail || 'Unknown error')); return; }
    const c = data.counts;
    const paths = '07_beats/prompts/GENERATIONS.md\n07_beats/prompts/scenes.json';
    try { await navigator.clipboard.writeText(paths); } catch {}
    alert(`PROMPT PACK\n\n${c.generations} generations (${c.masters} masters + ${c.dynamic} poses)\n${c.static_rows} static rows · ${c.skipped} locked\n\nFiles (paths copied to clipboard):\n${paths}`);
  };

  const setDirective = async (a, val) => {
    const next = a.improv_note === val ? '' : val;
    await fetch(`/api/v1/projects/${currentProject.id}/beats/elements/${a.be_id}/note`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ improv_note: next })
    });
    collect(openBeat, true);
  };

  const openNote = (a) => {
    if (noteOpen === a.be_id) { setNoteOpen(null); return; }
    setNoteOpen(a.be_id);
    setNoteDraft(a.editor_note);
  };

  const saveNote = async (a) => {
    await fetch(`/api/v1/projects/${currentProject.id}/beats/elements/${a.be_id}/note`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ editor_note: noteDraft })
    });
    setNoteOpen(null);
    collect(openBeat, true);
  };

  const copyPrompt = async (a) => {
    try { await navigator.clipboard.writeText(a.prompt_text); }
    catch { alert('Copy failed — select the text manually.'); }
  };

  const remove = async (beatId) => {
    if (!confirm('Delete this beat?')) return;
    await fetch(`/api/v1/projects/${currentProject.id}/beats/${beatId}`, { method: 'DELETE' });
    refresh();
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
      </div>
    );
  }

  const groups = [];
  for (const b of beats) {
    let g = groups.find(x => x.chunk === b.chunk_id);
    if (!g) { g = { chunk: b.chunk_id, beats: [] }; groups.push(g); }
    g.beats.push(b);
  }

  const totalSec = beats.reduce((a, b) => a + b.duration_sec, 0);
  const totalElements = beats.reduce((a, b) => a + b.elements.length, 0);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex justify-between items-center flex-wrap gap-2">
        <h2 className="font-display text-2xl text-ink">Beat Board (P13)</h2>
        <div className="flex gap-2 flex-wrap">
          <BlockButton variant="secondary" onClick={composeAll}>🧩 Compose Prompts</BlockButton>
          <BlockButton variant="secondary" onClick={exportPack}>📤 Export Pack</BlockButton>
          <BlockButton onClick={extract} disabled={loading}>
            {loading ? 'Breaking down...' : '🎬 Re-Extract Beats'}
          </BlockButton>
        </div>
      </div>

      <div className="flex gap-3 flex-wrap">
        <span className="text-xs font-heading font-bold bg-panel border-2 border-ink px-3 py-1 rounded">{beats.length} BEATS</span>
        <span className="text-xs font-heading font-bold bg-panel border-2 border-ink px-3 py-1 rounded">
          ⏱ {Math.round(totalSec)}s (~{(totalSec / 60).toFixed(1)} min)
        </span>
        <span className="text-xs font-heading font-bold bg-panel border-2 border-ink px-3 py-1 rounded">{totalElements} ELEMENTS</span>
      </div>

      {beats.length === 0 && (
        <Card title="No Beats Yet">
          <p className="font-body text-sm text-ink/70">Click "Re-Extract Beats" to split the locked script into storyboard moments.</p>
        </Card>
      )}

      {groups.map((g, gi) => {
        const gSec = g.beats.reduce((a, b) => a + b.duration_sec, 0);
        return (
          <Card key={gi} title={`${g.chunk} (${g.beats.length} beats · ${Math.round(gSec)}s)`}>
            <div className="space-y-3">
              {g.beats.map(b => (
                <div key={b.id} className="p-3 border-2 border-ink/20 rounded-md bg-white">
                  <div className="flex items-start gap-3">
                    <span className="font-display text-xs text-ink/40 pt-1">{String(b.sort_order + 1).padStart(2, '0')}</span>
                    <div className="flex-1">
                      <p className="font-body text-sm text-ink mb-1">"{clean(b.text)}"</p>
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="font-mono text-ink/60">{b.duration_sec.toFixed(1)}s</span>
                        {b.duration_sec < 3.5 && (
                          <span className="font-bold bg-danger/10 border border-danger text-danger px-2 py-0.5 rounded"
                            title="Very short cut — consider merging with the neighbour beat">⚡ FLASH</span>
                        )}
                        {b.duration_sec > 11 && (
                          <span className="font-bold bg-warn/20 border border-warn px-2 py-0.5 rounded"
                            title="Long hold — consider splitting or adding motion">🐢 HOLD</span>
                        )}
                        {b.elements.filter(e => e.layer === 'background').length > 1 && (
                          <span className="font-bold bg-info/10 border border-info text-info px-2 py-0.5 rounded"
                            title="Two backgrounds — editor should crossfade them">🔄 CROSSFADE</span>
                        )}
                        <span className="italic text-ink/70">→ {clean(b.svo)}</span>
                        {b.text_only === 1 && (
                          <span className="font-bold bg-panel border-2 border-ink px-2 py-0.5 rounded">TEXT-ONLY</span>
                        )}
                        {b.overlay_text && (
                          <span className="font-bold bg-warn/20 border border-warn px-2 py-0.5 rounded">
                            🏷 {clean(b.overlay_text)} <span className="opacity-60">[{b.overlay_spec || 'graphic'}]</span>
                          </span>
                        )}
                      </div>
                      {b.elements.length > 0 && (
                        <div className="flex flex-wrap gap-1 mt-2">
                          {b.elements.map(el => (
                            <span key={el.id} className={`text-xs border px-2 py-0.5 rounded font-bold ${refColor(el.asset_ref)}`}>
                              {el.asset_ref} · {el.layer} · {el.framing}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                    <div className="flex flex-col gap-1">
                      <button onClick={() => collect(b.id)} title="Shot kit + prompts"
                        className="text-xs font-heading font-bold hover:text-info">📦</button>
                      <button onClick={() => remove(b.id)} className="text-xs font-heading font-bold text-danger hover:underline">🗑</button>
                    </div>
                  </div>

                  {openBeat === b.id && manifest && (
                    <div className="mt-2 p-2 border-2 border-info/40 bg-info/10 rounded space-y-2">
                      <p className="text-xs font-heading font-bold">
                        SHOT KIT: {manifest.ready}/{manifest.total} assets ready · {manifest.duration_sec.toFixed(1)}s
                        {manifest.overlay_text && <span className="ml-2 text-warn">🏷 {clean(manifest.overlay_text)}</span>}
                      </p>

                      {manifest.assets.map(a => (
                        <div key={a.be_id} className="p-2 bg-white border border-ink/20 rounded">
                          <div className="flex items-center gap-2 flex-wrap text-xs">
                            <span className={`font-bold px-2 py-0.5 rounded border ${
                              a.status === 'ready' ? 'border-success text-success bg-success/20' : 'border-danger text-danger bg-danger/10'}`}>
                              {a.status === 'ready' ? 'READY' : 'MISSING'}
                            </span>
                            <span className="font-mono">{a.asset_ref}</span>
                            <span>{a.title}</span>
                            <span className="text-ink/50 ml-auto">{a.layer} · {a.framing}</span>
                          </div>

                          {a.prompt_text ? (
                            <p className="mt-1 text-xs font-body text-ink/80 whitespace-pre-wrap bg-sky/10 border border-sky/30 rounded p-2 max-h-40 overflow-y-auto">
                              {a.prompt_text}
                            </p>
                          ) : (
                            <p className="mt-1 text-xs italic text-ink/50">No prompt yet — click 🧩 Compose Prompts.</p>
                          )}
                          {a.refs && <p className="text-xs text-ink/50 mt-1">refs: {a.refs}</p>}

                          <div className="flex gap-2 mt-2 flex-wrap items-center">
                            <button onClick={() => copyPrompt(a)} disabled={!a.prompt_text}
                              className="text-xs font-heading font-bold hover:text-info disabled:opacity-40">📋 copy</button>
                            <button onClick={() => setDirective(a, 'lock')}
                              className={`text-xs font-heading font-bold px-2 py-0.5 rounded border-2 ${
                                a.improv_note === 'lock' ? 'border-danger text-danger bg-danger/10' : 'border-ink/30'}`}>
                              {a.improv_note === 'lock' ? '🔒 locked' : '🔓 lock'}
                            </button>
                            <button onClick={() => setDirective(a, 'dynamic')}
                              className={`text-xs font-heading font-bold px-2 py-0.5 rounded border-2 ${
                                a.improv_note === 'dynamic' ? 'border-info text-info bg-info/10' : 'border-ink/30'}`}>D</button>
                            <button onClick={() => setDirective(a, 'static')}
                              className={`text-xs font-heading font-bold px-2 py-0.5 rounded border-2 ${
                                a.improv_note === 'static' ? 'border-success text-success bg-success/10' : 'border-ink/30'}`}>S</button>
                            <button onClick={() => openNote(a)}
                              className="text-xs font-heading font-bold hover:text-warn">✏️ note</button>
                          </div>

                          {noteOpen === a.be_id && (
                            <div className="mt-2">
                              <textarea name={`note_${a.be_id}`} value={noteDraft} rows={2}
                                onChange={e => setNoteDraft(e.target.value)}
                                className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-body text-xs"
                                placeholder={"diegetic: ship name 'Esperança'\nor free director notes..."} />
                              <div className="flex justify-end mt-1">
                                <BlockButton variant="secondary" onClick={() => saveNote(a)}>💾 save note</BlockButton>
                              </div>
                            </div>
                          )}
                        </div>
                      ))}

                      {manifest.total - manifest.ready > 0 && (
                        <p className="text-xs text-ink/60 italic">Missing assets → fill them in 📚 Library (use 🔎 for world ones).</p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
