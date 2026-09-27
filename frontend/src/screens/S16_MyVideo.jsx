import Card from '../components/Card';

// D5+D10-T01 — My Video node (placeholder). The sidebar regroup adds this
// entry so Dawood's road ends at finished MP4s. Full versioned finals list
// (watch + download, existing file-serving pattern) lands in D5+D10-T03.
// Frontend-only, no backend calls here.
export default function S16_MyVideo({ currentProject }) {
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
      <Card title="Finished MP4s live here">
        <p className="font-body text-sm text-ink/70">
          Project <span className="font-mono font-bold">{currentProject.slug || currentProject.id}</span> — the
          versioned finals list (click-to-play + Download per MP4) lands in D5+D10-T03.
        </p>
      </Card>
    </div>
  );
}
