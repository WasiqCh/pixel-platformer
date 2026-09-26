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

const PALETTE = ['#5b8def', '#f2a541', '#6bbf59', '#e05e5e', '#9b6bd6', '#4ecdc4', '#f7b32b', '#7a6ff0'];

export default function S09_BeatBoard({ currentProject }) {
  const [beats, setBeats] = useState([]);
  const [loading, setLoading] = useState(false);
  const [openBeat, setOpenBeat] = useState(null);
  const [manifest, setManifest] = useState(null);
  const [noteOpen, setNoteOpen] = useState(null);
  const [noteDraft, setNoteDraft] = useState('');
  const [voRunning, setVoRunning] = useState(false);
  const [voDone, setVoDone] = useState(0);
  const [voTotal, setVoTotal] = useState(0);
  // SCENES-MP4 P3-T02: scene preview + 3-button row. Approve hits the real
  // PUT scenes endpoint; fix-note/regen go through the beat's first SVG asset
  // via the real svg improve/regenerate endpoints (beats with no SVG asset
  // get an honest inline message — no scene-level AI endpoint exists yet).
  const [scenes, setScenes] = useState({});
  const [sceneAssets, setSceneAssets] = useState({});
  const [sceneBusy, setSceneBusy] = useState(null);
  const [fixOpen, setFixOpen] = useState(null);
  const [fixDraft, setFixDraft] = useState('');
  const [sceneMsg, setSceneMsg] = useState({});
  const [previewDead, setPreviewDead] = useState({});

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/beats`)
        .then(r => r.json()).then(setBeats).catch(() => {});
  };
  useEffect(refresh, [currentProject]);

  const refreshScenes = () => {
    if (!currentProject) return;
    fetch(`/api/v1/projects/${currentProject.id}/scenes`)
      .then(r => r.json())
      .then(rows => {
        const m = {};
        (Array.isArray(rows) ? rows : []).forEach(s => { m[s.beat_id] = s; });
        setScenes(m);
      }).catch(() => {});
    fetch(`/api/v1/projects/${currentProject.id}/scenes/assets`)
      .then(r => r.json())
      .then(rows => {
        const m = {};
        (Array.isArray(rows) ? rows : []).forEach(a => { (m[a.beat_id] = m[a.beat_id] || []).push(a); });
        setSceneAssets(m);
      }).catch(() => {});
  };
  useEffect(refreshScenes, [currentProject]);

  const sayScene = (beatId, msg) => setSceneMsg(m => ({ ...m, [beatId]: msg }));

  const approveScene = async (beatId) => {
    setSceneBusy(beatId);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/scenes/${beatId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'approved' })
      });
      const data = await safeJson(res);
      if (!res.ok) { sayScene(beatId, 'Approve failed: ' + (data.detail || 'Unknown error')); return; }
      setScenes(s => ({ ...s, [beatId]: { ...s[beatId], status: 'approved' } }));
      sayScene(beatId, '✓ scene approved (1 click)');
    } catch (e) { sayScene(beatId, 'Network error: ' + e.message); } finally { setSceneBusy(null); }
  };

  const firstSvgAsset = (beatId) => (sceneAssets[beatId] || []).find(a => a.generation_id);

  const sendFixNote = async (beatId) => {
    const note = fixDraft.trim();
    if (!note) { sayScene(beatId, 'Write a note first — what should change?'); return; }
    const asset = firstSvgAsset(beatId);
    if (!asset) {
      sayScene(beatId, 'No SVG asset on this beat — note kept, scene-level improve lands in a later ticket.');
      return;
    }
    setSceneBusy(beatId);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/generate/svg/${asset.generation_id}/improve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note })
      });
      const data = await safeJson(res);
      if (!res.ok) { sayScene(beatId, 'Improve failed: ' + (data.detail || 'Unknown error')); return; }
      setFixOpen(null); setFixDraft('');
      sayScene(beatId, `✓ "${asset.name}" improve → v${data.version} (${data.status})`);
    } catch (e) { sayScene(beatId, 'Network error: ' + e.message); } finally { setSceneBusy(null); }
  };

  const regenAsset = async (beatId) => {
    const asset = firstSvgAsset(beatId);
    if (!asset) {
      sayScene(beatId, 'No SVG asset on this beat — nothing to regenerate (all library matches).');
      return;
    }
    if (!confirm(`Regenerate "${asset.name}" (gen ${asset.generation_id}) as a NEW version?\nOld versions are kept, never overwritten.`)) return;
    setSceneBusy(beatId);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/generate/svg/${asset.generation_id}`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) { sayScene(beatId, 'Regenerate failed: ' + (data.detail || 'Unknown error')); return; }
      if (data.status === 'error') { sayScene(beatId, 'Asset error: ' + (data.error || 'Unknown')); return; }
      sayScene(beatId, `✓ "${asset.name}" regen → v${data.version} (${data.status})`);
    } catch (e) { sayScene(beatId, 'Network error: ' + e.message); } finally { setSceneBusy(null); }
  };

  const extract = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/beats/extract`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) alert('Extract failed:\n\n' + (data.detail || 'Unknown error'));
      else {
        alert(`Success! ${data.beats} beats, ${data.elements} elements, ${data.unmapped} unmapped.` +
          (data.compose ? `\nPrompts auto-composed: ${data.compose.generations} generations.` : ''));
        refresh();
      }
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

  const jumpTo = (beatId) => {
    collect(beatId, true);
    setTimeout(() => {
      const el = document.getElementById(`beat-${beatId}`);
      if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 50);
  };

  const startVoice = async () => {
    const res = await fetch(`/api/v1/projects/${currentProject.id}/voiceover/build`, { method: 'POST' });
    const d = await safeJson(res);
    if (!res.ok) { alert('Voiceover failed:\n\n' + (d.detail || 'Unknown error')); return; }
    setVoRunning(true);
    const t = setInterval(async () => {
      const r = await fetch(`/api/v1/projects/${currentProject.id}/voiceover/status`);
      const s = await r.json();
      setVoDone(s.done); setVoTotal(s.total);
      if (!s.running) {
        clearInterval(t);
        setVoRunning(false);
        alert(`Voiceover done: ${s.total} beats retimed to REAL speech.\nWAV files saved in 08_export/voiceover/`);
        refresh();
      }
    }, 3000);
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

  const mergeNext = async (b) => {
    if (!confirm(`Merge ${b.id} with the NEXT beat in the same section?\nThe next beat's text and elements get absorbed into ${b.id}.`)) return;
    const res = await fetch(`/api/v1/projects/${currentProject.id}/beats/${b.id}/merge_next`, { method: 'POST' });
    const data = await safeJson(res);
    if (!res.ok) { alert('Merge failed:\n\n' + (data.detail || 'Unknown error')); return; }
    alert(`Merged into ${data.merged_into} (removed ${data.removed}).\nPrompts recomposed: ${data.compose.generations} generations.`);
    refresh();
    if (openBeat) collect(openBeat, true);
  };

  const splitBeat = async (b) => {
    if (!confirm(`Split ${b.id} into two beats at the middle sentence?`)) return;
    const res = await fetch(`/api/v1/projects/${currentProject.id}/beats/${b.id}/split`, { method: 'POST' });
    const data = await safeJson(res);
    if (!res.ok) { alert('Split failed:\n\n' + (data.detail || 'Unknown error')); return; }
    alert(`Split into ${data.part1} + ${data.part2}.\nPrompts recomposed: ${data.compose.generations} generations.`);
    refresh();
    if (openBeat) collect(openBeat, true);
  };

  const isLastInChunk = (g, b) => g.beats[g.beats.length - 1].id === b.id;


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
          <BlockButton variant="secondary" onClick={startVoice} disabled={voRunning}>
            {voRunning ? `🎙️ ${voDone}/${voTotal}…` : '🎙️ Narrate & Retime'}
          </BlockButton>
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

      {beats.length > 0 && (
        <Card title="Timeline — click a block to jump to that beat">
          <div className="flex gap-0.5 h-12 w-full pt-2">
            {beats.map(b => {
              const gi = groups.findIndex(g => g.chunk === b.chunk_id);
              const color = PALETTE[gi % PALETTE.length];
              return (
                <button key={b.id} onClick={() => jumpTo(b.id)}
                  title={`${b.id} · ${b.duration_sec.toFixed(1)}s · ${b.text.slice(0, 70)}`}
                  className="relative rounded-sm border border-ink/30 hover:opacity-80"
                  style={{ flexGrow: b.duration_sec, minWidth: '8px', backgroundColor: color }}>
                  <span className="absolute inset-0 flex items-center justify-center text-[9px] font-bold text-white">
                    {b.duration_sec >= 4 ? b.sort_order + 1 : ''}
                  </span>
                  {b.duration_sec < 3.5 && <span className="absolute -top-2 left-0 text-[10px]">⚡</span>}
                  {b.duration_sec > 11 && <span className="absolute -top-2 left-0 text-[10px]">🐢</span>}
                  {b.overlay_text && <span className="absolute bottom-0 right-0 text-[8px]">🏷</span>}
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap gap-3 mt-3">
            {groups.map((g, gi) => (
              <span key={gi} className="flex items-center gap-1 text-xs font-body text-ink/70">
                <span className="w-3 h-3 rounded-sm border border-ink/30" style={{ backgroundColor: PALETTE[gi % PALETTE.length] }} />
                {g.chunk}
              </span>
            ))}
          </div>
        </Card>
      )}

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
                <div key={b.id} id={`beat-${b.id}`} className="p-3 border-2 border-ink/20 rounded-md bg-white">
                  <div className="flex items-start gap-3">
                    <span className="font-display text-xs text-ink/40 pt-1">{String(b.sort_order + 1).padStart(2, '0')}</span>
                    <div className="flex-1">
                      <p className="font-body text-sm text-ink mb-1">"{clean(b.text)}"</p>
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="font-mono text-ink/60">{b.duration_sec.toFixed(1)}s</span>
                        <span className="font-mono text-ink/50">{b.word_count}w</span>
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
                      <button onClick={() => mergeNext(b)} title="Merge with next beat (same section)"
                        disabled={isLastInChunk(g, b)}
                        className="text-xs font-heading font-bold hover:text-success disabled:opacity-30">⤵️</button>
                      <button onClick={() => splitBeat(b)} title="Split at middle sentence"
                        className="text-xs font-heading font-bold hover:text-warn">✂️</button>
                      <button onClick={() => remove(b.id)} className="text-xs font-heading font-bold text-danger hover:underline">🗑</button>
                    </div>
                  </div>

                  {scenes[b.id] ? (
                    <div className="mt-2 p-2 border-2 border-success/40 bg-success/5 rounded">
                      <div className="flex items-center gap-2 flex-wrap text-xs">
                        <span className={`font-bold px-2 py-0.5 rounded border ${
                          scenes[b.id].status === 'approved'
                            ? 'border-success text-success bg-success/20'
                            : 'border-warn text-ink bg-warn/20'}`}>
                          {scenes[b.id].status === 'approved' ? '✓ SCENE APPROVED' : 'SCENE DRAFT'}
                        </span>
                        <span className="text-ink/50 font-mono">{(sceneAssets[b.id] || []).length} assets</span>
                      </div>
                      {!previewDead[b.id] ? (
                        <img src={`/api/v1/projects/${currentProject.id}/scenes/${b.id}/preview`}
                          alt={`Scene preview ${b.id}`} loading="lazy"
                          onError={() => setPreviewDead(p => ({ ...p, [b.id]: true }))}
                          className="mt-2 w-full rounded border border-ink/20" />
                      ) : (
                        <p className="mt-2 text-xs italic text-ink/50">Preview unavailable for {b.id}.</p>
                      )}
                      <div className="flex gap-2 mt-2 flex-wrap">
                        <BlockButton variant="secondary" disabled={sceneBusy === b.id || scenes[b.id].status === 'approved'}
                          onClick={() => approveScene(b.id)}>
                          {scenes[b.id].status === 'approved' ? '✓ Approved' : '✅ Approve scene'}
                        </BlockButton>
                        <BlockButton variant="secondary"
                          onClick={() => { setFixOpen(fixOpen === b.id ? null : b.id); setFixDraft(''); }}>
                          📝 Fix-note
                        </BlockButton>
                        <BlockButton variant="secondary" disabled={sceneBusy === b.id}
                          onClick={() => regenAsset(b.id)}>
                          🔁 Regen one asset
                        </BlockButton>
                      </div>
                      {sceneMsg[b.id] && <p className="mt-1 text-xs font-heading text-primary">{sceneMsg[b.id]}</p>}
                      {fixOpen === b.id && (
                        <div className="mt-2">
                          <textarea name={`fix_${b.id}`} value={fixDraft} rows={2}
                            onChange={e => setFixDraft(e.target.value)}
                            className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-body text-xs"
                            placeholder="What should change in the asset's next version? (sent to the beat's first SVG asset)" />
                          <div className="flex justify-end mt-1">
                            <BlockButton variant="secondary" disabled={sceneBusy === b.id}
                              onClick={() => sendFixNote(b.id)}>📨 send to improve</BlockButton>
                          </div>
                        </div>
                      )}
                    </div>
                  ) : (
                    <p className="mt-2 text-xs italic text-ink/50">No scene row — plan scenes first (API).</p>
                  )}

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
