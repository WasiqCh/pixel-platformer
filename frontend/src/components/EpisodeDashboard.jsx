import { useState, useEffect } from 'react';
import Card from './Card';
import BlockButton from './BlockButton';
import { playSfx } from '../lib/sfx';

// Answers "where is this episode and what do I do next" in one place, so you
// don't have to visit every stage to work it out.

function Metric({ label, value }) {
  return (
    <div className="bg-sky/20 rounded-md p-3">
      <p className="text-xs font-heading text-ink/60 mb-1">{label}</p>
      <p className="font-display text-2xl font-bold text-ink">{value}</p>
    </div>
  );
}

export default function EpisodeDashboard({ currentProject, onNavigate }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const load = () => {
    if (!currentProject?.id) { setData(null); return; }
    fetch(`/api/v1/projects/${currentProject.id}/dashboard`)
      .then(r => r.json()).then(d => setData(d && d.project_id ? d : null)).catch(() => setData(null));
  };

  useEffect(() => { load(); }, [currentProject?.id]);

  if (!currentProject || !data) return null;

  const reextract = async () => {
    setBusy(true); setMsg('');
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/stale/reextract`, { method: 'POST' });
      const d = await res.json();
      const failed = d.failed || [];
      setMsg(failed.length ? `Rebuilt, but ${failed.join(', ')} failed` : 'Rebuilt');
      playSfx(failed.length ? 'error' : 'success');
      load();
    } catch { setMsg('Network error'); playSfx('error'); }
    setBusy(false);
  };

  const next = data.next_action || {};
  const counts = data.counts || {};
  const lib = data.library || {};

  return (
    <Card title="Episode status">
      <div className="bg-panel rounded-md p-4 mb-4">
        <p className="text-xs font-heading text-ink/60 mb-1">Next action</p>
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div>
            <p className="font-heading text-lg font-bold text-ink">{next.label}</p>
            <p className="text-xs font-body text-ink/60">{next.why}</p>
          </div>
          {next.action === 'reextract' ? (
            <BlockButton onClick={reextract} disabled={busy}>
              {busy ? 'Rebuilding…' : 'Re-extract stale'}
            </BlockButton>
          ) : (
            <BlockButton onClick={() => { playSfx('pop'); onNavigate(next.screen); }}>
              Go →
            </BlockButton>
          )}
        </div>
        {msg && <p className="text-xs font-heading text-primary mt-2">{msg}</p>}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Metric label="Stale" value={data.stale?.total ?? 0} />
        <Metric label="Assets ready" value={`${lib.ready ?? 0}/${lib.total ?? 0}`} />
        <Metric label="Shot prompts" value={counts.generations ?? 0} />
        <Metric label="Script words" value={data.script?.words ?? 0} />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Metric label="Cast" value={counts.characters ?? 0} />
        <Metric label="Locations" value={counts.environments ?? 0} />
        <Metric label="Beats" value={counts.beats ?? 0} />
        <Metric label="World" value={counts.world_records ?? 0} />
      </div>

      <div>
        <p className="text-xs font-heading text-ink/60 mb-2">Blocking export</p>
        <div className="flex flex-col gap-1">
          {(data.blockers || []).map((b, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${b.done ? 'bg-success' : 'bg-ink/30'}`} />
              <span className={`text-sm font-body ${b.done ? 'text-ink/60' : 'text-ink'}`}>{b.label}</span>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}
