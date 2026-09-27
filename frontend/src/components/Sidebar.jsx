import { playSfx } from '../lib/sfx';

// D5+D10-T01 — sidebar regroup: nav runs top-to-bottom in the real pipeline
// order (Script → Cast/Locations/World → Beats → Assets → Library →
// Checkpoint → My Video). Variants/Sheets/Export sit under a
// "classic (external art)" divider. Ids + labels unchanged (no renamed
// routes, no deletions) — only order, hints, divider, and the new
// 'myvideo' node. Full My Video output lands in D5+D10-T03.
const nodes = [
  { id: 'home', label: 'Home', icon: '🏠', hint: 'Start — pick channel + project' },
  { id: 'idea', label: 'Idea', icon: '💡', hint: 'Shape the idea' },
  { id: 'title', label: 'Title', icon: '🏷️', hint: 'Titles to try' },
  { id: 'script', label: 'Script', icon: '📝', hint: 'Write + lock script, feeds everything' },
  { id: 'cast', label: 'Cast Board', icon: '🎭', hint: 'who exists, feeds scenes' },
  { id: 'locations', label: 'Locations', icon: '🏞️', hint: 'where it happens, feeds scenes' },
  { id: 'world', label: 'World Desk', icon: '🌍', hint: 'real photos + maps, feeds scenes' },
  { id: 'beats', label: 'Beats', icon: '🎬', hint: 'scenes beat by beat, approve here' },
  { id: 'assets', label: 'Assets', icon: '🖼️', hint: 'every asset, fix + approve' },
  { id: 'library', label: 'Library', icon: '📚', hint: 'approved art, reuse store' },
  { id: 'checkpoint', label: 'Checkpoint', icon: '✅', hint: 'gates before render' },
  { id: 'myvideo', label: 'My Video', icon: '🎞️', hint: 'finished MP4s — watch + download' },
  { id: 'handoff', label: 'Handoff', icon: '🚀', hint: 'sign off + hand over package' },
  { id: 'stats', label: 'Stats', icon: '📈', hint: 'counts at a glance' },
  { id: 'prompts', label: 'Prompts & runs', icon: '🧾', hint: 'prompt library + run log' },
  { id: 'variants', label: 'Variants', icon: '👗', hint: 'classic — external art only', classic: true },
  { id: 'sheets', label: 'Sheets', icon: '🎨', hint: 'external art only', classic: true },
  { id: 'export', label: 'Export', icon: '📦', hint: 'classic — external art only', classic: true },
];

function NodeButton({ node, isActive, staleCount, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center justify-between p-2 rounded border-2 transition-all text-left ${
        isActive
          ? 'bg-sky/30 border-ink shadow-block'
          : 'border-transparent hover:bg-sky/10'
      }`}
    >
      <span className="flex items-start gap-2 min-w-0">
        <span className="mt-0.5">{node.icon}</span>
        <span className="min-w-0">
          <span className="block leading-tight">{node.label}</span>
          <span className="block text-xs font-body text-ink/60 leading-tight">{node.hint}</span>
        </span>
      </span>
      {staleCount > 0 && (
        <span className="bg-warn text-ink text-xs font-bold px-2 py-0.5 rounded-full border border-ink ml-2 shrink-0">
          {staleCount}
        </span>
      )}
    </button>
  );
}

export default function Sidebar({ activeNode, onNodeClick, staleCounts = {} }) {
  const handleNodeClick = (id) => {
    playSfx(id === activeNode ? 'click' : 'pop');
    onNodeClick(id);
  };

  const mainNodes = nodes.filter((n) => !n.classic);
  const classicNodes = nodes.filter((n) => n.classic);

  return (
    <aside className="w-64 bg-panel border-r-4 border-ink p-4 flex flex-col gap-1 overflow-y-auto">
      <h1 className="font-display text-sm text-primary mb-6 tracking-tight leading-tight">
        PIXEL<br />PLATFORMER
      </h1>
      <nav className="flex flex-col gap-1 font-heading text-base">
        {mainNodes.map((node) => (
          <NodeButton
            key={node.id}
            node={node}
            isActive={activeNode === node.id}
            staleCount={staleCounts[node.id] || 0}
            onClick={() => handleNodeClick(node.id)}
          />
        ))}
        <p className="mt-3 mb-1 px-2 text-xs font-heading font-bold uppercase tracking-wide text-ink/50">
          classic (external art)
        </p>
        {classicNodes.map((node) => (
          <NodeButton
            key={node.id}
            node={node}
            isActive={activeNode === node.id}
            staleCount={staleCounts[node.id] || 0}
            onClick={() => handleNodeClick(node.id)}
          />
        ))}
      </nav>

      <div className="mt-auto pt-6 border-t-2 border-ink/20 flex flex-col gap-1">
        <button
          onClick={() => handleNodeClick('changes')}
          className="w-full flex items-start gap-2 p-2 font-heading text-base rounded hover:bg-warn/20 border-2 border-transparent text-left"
        >
          <span className="mt-0.5">📥</span>
          <span>
            <span className="block leading-tight">Changes</span>
            <span className="block text-xs font-body text-ink/60 leading-tight">review incoming changes</span>
          </span>
        </button>
        <button
          onClick={() => handleNodeClick('settings')}
          className="w-full flex items-start gap-2 p-2 font-heading text-base rounded hover:bg-sky/20 border-2 border-transparent text-left"
        >
          <span className="mt-0.5">⚙️</span>
          <span>
            <span className="block leading-tight">Settings</span>
            <span className="block text-xs font-body text-ink/60 leading-tight">keys, voices, preferences</span>
          </span>
        </button>
      </div>
    </aside>
  );
}
