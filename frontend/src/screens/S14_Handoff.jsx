import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

export default function S14_Handoff({ currentProject }) {
  const [status, setStatus] = useState(null);
  const [signing, setSigning] = useState(false);

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/handoff/status`)
        .then(r => r.json()).then(setStatus).catch(() => {});
  };
  useEffect(refresh, [currentProject]);

  const signoff = async () => {
    setSigning(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/handoff/signoff`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) alert('Sign-off blocked:\n\n' + (data.detail || 'Unknown error'));
      else { alert('🚀 Episode handed off! Stage: handed_off'); refresh(); }
    } catch (e) { alert('Network error: ' + e.message); }
    setSigning(false);
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
      </div>
    );
  }

  const stage = status?.stage || 'script';

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="font-display text-2xl text-ink">Handoff</h2>
        <span className={`text-xs font-heading font-bold px-3 py-1 rounded border-2 ${
          stage === 'handed_off' ? 'border-success text-success bg-success/10' : 'border-ink bg-panel'}`}>
          STAGE: {stage.toUpperCase()}
        </span>
      </div>

      {stage === 'handed_off' ? (
        <>
          <div className="p-4 border-2 border-success rounded-md bg-success/10 font-body">
            <p className="font-display text-xl text-success mb-1">🏁 EPISODE HANDED OFF</p>
            <p className="text-sm text-ink/80">
              The package is signed. Hand <code className="bg-panel px-1 rounded">09_handoff/episode_package.*</code> to
              the animator or render tool — everything it needs is inside.
            </p>
          </div>
          {status?.handoff_md && (
            <Card title="Signed HANDOFF.md">
              <div className="bg-white border-2 border-ink rounded-md p-4 font-body text-sm whitespace-pre-wrap max-h-[30rem] overflow-y-auto">
                {status.handoff_md}
              </div>
            </Card>
          )}
        </>
      ) : (
        <Card title="Final sign-off">
          <p className="font-body text-sm text-ink/70 mb-4">
            {stage === 'ready_for_handoff'
              ? 'Checkpoint passed. Sign off to write HANDOFF.md and flip the stage to handed_off.'
              : `Current stage: ${stage}. Pass the ✅ Checkpoint and press 🚦 Advance Stage to unlock sign-off.`}
          </p>
          <div className="flex justify-end">
            <BlockButton onClick={signoff} disabled={signing || stage !== 'ready_for_handoff'}>
              {signing ? 'Signing...' : '🚀 Sign Off & Handoff'}
            </BlockButton>
          </div>
        </Card>
      )}
    </div>
  );
}
