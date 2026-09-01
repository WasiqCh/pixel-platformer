export default function TopBar({ channel, project, jobQueue }) {
  return (
    <header className="h-16 bg-panel border-b-4 border-ink px-6 flex items-center justify-between shrink-0">
      <div className="flex items-center gap-4 font-heading text-lg">
        <div className="flex items-center gap-2 bg-sky/20 px-3 py-1 rounded border-2 border-ink">
          <span>📺</span>
          <span>{channel || 'Select Channel'}</span>
        </div>
        <span className="text-ink/40">/</span>
        <div className="flex items-center gap-2 bg-sky/20 px-3 py-1 rounded border-2 border-ink">
          <span>🎬</span>
          <span>{project || 'Select Project'}</span>
        </div>
      </div>
      
      <div className="flex items-center gap-4">
        {jobQueue > 0 && (
          <div className="flex items-center gap-2 bg-warn/30 px-3 py-1 rounded border-2 border-ink font-heading text-sm animate-pulse">
            ⏳ {jobQueue} in queue
          </div>
        )}
        <div className="w-8 h-8 bg-brick rounded-full border-2 border-ink flex items-center justify-center text-white font-heading text-sm">
          W
        </div>
      </div>
    </header>
  );
}