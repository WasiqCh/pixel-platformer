import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

export default function S12_Export({ currentProject }) {
  const [pkg, setPkg] = useState(null);
  const [building, setBuilding] = useState(false);
  const [exporting, setExporting] = useState(false);

  const exportEditor = async () => {
    setExporting(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/export/editor`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) alert('Editor export failed:\n\n' + (data.detail || 'Unknown error'));
      else alert(`EDITOR TIMELINE EXPORTED\n\n${data.clips} clips · ${data.stickers} stickers · ${data.total_sec}s\nmissing assets: ${data.missing}\nvoiceover WAVs: 08_export/voiceover/\n\nFiles:\n${data.files.join('\n')}`);
    } catch (e) { alert('Network error: ' + e.message); }
    setExporting(false);
  };

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/handoff`)
        .then(r => r.json()).then(d => setPkg(d.package || null)).catch(() => {});
  };
  useEffect(refresh, [currentProject]);

  const build = async () => {
    setBuilding(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/handoff/build`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) alert('Build failed:\n\n' + (data.detail || 'Unknown error'));
      else { setPkg(data); alert('Episode package built! Files written to 09_handoff/.'); }
    } catch (e) { alert('Network error: ' + e.message); }
    setBuilding(false);
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
      </div>
    );
  }

  const pct = pkg && pkg.assets_total ? Math.round((pkg.assets_ready / pkg.assets_total) * 100) : 0;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="flex justify-between items-center flex-wrap gap-2">
        <h2 className="font-display text-2xl text-ink">Export / Handoff</h2>
        <div className="flex gap-2 flex-wrap">
          <BlockButton variant="secondary" onClick={exportEditor} disabled={exporting}>
            {exporting ? 'Exporting...' : '🎞️ Export Editor Timeline'}
          </BlockButton>
          <BlockButton onClick={build} disabled={building}>
            {building ? 'Packing...' : '📦 Build Episode Package'}
          </BlockButton>
        </div>
      </div>

      {!pkg ? (
        <Card title="No Package Yet">
          <p className="font-body text-sm text-ink/70">
            Build the episode package: script + style kit + beats with shot kits + cast + locations +
            world assets, written to <code className="bg-panel px-1 rounded">09_handoff/</code> as JSON + Markdown.
          </p>
        </Card>
      ) : (
        <>
          <Card title={`Package — ${pkg.project}`}>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
              <div className="p-2 border-2 border-ink/20 rounded text-center">
                <p className="font-display text-xl">{pkg.beats}</p><p className="text-xs font-heading">BEATS</p>
              </div>
              <div className="p-2 border-2 border-ink/20 rounded text-center">
                <p className="font-display text-xl">{(pkg.duration_sec / 60).toFixed(1)}</p><p className="text-xs font-heading">MINUTES</p>
              </div>
              <div className="p-2 border-2 border-ink/20 rounded text-center">
                <p className="font-display text-xl">{pkg.cast}</p><p className="text-xs font-heading">CAST</p>
              </div>
              <div className="p-2 border-2 border-ink/20 rounded text-center">
                <p className="font-display text-xl">{pkg.environments}</p><p className="text-xs font-heading">LOCATIONS</p>
              </div>
              <div className="p-2 border-2 border-ink/20 rounded text-center">
                <p className="font-display text-xl">{pkg.world}</p><p className="text-xs font-heading">WORLD</p>
              </div>
            </div>

            <div className="p-3 border-2 border-ink rounded-md bg-panel mb-3">
              <div className="flex justify-between text-xs font-heading font-bold mb-1">
                <span>ASSET READINESS</span>
                <span>{pkg.assets_ready} / {pkg.assets_total} ({pct}%)</span>
              </div>
              <div className="h-4 border-2 border-ink rounded overflow-hidden bg-white">
                <div className={`h-full transition-all ${pct === 100 ? 'bg-success' : 'bg-warn'}`} style={{ width: `${pct}%` }} />
              </div>
            </div>

            {pkg.missing.length > 0 ? (
              <div className="p-3 border-2 border-warn rounded-md bg-warn/10">
                <p className="text-xs font-heading font-bold mb-2">STILL MISSING ({pkg.missing.length}) — fill these in 📚 Library:</p>
                <div className="flex flex-wrap gap-2">
                  {pkg.missing.map(m => (
                    <span key={m.asset_ref} className="text-xs font-body bg-white border border-ink/30 px-2 py-1 rounded">
                      {m.asset_ref} · {m.title}
                    </span>
                  ))}
                </div>
              </div>
            ) : (
              <div className="p-3 border-2 border-success rounded-md bg-success/10 font-body text-sm font-bold text-success">
                ✅ ALL ASSETS READY — this episode is fully packable!
              </div>
            )}

            <p className="text-xs font-body text-ink/60 mt-3">
              Built {new Date(pkg.built_at).toLocaleString()} · files: {pkg.files.join(' + ')}
            </p>
          </Card>
        </>
      )}
    </div>
  );
}
