import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

// Fixes AI encoding artifacts (â€¢ -> •, etc.)
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
      <div className="flex justify-between items-center">
        <h2 className="font-display text-2xl text-ink">Beat Board (P13)</h2>
        <BlockButton onClick={extract} disabled={loading}>
          {loading ? 'Breaking down...' : '🎬 Re-Extract Beats'}
        </BlockButton>
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
                        <span className="italic text-ink/70">→ {clean(b.svo)}</span>
                        {b.text_only === 1 && (
                          <span className="font-bold bg-panel border-2 border-ink px-2 py-0.5 rounded">TEXT-ONLY</span>
                        )}
                        {b.overlay_text && (
                          <span className="font-bold bg-warn/20 border border-warn px-2 py-0.5 rounded">🏷 {clean(b.overlay_text)}</span>
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
                    <button onClick={() => remove(b.id)} className="text-xs font-heading font-bold text-danger hover:underline">🗑</button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        );
      })}
    </div>
  );
}
