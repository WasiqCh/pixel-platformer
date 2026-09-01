import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import StatusDot from '../components/StatusDot';

export default function S02_IdeaStudio({ currentProject, currentChannel }) {
  const [input, setInput] = useState('');
  const [ideas, setIdeas] = useState([]);
  const [loading, setLoading] = useState(false);
  const [surprises, setSurprises] = useState([]);

  useEffect(() => {
    if (currentProject) {
      fetch(`/api/v1/projects/${currentProject.id}/ideas`)
        .then(r => r.json())
        .then(setIdeas);
    }
  }, [currentProject]);

  const generate = async () => {
    if (!input.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/ideas/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input })
      });
      const data = await res.json();
      if (data.content) {
        setIdeas([{ id: data.id, content: data.content }, ...ideas]);
        setInput(''); // Clear input on success
      } else {
        alert("Failed to generate idea: " + (data.detail || "Unknown error"));
      }
    } catch (e) {
      alert("Network error");
    }
    setLoading(false);
  };

  const surprise = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/channels/${currentChannel.id}/ideas/surprise`, { method: 'POST' });
      const data = await res.json();
      if (data.ideas) setSurprises(data.ideas);
    } catch (e) {
      alert("Network error");
    }
    setLoading(false);
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
        <p className="font-body">Go to Home and select a project to start brainstorming.</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h2 className="font-display text-2xl text-ink">Idea Studio</h2>

      <Card title="Brainstorm">
        <textarea
          name="idea_input"
          value={input}
          onChange={e => setInput(e.target.value)}
          placeholder="Type a raw idea, a topic, or just one word..."
          className="w-full h-32 bg-white border-2 border-ink rounded-md p-3 font-body text-lg mb-4 focus:outline-none focus:border-info resize-none"
        />
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
              <div key={i} className="p-3 border-2 border-ink/30 rounded bg-sky/10 hover:bg-sky/20 transition-colors">
                <p className="font-body font-bold mb-2">{s.concept}</p>
                <div className="flex flex-wrap gap-1 mb-2">
                  {s.tags.map(t => <span key={t} className="text-xs bg-panel border border-ink px-2 py-0.5 rounded">{t}</span>)}
                </div>
                <p className="text-xs text-ink/60">Scale: {s.scale_estimate.characters} chars, {s.scale_estimate.environments} envs</p>
                {s.rw_watchout && <p className="text-xs text-danger font-bold mt-1">⚠ Needs real-world assets</p>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {ideas.length > 0 && (
        <Card title="Project Ideas">
          <div className="space-y-4">
            {ideas.map(idea => (
              <div key={idea.id} className="p-4 border-2 border-ink rounded-md bg-panel shadow-block">
                <div className="flex justify-between items-start mb-2">
                  <h3 className="font-heading text-lg font-bold">{idea.content.concept}</h3>
                  <StatusDot status="approved" />
                </div>
                <p className="font-body text-sm text-ink/80 mb-3">{idea.content.appeal}</p>
                <div className="flex flex-wrap gap-2 mb-3">
                  {idea.content.hooks.map((h, i) => (
                    <span key={i} className="text-xs bg-info/20 border border-info px-2 py-1 rounded font-bold">{h}</span>
                  ))}
                </div>
                <div className="flex gap-4 text-xs text-ink/60">
                  <span>Tags: {idea.content.tags.join(', ')}</span>
                  <span>Scale: {idea.content.scale_estimate.characters}C / {idea.content.scale_estimate.environments}E</span>
                  {idea.content.rw_watchout && <span className="text-danger font-bold">⚠ RW Watchout</span>}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}