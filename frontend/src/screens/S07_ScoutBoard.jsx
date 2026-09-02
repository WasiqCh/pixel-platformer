import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

export default function S07_ScoutBoard({ currentProject }) {
  const [envs, setEnvs] = useState([]);
  const [loading, setLoading] = useState(false);

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/environments`)
        .then(r => r.json()).then(setEnvs).catch(() => {});
  };
  useEffect(refresh, [currentProject]);

  const extract = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/environments/extract`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) alert('Extract failed:\n\n' + (data.detail || 'Unknown error'));
      else { alert(`Success! Added: ${data.added}, Updated: ${data.updated}`); refresh(); }
    } catch (e) { alert('Network error: ' + e.message); }
    setLoading(false);
  };

  const remove = async (envId) => {
    if (!confirm('Delete this location?')) return;
    await fetch(`/api/v1/projects/${currentProject.id}/environments/${envId}`, { method: 'DELETE' });
    refresh();
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
        <p className="font-body">Go to Home and select a project first.</p>
      </div>
    );
  }

  const greenCount = envs.filter(e => e.green_conflict === 1).length;

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="font-display text-2xl text-ink">Scout Board (P11)</h2>
        <BlockButton onClick={extract} disabled={loading}>
          {loading ? 'Scouting...' : '🗺️ Re-Extract Locations'}
        </BlockButton>
      </div>

      {greenCount > 0 && (
        <div className="p-3 border-2 border-success rounded-md bg-success/10 font-body text-sm">
          🟢 <b>{greenCount} location{greenCount > 1 ? 's' : ''}</b> flagged <b>green_conflict</b> — foliage-heavy.
          Plan non-chroma palettes or painted skies for these scenes.
        </div>
      )}

      {envs.length === 0 ? (
        <Card title="No Locations Yet">
          <p className="font-body text-sm text-ink/70">Click "Re-Extract Locations" to scout every place in the script.</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {envs.map(e => (
            <div key={e.id} className={`p-4 border-2 rounded-md bg-panel shadow-block ${e.green_conflict === 1 ? 'border-success' : 'border-ink'}`}>
              <div className="flex justify-between items-start mb-2">
                <div>
                  <h3 className="font-heading text-lg font-bold">{e.name}</h3>
                  <p className="text-xs font-mono text-ink/50">{e.id}</p>
                </div>
                {e.green_conflict === 1 && (
                  <span className="text-xs font-bold bg-success/20 border border-success text-success px-2 py-1 rounded">🟢 GREEN</span>
                )}
              </div>

              <ul className="font-body text-sm text-ink/80 space-y-1 mb-3 list-disc list-inside">
                {e.elements.map((el, i) => <li key={i}>{el}</li>)}
              </ul>

              {e.variations && e.variations.length > 0 && (
                <div className="mb-3">
                  <p className="text-xs font-bold text-ink/60 mb-1 font-heading">VARIATIONS:</p>
                  <div className="flex flex-wrap gap-1">
                    {e.variations.map((v, i) => (
                      <span key={i} className="text-xs bg-info/20 border border-info px-2 py-0.5 rounded font-bold">{v}</span>
                    ))}
                  </div>
                </div>
              )}

              <div className="text-xs font-body text-ink/60 mb-3">
                📍 {(e.presence || []).map(p => p.replace('## ', '')).join(' · ') || '—'}
              </div>

              <div className="flex justify-end pt-2 border-t border-ink/10">
                <button onClick={() => remove(e.id)} className="text-xs font-heading font-bold text-danger hover:underline">🗑 Delete</button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
