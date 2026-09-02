const nodes = [
  { id: 'home', label: 'Home', icon: '🏠' },
  { id: 'idea', label: 'Idea', icon: '💡' },
  { id: 'title', label: 'Title', icon: '🏷️' },
  { id: 'script', label: 'Script', icon: '📝' },
  { id: 'cast', label: 'Cast Board', icon: '🎭' },
  { id: 'variants', label: 'Variants', icon: '👗' },
  { id: 'locations', label: 'Locations', icon: '🏞️' },
  { id: 'world', label: 'World Desk', icon: '🌍' },
  { id: 'sheets', label: 'Sheets', icon: '🎨' },
  { id: 'export', label: 'Export', icon: '📦' },
  { id: 'check', label: 'Checkpoint', icon: '✅' },
  { id: 'library', label: 'Library', icon: '📚' },
  { id: 'beats', label: 'Beats', icon: '🎬' },
  { id: 'handoff', label: 'Handoff', icon: '🚀' },
  { id: 'stats', label: 'Stats', icon: '📈' },
];

export default function Sidebar({ activeNode, onNodeClick, staleCounts = {} }) {
  return (
    <aside className="w-64 bg-panel border-r-4 border-ink p-4 flex flex-col gap-1 overflow-y-auto">
      <h1 className="font-display text-sm text-primary mb-6 tracking-tight leading-tight">
        PIXEL<br/>PLATFORMER
      </h1>
      <nav className="flex flex-col gap-1 font-heading text-base">
        {nodes.map(node => {
          const isActive = activeNode === node.id;
          const staleCount = staleCounts[node.id] || 0;
          return (
            <button
              key={node.id}
              onClick={() => onNodeClick(node.id)}
              className={`flex items-center justify-between p-2 rounded border-2 transition-all text-left ${
                isActive 
                  ? 'bg-sky/30 border-ink shadow-block' 
                  : 'border-transparent hover:bg-sky/10'
              }`}
            >
              <span className="flex items-center gap-2">
                <span>{node.icon}</span>
                <span>{node.label}</span>
              </span>
              {staleCount > 0 && (
                <span className="bg-warn text-ink text-xs font-bold px-2 py-0.5 rounded-full border border-ink">
                  {staleCount}
                </span>
              )}
            </button>
          );
        })}
      </nav>
      
      <div className="mt-auto pt-6 border-t-2 border-ink/20 flex flex-col gap-1">
        <button 
          onClick={() => onNodeClick('changes')}
          className="w-full flex items-center gap-2 p-2 font-heading text-base rounded hover:bg-warn/20 border-2 border-transparent text-left"
        >
          📥 Changes
        </button>
        <button 
          onClick={() => onNodeClick('settings')}
          className="w-full flex items-center gap-2 p-2 font-heading text-base rounded hover:bg-sky/20 border-2 border-transparent text-left"
        >
          ⚙️ Settings
        </button>
      </div>
    </aside>
  );
}