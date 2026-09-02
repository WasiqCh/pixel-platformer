import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

export default function S13_Checkpoint({ currentProject }) {
  const [data, setData] = useState(null);
  const [advancing, setAdvancing] = useState(false);

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/checkpoint`)
        .then(r => r.json()).then(setData).catch(() => {});
  };
  useEffect(refresh, [currentProject]);

  const advance = async () => {
    setAdvancing(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/checkpoint/advance`, { method: 'POST' });
      const d = await safeJson(res);
      if (!res.ok) alert('Cannot advance:\n\n' + (d.detail || 'Unknown error'));
      else { alert('Stage advanced: ready_for_handoff ✅'); refresh(); }
    } catch (e) { alert('Network error: ' + e.message); }
    setAdvancing(false);
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
      </div>
    );
  }

  const icon = (c) => (c.ok ? '✅' : c.required ? '❌' : '⚠️');

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="font-display text-2xl text-ink">Checkpoint (Definition of Done)</h2>
        <span className="text-xs font-heading font-bold bg-panel border-2 border-ink px-3 py-1 rounded">
          STAGE: {(data?.stage || '').toUpperCase()}
        </span>
      </div>

      {!data ? (
        <Card title="Loading..."><p className="font-body text-sm">Reading project state…</p></Card>
      ) : (
        <Card title={`Required gates: ${data.required_pass} / ${data.required_total} passed`}>
          <div className="space-y-2">
            {data.checks.map(c => (
              <div key={c.id} className={`p-3 border-2 rounded-md flex items-center gap-3 ${
                c.ok ? 'border-success/40 bg-success/5' : c.required ? 'border-danger bg-danger/10' : 'border-warn bg-warn/10'}`}>
                <span className="text-lg">{icon(c)}</span>
                <div className="flex-1">
                  <p className="font-heading text-sm font-bold">
                    {c.label} {!c.required && <span className="text-xs text-ink/50">(recommended)</span>}
                  </p>
                  <p className="text-xs font-body text-ink/70">{c.detail}</p>
                </div>
              </div>
            ))}
          </div>

          <div className="flex justify-end mt-4">
            <BlockButton onClick={advance} disabled={!data.can_advance || advancing}>
              {advancing ? 'Advancing...' : '🚦 Advance Stage'}
            </BlockButton>
          </div>
          {!data.can_advance && (
            <p className="text-xs font-body text-ink/60 mt-2 text-right">
              Fix the ❌ gates in their screens, then come back. ⚠️ items never block shipping.
            </p>
          )}
        </Card>
      )}
    </div>
  );
}
