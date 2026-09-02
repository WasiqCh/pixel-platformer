import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 500) || `HTTP ${res.status} (Empty response)` }; }
};

export default function S06_VariantTimelines({ currentProject }) {
  const [variants, setVariants] = useState([]);
  const [loading, setLoading] = useState(false);

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/variants`)
        .then(r => r.json())
        .then(setVariants);
  };
  useEffect(refresh, [currentProject]);

  const extract = async () => {
    setLoading(true);
    const res = await fetch(`/api/v1/projects/${currentProject.id}/variants/extract`, { method: 'POST' });
    const data = await safeJson(res);
    if (!res.ok) {
      alert('Extract failed:\n\n' + (data.detail || 'Unknown error'));
    } else {
      alert(`Success! Added: ${data.added}`);
    }
    refresh();
    setLoading(false);
  };

  const deleteVariant = async (varId) => {
    if (!confirm('Delete this variant?')) return;
    await fetch(`/api/v1/projects/${currentProject.id}/variants/${varId}`, { method: 'DELETE' });
    refresh();
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
      </div>
    );
  }

  // Group variants by character
  const grouped = {};
  for (const v of variants) {
    if (!grouped[v.character_id]) {
      grouped[v.character_id] = { name: v.char_names[0], variants: [] };
    }
    grouped[v.character_id].variants.push(v);
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="font-display text-2xl text-ink">Variant Timelines (P10)</h2>
        <BlockButton onClick={extract} disabled={loading}>
          {loading ? 'Extracting...' : '🧠 Re-Extract Variants'}
        </BlockButton>
      </div>

      {Object.keys(grouped).length === 0 ? (
        <Card title="No Variants Yet">
          <p className="font-body text-sm text-ink/70">Click "Re-Extract Variants" to find costume/age changes for your cast.</p>
        </Card>
      ) : (
        Object.entries(grouped).map(([charId, data]) => (
          <Card key={charId} title={`${data.name} (${charId})`}>
            <div className="relative border-l-4 border-primary/30 ml-3 pl-6 space-y-6">
              {data.variants.map((v, idx) => (
                <div key={v.id} className="relative">
                  <div className={`absolute -left-[34px] top-1 w-6 h-6 rounded-full border-2 border-ink flex items-center justify-center bg-panel text-xs font-bold ${v.stale ? 'border-warn text-warn' : 'border-primary text-primary'}`}>
                    {idx + 1}
                  </div>
                  <div className={`p-4 border-2 rounded-md ${v.stale ? 'border-warn bg-warn/10' : 'border-ink bg-white'} shadow-sm`}>
                    <div className="flex justify-between items-start mb-2">
                      <div>
                        <h4 className="font-heading text-lg font-bold text-ink">{v.delta}</h4>
                        <p className="text-xs font-mono text-info">{v.id} · conf: {Math.round(v.confidence * 100)}%</p>
                      </div>
                      <div className="flex gap-2 items-center">
                        {v.stale === 1 && <span className="text-xs font-bold text-warn border border-warn px-2 py-1 rounded">ONE-OFF</span>}
                        <button onClick={() => deleteVariant(v.id)} className="text-xs font-bold text-danger hover:underline">🗑 Delete</button>
                      </div>
                    </div>
                    <div className="text-xs font-body text-ink/60 mb-2 italic bg-sky/20 p-2 rounded">
                      📍 {v.span}
                    </div>
                    <p className="font-body text-sm text-ink/90 italic">"{v.evidence}"</p>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        ))
      )}
    </div>
  );
}
