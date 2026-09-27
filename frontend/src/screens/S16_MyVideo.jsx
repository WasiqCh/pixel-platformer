import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import RenderProgress from '../components/RenderProgress';

// D5+D10-T03 — My Video (full output, was a T01 placeholder). Plain-words
// render (shared <RenderProgress>: scene counts, named-scene errors + Resume)
// + versioned finals list reading 08_handoff/ via the new read-only
// GET .../render/finals, click-to-play + Download per MP4 via
// GET .../render/file/{name} (FileResponse pattern, like the PNG image
// endpoints). Render control reuses existing endpoints only.
const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

const versionOf = (name) => {
  const m = String(name || '').match(/_final_v(\d+)\.mp4$/);
  if (m) return `Version ${parseInt(m[1], 10)}`;
  if (/_final\.mp4$/.test(String(name || ''))) return 'Version 1';
  return name;
};

const mbOf = (size) => {
  const n = Number(size || 0);
  if (!n) return '';
  return `${(n / 1048576).toFixed(1)} MB`;
};

export default function S16_MyVideo({ currentProject }) {
  const [finals, setFinals] = useState([]);
  const [latest, setLatest] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadErr, setLoadErr] = useState('');

  const pid = currentProject?.id;

  const load = async (quiet) => {
    if (!pid) return;
    if (!quiet) setLoading(true);
    setLoadErr('');
    try {
      const res = await fetch(`/api/v1/projects/${pid}/render/finals`);
      const data = await safeJson(res);
      if (!res.ok) { if (!quiet) setLoadErr(data.detail || 'Could not list videos.'); return; }
      setFinals(Array.isArray(data.finals) ? data.finals : []);
      setLatest(data.latest || '');
    } catch (e) { if (!quiet) setLoadErr('Network hiccup — try again. (' + e.message + ')'); }
    if (!quiet) setLoading(false);
  };

  useEffect(() => {
    setFinals([]); setLatest(''); setLoadErr('');
    if (!pid) return;
    load(false);
    const t = setInterval(() => load(true), 10000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">My Video</h2>
        <p className="font-body text-sm text-ink/70">Pick a project first — its finished MP4s will live here.</p>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h2 className="font-display text-2xl text-ink">My Video</h2>

      <Card title="Your video (plain words)">
        <RenderProgress currentProject={currentProject} />
        <p className="mt-2 font-body text-xs text-ink/60">
          Finished videos appear below to watch and keep. Making another version never deletes the old ones.
        </p>
      </Card>

      <Card
        title={`Finished videos (${finals.length})`}
        actions={
          <BlockButton variant="secondary" onClick={() => load(false)} disabled={loading}>
            {loading ? 'Checking…' : '↻ Refresh'}
          </BlockButton>
        }
      >
        {loadErr && <p className="font-body text-xs text-danger mb-2">{loadErr}</p>}
        {finals.length === 0 && !loadErr && (
          <p className="font-body text-sm text-ink/70">
            No finished videos yet — approve your scenes on the Beats page, press Render, and they will appear here to watch and download.
          </p>
        )}
        <div className="space-y-4">
          {finals.map((f) => {
            const url = `/api/v1/projects/${pid}/render/file/${encodeURIComponent(f.name)}`;
            const isLatest = latest && latest.endsWith(f.name);
            return (
              <div key={f.name} className="p-3 border-2 border-ink/20 rounded-md bg-white">
                <div className="flex items-center gap-2 flex-wrap text-xs mb-2">
                  <span className="font-heading font-bold">{versionOf(f.name)}</span>
                  {isLatest && (
                    <span className="font-bold px-2 py-0.5 rounded border border-success text-success bg-success/20">LATEST</span>
                  )}
                  <span className="font-mono text-ink/60">{f.name}</span>
                  {mbOf(f.size) && <span className="font-mono text-ink/50 ml-auto">{mbOf(f.size)}</span>}
                </div>
                <video
                  controls
                  preload="metadata"
                  src={url}
                  className="w-full rounded border-2 border-ink/30 bg-black"
                  style={{ maxHeight: '360px' }}
                />
                <div className="flex justify-end mt-2">
                  <a
                    href={url}
                    download={f.name}
                    className="text-xs font-heading font-bold hover:text-info"
                  >
                    ⬇ Download {f.name}
                  </a>
                </div>
              </div>
            );
          })}
        </div>
      </Card>
    </div>
  );
}
