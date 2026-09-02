import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import StatusDot from '../components/StatusDot';

export default function S02_IdeaStudio({ currentProject, currentChannel, onNavigate }) {
  const [input, setInput] = useState('');
  const [ideas, setIdeas] = useState([]);
  const [loading, setLoading] = useState(false);
  const [surprises, setSurprises] = useState([]);
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState(null);

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/ideas`).then(r => r.json()).then(setIdeas);
  };
  useEffect(refresh, [currentProject]);

  const generate = async () => {
    if (!input.trim()) return;
    setLoading(true);
    const res = await fetch(`/api/v1/projects/${currentProject.id}/ideas/generate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input })
    });
    const data = await res.json();
    if (data.content) { setInput(''); refresh(); }
    else alert('Failed: ' + (data.detail || 'Unknown error'));
    setLoading(false);
  };

  const surprise = async () => {
    setLoading(true);
    const res = await fetch(`/api/v1/channels/${currentChannel.id}/ideas/surprise`, { method: 'POST' });
    const data = await res.json();
    if (data.ideas) setSurprises(data.ideas);
    setLoading(false);
  };

  const promoteSurprise = async (conceptText) => {
    setLoading(true);
    // We send the raw concept through the generator to flesh out the hooks/appeal
    const res = await fetch(`/api/v1/projects/${currentProject.id}/ideas/generate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: conceptText })
    });
    if (res.ok) {
      refresh(); // Reloads the Active ideas list below
      setSurprises([]); // Clears the 6 concepts since we promoted one
    } else {
      alert('Promote failed: ' + ((await res.json()).detail || 'Unknown error'));
    }
    setLoading(false);
  };

  const lock = async (id) => {
    await fetch(`/api/v1/projects/${currentProject.id}/ideas/${id}/lock`, { method: 'POST' });
    refresh();
  };

  const toggleShelf = async (id) => {
    await fetch(`/api/v1/projects/${currentProject.id}/ideas/${id}/shelf`, { method: 'POST' });
    refresh();
  };

  const refine = async (id) => {
    const note = prompt('Refine instruction (e.g. "make it darker", "focus on the betrayal"):');
    if (!note) return;
    setLoading(true);
    const res = await fetch(`/api/v1/projects/${currentProject.id}/ideas/${id}/refine`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction: note })
    });
    const data = await res.json();
    if (!res.ok) alert('Refine failed: ' + (data.detail || 'Unknown error'));
    refresh();
    setLoading(false);
  };

  const startEdit = (idea) => {
    setEditingId(idea.id);
    setEditDraft({
      concept: idea.content.concept,
      appeal: idea.content.appeal,
      hooks: idea.content.hooks.join('\n'),
      tags: idea.content.tags.join(', '),
      scale_estimate: idea.content.scale_estimate,
      rw_watchout: idea.content.rw_watchout,
    });
  };

  const saveEdit = async (id) => {
    const content = {
      concept: editDraft.concept,
      appeal: editDraft.appeal,
      hooks: editDraft.hooks.split('\n').map(s => s.trim()).filter(Boolean),
      tags: editDraft.tags.split(',').map(s => s.trim()).filter(Boolean),
      scale_estimate: editDraft.scale_estimate,
      rw_watchout: editDraft.rw_watchout,
    };
    await fetch(`/api/v1/projects/${currentProject.id}/ideas/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content })
    });
    setEditingId(null);
    refresh();
  };

  const activeIdeas = ideas.filter(i => !i.shelf_flag);
  const shelvedIdeas = ideas.filter(i => i.shelf_flag);

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
        <p className="font-body">Go to Home and select a project to start brainstorming.</p>
      </div>
    );
  }

  const renderIdeaCard = (idea) => (
    <div key={idea.id} className={`p-4 border-2 rounded-md ${idea.is_current ? 'border-success bg-success/10 shadow-block' : 'border-ink bg-panel'}`}>
      {editingId === idea.id ? (
        <div className="space-y-3">
          <textarea name="edit_concept" value={editDraft.concept}
            onChange={e => setEditDraft({ ...editDraft, concept: e.target.value })}
            className="w-full bg-white border-2 border-ink rounded p-2 font-body text-sm" rows={3} />
          <textarea name="edit_appeal" value={editDraft.appeal}
            onChange={e => setEditDraft({ ...editDraft, appeal: e.target.value })}
            className="w-full bg-white border-2 border-ink rounded p-2 font-body text-sm" rows={2} placeholder="appeal" />
          <textarea name="edit_hooks" value={editDraft.hooks}
            onChange={e => setEditDraft({ ...editDraft, hooks: e.target.value })}
            className="w-full bg-white border-2 border-ink rounded p-2 font-body text-sm" rows={3} placeholder="one hook per line" />
          <input name="edit_tags" value={editDraft.tags}
            onChange={e => setEditDraft({ ...editDraft, tags: e.target.value })}
            className="w-full bg-white border-2 border-ink rounded p-2 font-body text-sm" placeholder="tags, comma, separated" />
          <div className="flex gap-2 justify-end">
            <BlockButton variant="secondary" onClick={() => setEditingId(null)}>Cancel</BlockButton>
            <BlockButton onClick={() => saveEdit(idea.id)}>Save Edit</BlockButton>
          </div>
        </div>
      ) : (
        <>
          <div className="flex justify-between items-start mb-2">
            <h3 className="font-heading text-lg font-bold">{idea.content.concept}</h3>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-ink/50">v{idea.version}</span>
              {idea.is_current
                ? <span className="flex items-center gap-1 text-success font-bold text-sm"><StatusDot status="approved" /> LOCKED</span>
                : <StatusDot status="default" />}
            </div>
          </div>
          <p className="font-body text-sm text-ink/80 mb-3">{idea.content.appeal}</p>
          <div className="flex flex-wrap gap-2 mb-3">
            {idea.content.hooks.map((h, i) => (
              <span key={i} className="text-xs bg-info/20 border border-info px-2 py-1 rounded font-bold">{h}</span>
            ))}
          </div>
          <div className="flex items-center justify-between">
            <div className="flex gap-4 text-xs text-ink/60">
              <span>Tags: {idea.content.tags.join(', ')}</span>
              <span>Scale: {idea.content.scale_estimate.characters}C / {idea.content.scale_estimate.environments}E</span>
              {idea.content.rw_watchout && <span className="text-danger font-bold">⚠ RW</span>}
            </div>
            <div className="flex gap-2">
              <button onClick={() => toggleShelf(idea.id)} className="text-xs font-heading hover:text-warn" title={idea.shelf_flag ? "Unshelf" : "Shelf"}>
                {idea.shelf_flag ? '📤 Unshelf' : '📥 Shelf'}
              </button>
              <BlockButton variant="secondary" onClick={() => startEdit(idea)}>✏️</BlockButton>
              <BlockButton variant="secondary" onClick={() => refine(idea.id)} disabled={loading}>🤖</BlockButton>
              {!idea.is_current && <BlockButton onClick={() => lock(idea.id)}>🔒</BlockButton>}
            </div>
          </div>
        </>
      )}
    </div>
  );

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h2 className="font-display text-2xl text-ink">Idea Studio</h2>

      <Card title="Brainstorm">
        <textarea name="idea_input" value={input} onChange={e => setInput(e.target.value)}
          placeholder="Type a raw idea, a topic, or just one word..."
          className="w-full h-32 bg-white border-2 border-ink rounded-md p-3 font-body text-lg mb-4 focus:outline-none focus:border-info resize-none" />
        <div className="flex gap-3">
          <BlockButton onClick={generate} disabled={loading || !input.trim()}>
            {loading ? 'Thinking...' : 'Refine & Expand'}
          </BlockButton>
          <BlockButton variant="secondary" onClick={surprise} disabled={loading}>
            🎲 Surprise Me (6 concepts)
          </BlockButton>
        </div>
      </Card>

      {surprises.length > 0 && (
        <Card title="Surprise Concepts" actions={<button onClick={() => setSurprises([])} className="text-sm text-ink/60 hover:text-danger font-heading">Clear</button>}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {surprises.map((s, i) => (
              <div key={i} className="p-3 border-2 border-ink/30 rounded bg-sky/10 flex flex-col justify-between">
                <div>
                  <p className="font-body font-bold mb-2">{s.concept}</p>
                  <div className="flex flex-wrap gap-1 mb-2">
                    {s.tags.map(t => <span key={t} className="text-xs bg-panel border border-ink px-2 py-0.5 rounded">{t}</span>)}
                  </div>
                  <p className="text-xs text-ink/60 mb-2">Scale: {s.scale_estimate.characters}C / {s.scale_estimate.environments}E</p>
                  {s.rw_watchout && <p className="text-xs text-danger font-bold">⚠ Needs real-world assets</p>}
                </div>
                <div className="flex justify-end mt-3 pt-2 border-t border-ink/10">
                  <BlockButton onClick={() => promoteSurprise(s.concept)} disabled={loading}>
                    🚀 Promote to Idea
                  </BlockButton>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {activeIdeas.length > 0 && (
        <Card title="Active & History">
          <div className="space-y-4">{activeIdeas.map(renderIdeaCard)}</div>
        </Card>
      )}

      {shelvedIdeas.length > 0 && (
        <Card title="The Shelf (Saved for later)">
          <div className="space-y-4 opacity-80">{shelvedIdeas.map(renderIdeaCard)}</div>
        </Card>
      )}

      <Card title="Fast Lane / Skip Doors">
        <p className="font-body text-sm text-ink/70 mb-4">Already have what you need? Jump to the next stage.</p>
        <div className="flex gap-4">
          <BlockButton variant="secondary" onClick={() => onNavigate('title')}>Skip to Titles →</BlockButton>
          <BlockButton variant="secondary" onClick={() => onNavigate('script')}>Skip to Script →</BlockButton>
        </div>
      </Card>
    </div>
  );
}
