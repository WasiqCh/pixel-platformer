import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

// D2-T01 — Assets page (read-only): every scene need in one list with
// provenance badge + status + thumbnail (existing image endpoints only;
// labelled box when no PNG). Copy-prompt copies the exact stored prompt
// (generations.prompt — the same text P2-T04 stores and builds the svg_gen
// context from via _svg_asset_info/_build_svg_context) verbatim to the
// clipboard. No writes, no new endpoints.
export default function S15_Assets({ currentProject }) {
  const [needs, setNeeds] = useState([]);
  const [gensById, setGensById] = useState({});
  const [libById, setLibById] = useState({});
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(null);
  const [imgDead, setImgDead] = useState({});
  const [filter, setFilter] = useState('all');
  const [msg, setMsg] = useState('');
  // D2-T02 — paste-code + bring-my-own (per-asset). Paste box POSTs external
  // SVG through POST .../generate/svg/{gen_id}/paste {code} (real
  // SvgGen/validate_svg_text path backend-side, versioned _vN, pointer move,
  // source='pasted' so the badge below flips to PASTED). Pending rows read
  // "bring my own" (skip-generation); generated rows read "paste-code (new
  // version)". Old versions + revert intact (versions endpoint untouched).
  const [pasteOpen, setPasteOpen] = useState(null);
  const [pasteDraft, setPasteDraft] = useState('');
  const [pasteBusy, setPasteBusy] = useState(false);
  const [pasteMsg, setPasteMsg] = useState({});

  // Read-only loads (existing list endpoints only). Effect loader carries
  // no synchronous setState (async .then sets only, S09 pattern) so the
  // effect itself stays warning-free; the button loader adds its own busy flag.
  const loadEffect = () => {
    if (!currentProject) return;
    fetch(`/api/v1/projects/${currentProject.id}/scenes/assets`)
      .then((r) => r.json())
      .then((rows) => setNeeds(Array.isArray(rows) ? rows : []))
      .catch(() => {});
    fetch(`/api/v1/projects/${currentProject.id}/generations`)
      .then(safeJson)
      .then((d) => {
        const rows = Array.isArray(d.rows) ? d.rows : (Array.isArray(d) ? d : []);
        const m = {};
        rows.forEach((g) => { m[g.id] = g; });
        setGensById(m);
      })
      .catch(() => {});
    fetch(`/api/v1/projects/${currentProject.id}/library`)
      .then((r) => r.json())
      .then((rows) => {
        const lm = {};
        (Array.isArray(rows) ? rows : []).forEach((l) => { lm[l.id] = l; });
        setLibById(lm);
      })
      .catch(() => setMsg('Could not load assets. Is the backend running?'));
  };
  useEffect(loadEffect, [currentProject]);

  const refresh = () => {
    if (!currentProject) return;
    setLoading(true);
    setMsg('');
    Promise.all([
      fetch(`/api/v1/projects/${currentProject.id}/scenes/assets`).then((r) => r.json()),
      fetch(`/api/v1/projects/${currentProject.id}/generations`).then(safeJson),
      fetch(`/api/v1/projects/${currentProject.id}/library`).then((r) => r.json()),
    ])
      .then(([assets, gens, lib]) => {
        setNeeds(Array.isArray(assets) ? assets : []);
        const rows = Array.isArray(gens.rows) ? gens.rows : (Array.isArray(gens) ? gens : []);
        const m = {};
        rows.forEach((g) => { m[g.id] = g; });
        setGensById(m);
        const lm = {};
        (Array.isArray(lib) ? lib : []).forEach((l) => { lm[l.id] = l; });
        setLibById(lm);
      })
      .catch(() => setMsg('Could not load assets. Is the backend running?'))
      .finally(() => setLoading(false));
  };

  // Provenance badge logic (D2-T01 must already handle PASTED ahead of D2-T02):
  // LIBRARY = scene need carries library_ref; PASTED = its generation carries
  // source='pasted' (set by D2-T02 on first paste, no frontend change needed);
  // otherwise GENERATED = needs_generate + gen status. No backend source column
  // exists yet, so gen.source is undefined today and every svg need reads GENERATED.
  const provenanceOf = (asset) => {
    if (asset.library_ref) return 'LIBRARY';
    const gen = gensById[asset.generation_id];
    if (gen && gen.source === 'pasted') return 'PASTED';
    return 'GENERATED';
  };

  const copyPrompt = async (asset) => {
    const gen = gensById[asset.generation_id];
    if (!gen) { setMsg(`No generation row for "${asset.name}" — nothing to copy.`); return; }
    try {
      // Byte-equals: write the stored prompt verbatim — no trim, no reformat.
      await navigator.clipboard.writeText(gen.prompt);
      setCopied(asset.id);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      setMsg('Copy failed — select the prompt text manually.');
    }
  };

  const sayPaste = (assetId, m) => setPasteMsg((p) => ({ ...p, [assetId]: m }));

  const sendPaste = async (asset) => {
    const code = (pasteDraft || '').trim();
    if (!code) { sayPaste(asset.id, 'Paste SVG markup first — code box is empty.'); return; }
    if (!asset.generation_id) { sayPaste(asset.id, 'Library match — nothing to paste into.'); return; }
    setPasteBusy(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/generate/svg/${asset.generation_id}/paste`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      const data = await safeJson(res);
      if (!res.ok) { sayPaste(asset.id, 'Paste rejected: ' + (data.detail || 'Unknown error')); return; }
      // Badge flips to PASTED without a full reload: patch the gen row's
      // source in place, then re-fetch for the pointer (svg_path/status).
      setGensById((m) => ({
        ...m,
        [asset.generation_id]: {
          ...m[asset.generation_id],
          source: 'pasted',
          svg_path: data.svg_path || m[asset.generation_id]?.svg_path,
          status: data.status || m[asset.generation_id]?.status,
        },
      }));
      setPasteOpen(null);
      setPasteDraft('');
      sayPaste(asset.id, `✓ pasted → v${data.version} (${data.status}, source=pasted)`);
    } catch (e) { sayPaste(asset.id, 'Network error: ' + e.message); } finally { setPasteBusy(false); }
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
      </div>
    );
  }

  const counts = { all: needs.length, GENERATED: 0, LIBRARY: 0, PASTED: 0 };
  needs.forEach((a) => { counts[provenanceOf(a)] += 1; });
  const shown = filter === 'all' ? needs : needs.filter((a) => provenanceOf(a) === filter);

  const badgeStyle = (prov) => {
    if (prov === 'LIBRARY') return 'border-info text-info bg-info/10';
    if (prov === 'PASTED') return 'border-warn text-ink bg-warn/20';
    return 'border-success text-success bg-success/10';
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex justify-between items-center flex-wrap gap-2">
        <h2 className="font-display text-2xl text-ink">Assets (D2)</h2>
        <BlockButton variant="secondary" onClick={refresh} disabled={loading}>
          {loading ? 'Loading…' : '↻ Refresh'}
        </BlockButton>
      </div>

      <div className="flex gap-3 flex-wrap">
        <span className="text-xs font-heading font-bold bg-panel border-2 border-ink px-3 py-1 rounded">{needs.length} NEEDS</span>
        <span className="text-xs font-heading font-bold bg-panel border-2 border-ink px-3 py-1 rounded">{counts.GENERATED} GENERATED</span>
        <span className="text-xs font-heading font-bold bg-panel border-2 border-ink px-3 py-1 rounded">{counts.LIBRARY} LIBRARY</span>
        <span className="text-xs font-heading font-bold bg-panel border-2 border-ink px-3 py-1 rounded">{counts.PASTED} PASTED</span>
      </div>

      <Card title={`All assets${filter !== 'all' ? ` · filtered: ${filter}` : ''} (paste live in D2-T02 · playground lands in D2-T03)`}>
        <div className="flex gap-2 flex-wrap mb-3">
          {['all', 'GENERATED', 'LIBRARY', 'PASTED'].map((f) => (
            <BlockButton key={f} variant="secondary" onClick={() => setFilter(f)}>
              {filter === f ? `● ${f}` : f}
            </BlockButton>
          ))}
        </div>
        {msg && <p className="mb-2 text-xs font-heading text-primary">{msg}</p>}
        {needs.length === 0 ? (
          <p className="font-body text-sm text-ink/70">
            No scene assets yet — run ① Plan scenes then ② Plan assets on the Beat Board first.
          </p>
        ) : (
          <div className="space-y-2 max-h-[60rem] overflow-y-auto pr-1">
            {shown.map((a) => {
              const prov = provenanceOf(a);
              const gen = gensById[a.generation_id];
              const lib = a.library_ref ? libById[a.library_ref] : null;
              const status = a.library_ref
                ? (lib ? lib.status : `library ${a.library_ref}`)
                : (gen ? gen.status : `gen ${a.generation_id} missing`);
              const hasPng = !!(gen && (gen.file_path || '').trim() && !imgDead[a.generation_id]);
              return (
                <div key={a.id} className="p-2 border-2 border-ink/20 rounded-md bg-white flex items-start gap-3">
                  {a.generation_id && hasPng ? (
                    <img
                      src={`/api/v1/projects/${currentProject.id}/generations/${a.generation_id}/image`}
                      alt={a.name}
                      loading="lazy"
                      onError={() => setImgDead((p) => ({ ...p, [a.generation_id]: true }))}
                      className="w-20 h-20 object-cover rounded border border-ink/30 shrink-0"
                    />
                  ) : (
                    <div className="w-20 h-20 rounded border-2 border-dashed border-ink/30 bg-panel flex flex-col items-center justify-center text-center px-1 shrink-0">
                      <span className="text-[10px] font-heading font-bold text-ink/60">NO PNG</span>
                      <span className="text-[9px] font-mono text-ink/50 truncate w-full" title={a.library_ref ? `library ${a.library_ref}` : `gen ${a.generation_id} · ${gen ? gen.status : 'missing'}`}>
                        {a.library_ref ? a.library_ref : `gen ${a.generation_id}`}
                      </span>
                    </div>
                  )}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-xs font-bold px-2 py-0.5 rounded border-2 ${badgeStyle(prov)}`}>{prov}</span>
                      <span className="font-heading text-sm font-bold truncate">{a.name}</span>
                      <span className="text-xs font-mono text-ink/50">{a.kind} · {a.beat_id}{a.generation_id ? ` · gen ${a.generation_id}` : ''}{a.library_ref ? ` · ${a.library_ref}` : ''}</span>
                      <span className="text-xs font-mono text-ink/60 ml-auto">{status}</span>
                    </div>
                    <p className="mt-1 text-xs font-body text-ink/60 truncate" title={a.search_query}>
                      🔎 {a.search_query}
                    </p>
                    {gen && (
                      <p className="mt-1 text-xs font-body text-ink/80 whitespace-pre-wrap bg-sky/10 border border-sky/30 rounded p-2 max-h-24 overflow-y-auto" title="Stored prompt (generations.prompt) — copy-prompt copies this byte-for-byte">
                        {gen.prompt}
                      </p>
                    )}
                    {a.library_ref && lib && (
                      <p className="mt-1 text-xs font-body text-ink/60 truncate" title={lib.title}>
                        📚 {lib.title}{lib.file_path ? ` · ${lib.file_path.split('/').pop()}` : ' · no file yet'}
                      </p>
                    )}
                    <div className="flex gap-2 mt-2 flex-wrap items-center">
                      {a.generation_id && gen ? (
                        <>
                          <button
                            onClick={() => copyPrompt(a)}
                            title="Copy the exact stored prompt (generations.prompt) to the clipboard"
                            className="text-xs font-heading font-bold hover:text-info"
                          >
                            {copied === a.id ? '✓ Copied!' : '📋 copy-prompt'}
                          </button>
                          <button
                            onClick={() => { setPasteOpen(pasteOpen === a.id ? null : a.id); setPasteDraft(''); }}
                            title={gen.status === 'pending'
                              ? 'Bring my own: paste external SVG instead of generating (heals pending rows)'
                              : 'Paste external SVG as a new versioned _vN (history kept, revert intact)'}
                            className="text-xs font-heading font-bold hover:text-warn"
                          >
                            {gen.status === 'pending' ? '🧳 bring my own' : '📥 paste-code'}
                          </button>
                        </>
                      ) : (
                        <span className="text-xs italic text-ink/50">library match — no svg prompt to copy</span>
                      )}
                    </div>
                    {pasteOpen === a.id && a.generation_id && gen && (
                      <div className="mt-2">
                        <textarea
                          name={`paste_${a.id}`}
                          value={pasteDraft}
                          rows={4}
                          onChange={(e) => setPasteDraft(e.target.value)}
                          className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-mono text-xs"
                          placeholder={`Paste external SVG for "${a.name}" (gen ${a.generation_id}) — validated like AI output, saved as versioned _vN, source flips to PASTED…`}
                        />
                        <div className="flex justify-end gap-2 mt-1">
                          <BlockButton variant="secondary" onClick={() => { setPasteOpen(null); setPasteDraft(''); }}>
                            Cancel
                          </BlockButton>
                          <BlockButton disabled={pasteBusy} onClick={() => sendPaste(a)}>
                            {pasteBusy ? 'Pasting…' : '📥 paste as new version'}
                          </BlockButton>
                        </div>
                      </div>
                    )}
                    {pasteMsg[a.id] && <p className="mt-1 text-xs font-heading text-primary">{pasteMsg[a.id]}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
