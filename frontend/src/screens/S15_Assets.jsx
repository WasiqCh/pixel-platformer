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
  // D2-T03 — SVG playground (validate + raster, no project writes). Code box
  // → Preview button → PNG shown → Download button. POSTs pasted code to
  // POST .../svg-playground {code} (real validate_svg_text path, Inkscape
  // raster to a hash-named %TEMP% PNG, PNG bytes back). Reads the PNG as a
  // blob → object URL for both preview and download. Touches no
  // scenes/gens/library state — fully separate from the list above.
  const [pgCode, setPgCode] = useState('');
  const [pgBusy, setPgBusy] = useState(false);
  const [pgMsg, setPgMsg] = useState('');
  const [pgUrl, setPgUrl] = useState(null);
  const [pgHash, setPgHash] = useState('');
  // S-T04 — per-asset web-fetch + image upload. Fetch: search box (defaults
  // to the need's search_query) → GET .../fetch-search?q= (Wikimedia,
  // license-filtered) → per-result Attach → POST .../fetch {file_url,
  // source_url, license, author} (versioned file, license recorded,
  // source='fetched'). Upload: file input (.svg/.png/.jpg/.jpeg) → POST
  // .../upload multipart (validated, versioned, source='uploaded'). Both
  // patch the gen row in place (badge flips, thumbnail refreshes via the
  // file_path key); history stays on disk (versions endpoint lists both).
  const [fetchOpen, setFetchOpen] = useState(null);
  const [fetchQ, setFetchQ] = useState('');
  const [fetchBusy, setFetchBusy] = useState(false);
  const [fetchFound, setFetchFound] = useState({});
  const [fetchMsg, setFetchMsg] = useState({});
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadMsg, setUploadMsg] = useState({});
  // I-T03 — local recolor (fill-swap, zero AI). Click a fill swatch → wheel
  // → preview updates (client-side swatch preview, no code visible) → Apply
  // POSTs {mapping:{old:new}} to POST .../generate/svg/{gen_id}/recolor
  // (versioned _vN, pointer move, history intact — same semantics as
  // improve). Thumbnail PNG refreshes on approve (same ladder as paste);
  // the panel re-fetches fills after apply so the new palette shows.
  const [recolorOpen, setRecolorOpen] = useState(null);
  const [recolorFills, setRecolorFills] = useState({});
  const [recolorBusy, setRecolorBusy] = useState(false);
  const [recolorOld, setRecolorOld] = useState({});
  const [recolorNew, setRecolorNew] = useState({});
  const [recolorMsg, setRecolorMsg] = useState({});

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
  // FETCHED/UPLOADED = S-T04 web-fetch / image-upload (source set by POST
  // .../fetch or POST .../upload — manual always wins, badge shows it);
  // otherwise GENERATED = needs_generate + gen status.
  const provenanceOf = (asset) => {
    if (asset.library_ref) return 'LIBRARY';
    const gen = gensById[asset.generation_id];
    if (gen && gen.source === 'pasted') return 'PASTED';
    if (gen && gen.source === 'fetched') return 'FETCHED';
    if (gen && gen.source === 'uploaded') return 'UPLOADED';
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

  // D2-T03 playground preview: POST code → PNG blob → object URL (preview +
  // download share it). Invalid code shows the validator message, no image.
  const previewPlayground = async () => {
    const code = (pgCode || '').trim();
    if (!code) { setPgMsg('Paste SVG markup first — code box is empty.'); return; }
    if (pgUrl) { URL.revokeObjectURL(pgUrl); setPgUrl(null); }
    setPgBusy(true);
    setPgMsg('');
    setPgHash('');
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/svg-playground`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      });
      if (!res.ok) {
        const data = await safeJson(res);
        setPgMsg('Playground rejected: ' + (data.detail || 'Unknown error'));
        return;
      }
      const blob = await res.blob();
      setPgUrl(URL.createObjectURL(blob));
      const hash = res.headers.get('X-Svg-Hash') || '';
      setPgHash(hash);
      const hit = res.headers.get('X-Playground-Cached') === 'true';
      setPgMsg(`✓ preview 1920×1080 PNG (${blob.size}B${hit ? ' · cache hit — same bytes' : ' · fresh raster'}) · nothing written to the project`);
    } catch (e) { setPgMsg('Network error: ' + e.message); } finally { setPgBusy(false); }
  };

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

  const sayFetch = (assetId, m) => setFetchMsg((p) => ({ ...p, [assetId]: m }));
  const sayUpload = (assetId, m) => setUploadMsg((p) => ({ ...p, [assetId]: m }));

  // S-T04 fetch-through-web: search Wikimedia (license-filtered) for this
  // asset, then attach the picked result (license recorded on the row).
  const runFetchSearch = async (asset) => {
    const q = (fetchQ || '').trim();
    if (!q) { sayFetch(asset.id, 'Type a search first — defaults to the need’s 🔎 query.'); return; }
    if (!asset.generation_id) { sayFetch(asset.id, 'Library match — nothing to fetch into.'); return; }
    setFetchBusy(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/generate/svg/${asset.generation_id}/fetch-search?q=${encodeURIComponent(q)}`);
      const data = await safeJson(res);
      if (!res.ok) { sayFetch(asset.id, 'Search failed: ' + (data.detail || 'Unknown error')); return; }
      const results = Array.isArray(data.results) ? data.results : [];
      setFetchFound((p) => ({ ...p, [asset.id]: { query: data.query || q, results } }));
      sayFetch(asset.id, results.length === 0
        ? `No freely-licensed files for “${data.query || q}” — try other words.`
        : `${results.length} freely-licensed file(s) for “${data.query || q}” — Attach one.`);
    } catch (e) { sayFetch(asset.id, 'Network error: ' + e.message); } finally { setFetchBusy(false); }
  };

  const attachFetch = async (asset, item) => {
    if (!asset.generation_id || !item) return;
    setFetchBusy(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/generate/svg/${asset.generation_id}/fetch`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          file_url: item.file_url, source_url: item.source_url || '',
          license: item.license || '', author: item.author || '',
        }),
      });
      const data = await safeJson(res);
      if (!res.ok) { sayFetch(asset.id, 'Attach failed: ' + (data.detail || 'Unknown error')); return; }
      // User file wins: badge flips to FETCHED, thumbnail swaps to the real
      // file (img key on file_path below), license line appears.
      setGensById((m) => ({
        ...m,
        [asset.generation_id]: {
          ...m[asset.generation_id],
          source: 'fetched',
          file_path: data.file_path || m[asset.generation_id]?.file_path,
          status: data.status || m[asset.generation_id]?.status,
          license: data.license || '',
          source_url: data.source_url || '',
        },
      }));
      setImgDead((p) => ({ ...p, [asset.generation_id]: false }));
      sayFetch(asset.id, `✓ fetched → v${data.version} (${item.license || 'license recorded'}) — history kept`);
    } catch (e) { sayFetch(asset.id, 'Network error: ' + e.message); } finally { setFetchBusy(false); }
  };

  // S-T04 image upload: .svg/.png/.jpg/.jpeg file → versioned, pointer moved
  // (user file wins), history kept. Raster previews immediately; SVG needs
  // approve (same ladder as paste).
  const sendUpload = async (asset, file) => {
    if (!file) return;
    if (!asset.generation_id) { sayUpload(asset.id, 'Library match — nothing to upload into.'); return; }
    setUploadBusy(true);
    try {
      const form = new FormData();
      form.append('file', file, file.name);
      const res = await fetch(`/api/v1/projects/${currentProject.id}/generate/svg/${asset.generation_id}/upload`, {
        method: 'POST', body: form,
      });
      const data = await safeJson(res);
      if (!res.ok) { sayUpload(asset.id, 'Upload rejected: ' + (data.detail || 'Unknown error')); return; }
      setGensById((m) => ({
        ...m,
        [asset.generation_id]: {
          ...m[asset.generation_id],
          source: 'uploaded',
          svg_path: data.svg_path || m[asset.generation_id]?.svg_path,
          // SVG upload onto a fetched row drops the stale raster pointer
          // (backend returns file_path:"") — thumbnail honestly flips to
          // NO-PNG until approve rasters the new SVG.
          file_path: (data.file_path !== undefined ? data.file_path : m[asset.generation_id]?.file_path),
          status: data.status || m[asset.generation_id]?.status,
        },
      }));
      setImgDead((p) => ({ ...p, [asset.generation_id]: false }));
      sayUpload(asset.id, data.svg_path
        ? `✓ uploaded SVG → ${data.svg_path.split('/').pop()} (approve to raster)`
        : `✓ uploaded image → ${data.file_path.split('/').pop()} (preview shows it now)`);
    } catch (e) { sayUpload(asset.id, 'Network error: ' + e.message); } finally { setUploadBusy(false); }
  };

  const sayRecolor = (assetId, m) => setRecolorMsg((p) => ({ ...p, [assetId]: m }));

  // <input type="color"> needs #RRGGBB — named colors / #RGB / #RRGGBBAA
  // fall back to blue; hex-6 passes through (wheel shows the current fill).
  const wheelDefault = (fill) => {
    if (typeof fill === 'string' && /^#[0-9a-fA-F]{6}$/.test(fill.trim())) return fill.trim();
    if (typeof fill === 'string' && /^#[0-9a-fA-F]{3}$/.test(fill.trim())) {
      const h = fill.trim().slice(1);
      return `#${h[0]}${h[0]}${h[1]}${h[1]}${h[2]}${h[2]}`;
    }
    return '#0000FF';
  };

  // I-T03 recolor: open panel → GET fills (swatches) → click swatch picks
  // old → wheel picks new (preview box updates live) → Apply POSTs mapping.
  const openRecolor = async (asset) => {
    if (recolorOpen === asset.id) { setRecolorOpen(null); return; }
    if (!asset.generation_id) { sayRecolor(asset.id, 'Library match — nothing to recolor.'); return; }
    setRecolorOpen(asset.id);
    sayRecolor(asset.id, '');
    setRecolorBusy(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/generate/svg/${asset.generation_id}/fills`);
      const data = await safeJson(res);
      if (!res.ok) { sayRecolor(asset.id, 'Fills unavailable: ' + (data.detail || 'Unknown error')); return; }
      const fills = Array.isArray(data.fills) ? data.fills : [];
      setRecolorFills((p) => ({ ...p, [asset.id]: { fills, svg_path: data.svg_path || '' } }));
      if (fills.length > 0) {
        setRecolorOld((p) => ({ ...p, [asset.id]: p[asset.id] || fills[0] }));
        setRecolorNew((p) => ({ ...p, [asset.id]: p[asset.id] || wheelDefault(fills[0]) }));
      } else {
        sayRecolor(asset.id, 'No fills found in the current SVG — nothing to swap.');
      }
    } catch (e) { sayRecolor(asset.id, 'Network error: ' + e.message); } finally { setRecolorBusy(false); }
  };

  const applyRecolor = async (asset) => {
    const old = (recolorOld[asset.id] || '').trim();
    const fresh = (recolorNew[asset.id] || '').trim();
    if (!old) { sayRecolor(asset.id, 'Click a fill swatch first — no source color picked.'); return; }
    if (!fresh) { sayRecolor(asset.id, 'Pick a new color from the wheel first.'); return; }
    if (!asset.generation_id) { sayRecolor(asset.id, 'Library match — nothing to recolor.'); return; }
    setRecolorBusy(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/generate/svg/${asset.generation_id}/recolor`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mapping: { [old]: fresh } }),
      });
      const data = await safeJson(res);
      if (!res.ok) { sayRecolor(asset.id, 'Recolor rejected: ' + (data.detail || 'Unknown error')); return; }
      // New version, pointer moved, history intact: patch the gen row (same
      // shape as paste) so badges/counts stay truthful; PNG refreshes on
      // approve (same ladder as paste — honest note below).
      setGensById((m) => ({
        ...m,
        [asset.generation_id]: {
          ...m[asset.generation_id],
          svg_path: data.svg_path || m[asset.generation_id]?.svg_path,
          status: data.status || m[asset.generation_id]?.status,
        },
      }));
      sayRecolor(asset.id, `✓ recolored ${old} → ${fresh} (swapped ${data.swapped}, → v${data.version}) — approve to raster the new PNG`);
      const rf = await fetch(`/api/v1/projects/${currentProject.id}/generate/svg/${asset.generation_id}/fills`);
      const rd = await safeJson(rf);
      if (rf.ok) {
        const fills = Array.isArray(rd.fills) ? rd.fills : [];
        setRecolorFills((p) => ({ ...p, [asset.id]: { fills, svg_path: rd.svg_path || '' } }));
        if (fills.length > 0 && !fills.includes(old)) {
          setRecolorOld((p) => ({ ...p, [asset.id]: fills[0] }));
          setRecolorNew((p) => ({ ...p, [asset.id]: wheelDefault(fills[0]) }));
        }
      }
    } catch (e) { sayRecolor(asset.id, 'Network error: ' + e.message); } finally { setRecolorBusy(false); }
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
      </div>
    );
  }

  const counts = { all: needs.length, GENERATED: 0, LIBRARY: 0, PASTED: 0, FETCHED: 0, UPLOADED: 0 };
  needs.forEach((a) => { counts[provenanceOf(a)] += 1; });
  const shown = filter === 'all' ? needs : needs.filter((a) => provenanceOf(a) === filter);

  const badgeStyle = (prov) => {
    if (prov === 'LIBRARY') return 'border-info text-info bg-info/10';
    if (prov === 'PASTED') return 'border-warn text-ink bg-warn/20';
    if (prov === 'FETCHED') return 'border-info text-info bg-sky/10';
    if (prov === 'UPLOADED') return 'border-warn text-ink bg-warn/20';
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
        <span className="text-xs font-heading font-bold bg-panel border-2 border-ink px-3 py-1 rounded">{counts.FETCHED} FETCHED</span>
        <span className="text-xs font-heading font-bold bg-panel border-2 border-ink px-3 py-1 rounded">{counts.UPLOADED} UPLOADED</span>
      </div>

      <Card title={`All assets${filter !== 'all' ? ` · filtered: ${filter}` : ''} (fetch + upload live in S-T04 · playground below)`}>
        <div className="flex gap-2 flex-wrap mb-3">
          {['all', 'GENERATED', 'LIBRARY', 'PASTED', 'FETCHED', 'UPLOADED'].map((f) => (
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
                      key={gen.file_path || a.generation_id}
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
                    {gen && gen.license && (
                      <p className="mt-1 text-xs font-body text-ink/60 truncate" title={gen.source_url || gen.license}>
                        © {gen.license}{gen.source_url ? (
                          <> · <a href={gen.source_url} target="_blank" rel="noreferrer" className="underline hover:text-info">source</a></>
                        ) : null}
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
                          <button
                            onClick={() => {
                              const opening = fetchOpen !== a.id;
                              setFetchOpen(opening ? a.id : null);
                              if (opening && !fetchQ) setFetchQ(a.search_query || '');
                            }}
                            title="Fetch through the web: Wikimedia search (freely licensed) → Attach (license recorded, versioned, history kept)"
                            className="text-xs font-heading font-bold hover:text-info"
                          >
                            🌐 web-fetch
                          </button>
                          <label
                            title="Upload image (.svg/.png/.jpg/.jpeg): validated, versioned, your file wins, history kept"
                            className={`text-xs font-heading font-bold hover:text-warn cursor-pointer${uploadBusy ? ' opacity-40 pointer-events-none' : ''}`}
                          >
                            {uploadBusy ? '⏳ uploading…' : '📤 upload'}
                            <input
                              type="file"
                              accept=".svg,.png,.jpg,.jpeg"
                              className="hidden"
                              onChange={(e) => { const f = e.target.files && e.target.files[0]; e.target.value = ''; if (f) sendUpload(a, f); }}
                            />
                          </label>
                          <button
                            onClick={() => openRecolor(a)}
                            title="Local recolor: click a fill swatch → wheel → Apply (new version, history kept, zero AI, no code visible)"
                            className="text-xs font-heading font-bold hover:text-info"
                          >
                            {recolorOpen === a.id ? '🎨 recolor… (open)' : '🎨 recolor'}
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
                    {fetchOpen === a.id && a.generation_id && gen && (
                      <div className="mt-2 p-2 border-2 border-info/40 bg-info/10 rounded space-y-2">
                        <div className="flex gap-2">
                          <input
                            name={`fetch_${a.id}`}
                            value={fetchOpen === a.id ? fetchQ : ''}
                            onChange={(e) => setFetchQ(e.target.value)}
                            onKeyDown={(e) => { if (e.key === 'Enter') runFetchSearch(a); }}
                            className="flex-1 bg-white border-2 border-ink rounded px-2 py-1 font-body text-xs"
                            placeholder={`Search Wikimedia for "${a.name}"…`}
                          />
                          <BlockButton variant="secondary" disabled={fetchBusy} onClick={() => runFetchSearch(a)}>
                            {fetchBusy ? 'Searching…' : '🔎 Search'}
                          </BlockButton>
                        </div>
                        {(fetchFound[a.id]?.results || []).map((r, i) => (
                          <div key={i} className="flex items-center gap-2 bg-white border border-ink/20 rounded p-1">
                            {r.thumb ? (
                              <img src={r.thumb} alt={r.title} loading="lazy" className="w-12 h-12 object-cover rounded border border-ink/20 shrink-0" />
                            ) : (
                              <div className="w-12 h-12 rounded border border-dashed border-ink/30 bg-panel shrink-0" />
                            )}
                            <div className="flex-1 min-w-0">
                              <p className="text-xs font-heading font-bold truncate" title={r.title}>{r.title}</p>
                              <p className="text-[11px] font-body text-ink/60 truncate">© {r.license}{r.author ? ` · ${r.author.slice(0, 60)}` : ''}</p>
                            </div>
                            <BlockButton variant="secondary" disabled={fetchBusy} onClick={() => attachFetch(a, r)}>
                              Attach
                            </BlockButton>
                          </div>
                        ))}
                      </div>
                    )}
                    {fetchMsg[a.id] && <p className="mt-1 text-xs font-heading text-primary">{fetchMsg[a.id]}</p>}
                    {uploadMsg[a.id] && <p className="mt-1 text-xs font-heading text-primary">{uploadMsg[a.id]}</p>}
                    {recolorOpen === a.id && a.generation_id && gen && (
                      <div className="mt-2 p-2 border-2 border-warn/50 bg-warn/10 rounded space-y-2">
                        <p className="text-xs font-heading font-bold">🎨 Recolor — click a swatch, spin the wheel, Apply (no code, new version kept)</p>
                        {(recolorFills[a.id]?.fills || []).length > 0 ? (
                          <>
                            <div className="flex gap-2 flex-wrap">
                              {(recolorFills[a.id]?.fills || []).map((f) => (
                                <button
                                  key={f}
                                  onClick={() => {
                                    setRecolorOld((p) => ({ ...p, [a.id]: f }));
                                    setRecolorNew((p) => ({ ...p, [a.id]: wheelDefault(f) }));
                                  }}
                                  title={`Swap ${f} → wheel color`}
                                  className={`flex items-center gap-1 px-2 py-1 rounded border-2 text-xs font-mono${(recolorOld[a.id] || (recolorFills[a.id]?.fills || [])[0]) === f ? ' border-ink bg-white' : ' border-ink/20 bg-white/60'}`}
                                >
                                  <span className="inline-block w-4 h-4 rounded border border-ink/40" style={{ backgroundColor: f }} />
                                  {f}
                                </button>
                              ))}
                            </div>
                            <div className="flex gap-3 items-center flex-wrap bg-white border border-ink/20 rounded p-2">
                              <span className="text-xs font-heading font-bold">old</span>
                              <span className="inline-block w-8 h-8 rounded border-2 border-ink" style={{ backgroundColor: recolorOld[a.id] || (recolorFills[a.id]?.fills || [])[0] }} />
                              <span className="text-xs font-mono">{recolorOld[a.id] || (recolorFills[a.id]?.fills || [])[0]}</span>
                              <span className="text-xs font-heading font-bold">→ new</span>
                              <input
                                type="color"
                                aria-label={`New color for ${recolorOld[a.id] || 'fill'}`}
                                value={/^#[0-9a-fA-F]{6}$/.test(recolorNew[a.id] || '') ? recolorNew[a.id] : wheelDefault(recolorOld[a.id] || '#0000FF')}
                                onChange={(e) => setRecolorNew((p) => ({ ...p, [a.id]: e.target.value }))}
                                className="w-10 h-8 cursor-pointer bg-white border-2 border-ink rounded"
                              />
                              <span className="inline-block w-8 h-8 rounded border-2 border-ink" style={{ backgroundColor: recolorNew[a.id] || '#0000FF' }} />
                              <span className="text-xs font-mono">{recolorNew[a.id] || ''}</span>
                              <BlockButton variant="secondary" disabled={recolorBusy} onClick={() => applyRecolor(a)}>
                                {recolorBusy ? 'Recoloring…' : '🎨 Apply recolor'}
                              </BlockButton>
                              <BlockButton variant="secondary" onClick={() => setRecolorOpen(null)}>
                                Close
                              </BlockButton>
                            </div>
                            <p className="text-[11px] font-body text-ink/60">Preview updates on the swatches now; the PNG thumbnail refreshes after approve (same ladder as paste).</p>
                          </>
                        ) : (
                          <p className="text-xs font-body text-ink/60">{recolorBusy ? 'Loading fills…' : 'No fills loaded yet.'}</p>
                        )}
                      </div>
                    )}
                    {recolorMsg[a.id] && <p className="mt-1 text-xs font-heading text-primary">{recolorMsg[a.id]}</p>}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Card title="SVG playground (D2-T03 — validate + raster, no project writes)">
        <p className="font-body text-sm text-ink/70 mb-2">
          Paste any SVG → Preview → 1920×1080 PNG below → Download. Same validator the AI output
          passes through; rasters via the project Inkscape probe to a hash-named temp file
          (never into project dirs). Nothing here touches scenes, generations, or the library.
        </p>
        <textarea
          name="playground_code"
          value={pgCode}
          rows={6}
          onChange={(e) => setPgCode(e.target.value)}
          className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-mono text-xs"
          placeholder={'Paste SVG markup (must carry viewBox + width + height, no <script>/external refs)…'}
        />
        <div className="flex gap-2 mt-2 flex-wrap items-center">
          <BlockButton disabled={pgBusy} onClick={previewPlayground}>
            {pgBusy ? 'Rastering…' : '🖼️ Preview PNG'}
          </BlockButton>
          {pgUrl && (
            <a
              href={pgUrl}
              download={pgHash ? `svg_playground_${pgHash.slice(0, 12)}.png` : 'svg_playground.png'}
              className="text-xs font-heading font-bold hover:text-info"
            >
              ⬇ Download PNG
            </a>
          )}
        </div>
        {pgMsg && <p className="mt-2 text-xs font-heading text-primary">{pgMsg}</p>}
        {pgUrl ? (
          <img
            src={pgUrl}
            alt="SVG playground preview (1920×1080 raster)"
            className="mt-2 w-full rounded border-2 border-ink/30"
          />
        ) : (
          <div className="mt-2 w-full aspect-video rounded border-2 border-dashed border-ink/30 bg-panel flex items-center justify-center">
            <span className="text-xs font-heading font-bold text-ink/50">NO PREVIEW — paste code, hit Preview PNG</span>
          </div>
        )}
      </Card>
    </div>
  );
}
