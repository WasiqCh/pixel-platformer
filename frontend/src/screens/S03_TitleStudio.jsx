import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import StatusDot from '../components/StatusDot';

export default function S03_TitleStudio({ currentProject }) {
  const [titles, setTitles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [ownTitle, setOwnTitle] = useState('');

  const fetchTitles = () => {
    if (currentProject) {
      fetch(`/api/v1/projects/${currentProject.id}/titles`)
        .then(r => r.json())
        .then(setTitles);
    }
  };

  useEffect(() => { fetchTitles(); }, [currentProject]);

  const generate = async () => {
    setLoading(true);
    await fetch(`/api/v1/projects/${currentProject.id}/titles/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ count: 10 })
    });
    fetchTitles();
    setLoading(false);
  };

  const lock = async (id) => {
    await fetch(`/api/v1/titles/${id}/lock?project_id=${currentProject.id}`, { method: 'POST' });
    fetchTitles();
  };

  if (!currentProject) return <div className="card text-center">Select a project first.</div>;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h2 className="font-display text-2xl text-ink">Title Studio</h2>

      <Card title="Generate Candidates" actions={
        <BlockButton onClick={generate} disabled={loading}>
          {loading ? 'Brainstorming...' : 'Generate 10 Titles'}
        </BlockButton>
      }>
        <p className="text-sm text-ink/70 mb-4">Based on your Idea Card, the AI will propose 10 distinct angles.</p>
        
        <div className="flex gap-2 pt-4 border-t-2 border-ink/10">
          <input 
            type="text" 
            name="own_title"
            placeholder="Or type your own title..." 
            value={ownTitle}
            onChange={e => setOwnTitle(e.target.value)}
            className="flex-1 bg-white border-2 border-ink rounded px-3 py-2 font-body"
          />
          <BlockButton variant="secondary">Save Own Title</BlockButton>
        </div>
      </Card>

      {titles.length > 0 && (
        <Card title="Candidates">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {titles.map(t => (
              <div key={t.id} className={`p-4 border-2 rounded-md transition-all ${t.locked ? 'border-success bg-success/10 shadow-block' : 'border-ink bg-panel hover:shadow-hover hover:-translate-x-[2px] hover:-translate-y-[2px]'}`}>
                <div className="flex justify-between items-start mb-2">
                  <span className="text-xs font-bold uppercase text-info">{t.style_tag}</span>
                  <span className={`text-xs font-mono ${t.char_count > 70 ? 'text-danger' : 'text-ink/60'}`}>{t.char_count} chars</span>
                </div>
                <h3 className="font-heading text-lg font-bold mb-2 leading-tight">{t.text}</h3>
                <p className="text-sm text-ink/70 mb-4 italic">"{t.angle}"</p>
                
                <div className="flex justify-end">
                  {t.locked ? (
                    <span className="flex items-center gap-2 text-success font-bold text-sm">
                      <StatusDot status="approved" /> LOCKED
                    </span>
                  ) : (
                    <BlockButton variant="primary" onClick={() => lock(t.id)}>Lock Title</BlockButton>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}