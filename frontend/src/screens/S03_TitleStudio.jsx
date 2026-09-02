import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import StatusDot from '../components/StatusDot';

export default function S03_TitleStudio({ currentProject }) {
  const [titles, setTitles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [ownTitle, setOwnTitle] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState('');
  const [suggestion, setSuggestion] = useState(null); // {id, text}

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/titles`).then(r => r.json()).then(setTitles);
  };
  useEffect(refresh, [currentProject]);

  const generate = async () => {
    setLoading(true);
    const res = await fetch(`/api/v1/projects/${currentProject.id}/titles/generate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ count: 10 })
    });
    if (!res.ok) alert('Generate failed: ' + ((await res.json()).detail || res.status));
    refresh();
    setLoading(false);
  };

  const saveOwn = async () => {
    if (!ownTitle.trim()) return;
    await fetch(`/api/v1/projects/${currentProject.id}/titles/own`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: ownTitle })
    });
    setOwnTitle('');
    refresh();
  };

  const saveEdit = async (id) => {
    await fetch(`/api/v1/projects/${currentProject.id}/titles/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: editText })
    });
    setEditingId(null);
    refresh();
  };

  const makeVariants = async (id) => {
    setLoading(true);
    const res = await fetch(`/api/v1/projects/${currentProject.id}/titles/${id}/variants`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instruction: '' })
    });
    if (!res.ok) alert('Variants failed: ' + ((await res.json()).detail || res.status));
    refresh();
    setLoading(false);
  };

  const shorten = async (id) => {
    const res = await fetch(`/api/v1/projects/${currentProject.id}/titles/${id}/shorten`, { method: 'POST' });
    const data = await res.json();
    if (res.ok) setSuggestion({ id, text: data.shortened });
    else alert('Shorten failed: ' + (data.detail || 'Unknown error'));
  };

  const applySuggestion = async () => {
    await fetch(`/api/v1/projects/${currentProject.id}/titles/${suggestion.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: suggestion.text })
    });
    setSuggestion(null);
    refresh();
  };

  const lock = async (id) => {
    await fetch(`/api/v1/titles/${id}/lock?project_id=${currentProject.id}`, { method: 'POST' });
    refresh();
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
        <p className="text-sm text-ink/70 mb-4">Based on your locked idea, the AI proposes 10 distinct angles. Old titles are never deleted.</p>
        <div className="flex gap-2 pt-4 border-t-2 border-ink/10">
          <input
            type="text"
            name="own_title"
            placeholder="Or type your own title..."
            value={ownTitle}
            onChange={e => setOwnTitle(e.target.value)}
            className="flex-1 bg-white border-2 border-ink rounded px-3 py-2 font-body"
          />
          <BlockButton variant="secondary" onClick={saveOwn}>Save Own Title</BlockButton>
        </div>
      </Card>

      {titles.length > 0 && (
        <Card title={`Candidates (${titles.length})`}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {titles.map(t => (
              <div key={t.id} className={`p-4 border-2 rounded-md transition-all ${
                t.locked ? 'border-success bg-success/10 shadow-block' : 'border-ink bg-panel hover:shadow-hover hover:-translate-x-[2px] hover:-translate-y-[2px]'
              }`}>
                <div className="flex justify-between items-start mb-2">
                  <span className="text-xs font-bold uppercase text-info">{t.style_tag}</span>
                  <span className={`text-xs font-mono ${t.char_count > 70 ? 'text-danger font-bold' : 'text-ink/60'}`}>
                    {t.char_count} chars {t.char_count > 70 && '⚠'}
                  </span>
                </div>

                {editingId === t.id ? (
                  <div className="mb-3">
                    <input
                      name="edit_title"
                      value={editText}
                      onChange={e => setEditText(e.target.value)}
                      className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-heading font-bold"
                    />
                    <div className="flex gap-2 justify-end mt-2">
                      <BlockButton variant="secondary" onClick={() => setEditingId(null)}>Cancel</BlockButton>
                      <BlockButton onClick={() => saveEdit(t.id)}>Save</BlockButton>
                    </div>
                  </div>
                ) : (
                  <h3 className="font-heading text-lg font-bold mb-2 leading-tight">{t.text}</h3>
                )}

                <p className="text-sm text-ink/70 mb-3 italic">"{t.angle}"</p>

                {suggestion?.id === t.id && (
                  <div className="mb-3 p-2 bg-warn/20 border-2 border-warn rounded text-sm">
                    ✂️ AI suggests: <span className="font-bold">{suggestion.text}</span>
                    <div className="flex gap-2 justify-end mt-2">
                      <BlockButton variant="secondary" onClick={() => setSuggestion(null)}>Dismiss</BlockButton>
                      <BlockButton onClick={applySuggestion}>Apply</BlockButton>
                    </div>
                  </div>
                )}

                <div className="flex justify-between items-center pt-2 border-t border-ink/10">
                  <div className="flex gap-2 text-xs font-heading">
                    <button onClick={() => { setEditingId(t.id); setEditText(t.text); }} className="hover:text-info">✏️ Edit</button>
                    <button onClick={() => makeVariants(t.id)} className="hover:text-info" disabled={loading}>🎲 3 Variants</button>
                    {t.char_count > 70 && <button onClick={() => shorten(t.id)} className="hover:text-warn">✂️ Shorten</button>}
                  </div>
                  {t.locked ? (
                    <span className="flex items-center gap-2 text-success font-bold text-sm">
                      <StatusDot status="approved" /> LOCKED
                    </span>
                  ) : (
                    <BlockButton onClick={() => lock(t.id)}>Lock</BlockButton>
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
