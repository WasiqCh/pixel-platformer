// frontend/src/screens/S05_CastBoard.jsx
import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import StatusDot from '../components/StatusDot';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 500) || `HTTP ${res.status} (Empty response)` }; }
};

export default function S05_CastBoard({ currentProject }) {
  const [characters, setCharacters] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState(null);

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/characters`)
        .then(r => r.json())
        .then(setCharacters);
  };
  useEffect(refresh, [currentProject]);

  const extract = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/characters/extract`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) { 
        alert('Extract failed:\n\n' + (data.detail || 'Unknown error')); 
      } else {
        alert(`Success! Added: ${data.added}, Updated: ${data.updated}`);
        refresh();
      }
    } catch (e) { alert('Network error: ' + e.message); }
    setLoading(false);
  };

  const updateSignificance = async (charId, sig) => {
    await fetch(`/api/v1/projects/${currentProject.id}/characters/${charId}/significance`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ significance: sig })
    });
    refresh();
  };

  const updateRender = async (charId, render) => {
    await fetch(`/api/v1/projects/${currentProject.id}/characters/${charId}/render`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ render })
    });
    refresh();
  };

  const startEdit = (char) => {
    setEditingId(char.id);
    setEditDraft({
      names: char.names.join(', '),
      appearance: char.appearance || '',
      faction: char.faction || '',
    });
  };

  const saveEdit = async (charId) => {
    await fetch(`/api/v1/projects/${currentProject.id}/characters/${charId}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        names: editDraft.names.split(',').map(s => s.trim()).filter(Boolean),
        appearance: editDraft.appearance,
        faction: editDraft.faction,
      })
    });
    setEditingId(null);
    refresh();
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
        <p className="font-body">Go to Home and select a project first.</p>
      </div>
    );
  }

  const activeChars = characters.filter(c => !c.stale);
  const staleChars = characters.filter(c => c.stale);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="font-display text-2xl text-ink">Cast Board (P09)</h2>
        <BlockButton onClick={extract} disabled={loading}>
          {loading ? 'Extracting...' : '🧠 Re-Extract Characters'}
        </BlockButton>
      </div>

      <Card title={`Active Cast (${activeChars.length})`}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {activeChars.map(char => (
            <div key={char.id} className={`p-4 border-2 rounded-md bg-panel shadow-block transition-all ${
              char.significance === 'core' ? 'border-primary' : 
              char.significance === 'supporting' ? 'border-info' : 'border-ink/30'
            }`}>
              {editingId === char.id ? (
                <div className="space-y-2">
                  <input name={`edit_names_${char.id}`} value={editDraft.names}
                    onChange={e => setEditDraft({ ...editDraft, names: e.target.value })}
                    className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-body text-sm"
                    placeholder="Names (comma separated)" />
                  <textarea name={`edit_app_${char.id}`} value={editDraft.appearance}
                    onChange={e => setEditDraft({ ...editDraft, appearance: e.target.value })}
                    className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-body text-sm" rows={3}
                    placeholder="Appearance..." />
                  <input name={`edit_fac_${char.id}`} value={editDraft.faction}
                    onChange={e => setEditDraft({ ...editDraft, faction: e.target.value })}
                    className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-body text-sm"
                    placeholder="Faction..." />
                  <div className="flex gap-2 justify-end">
                    <BlockButton variant="secondary" onClick={() => setEditingId(null)}>Cancel</BlockButton>
                    <BlockButton onClick={() => saveEdit(char.id)}>Save</BlockButton>
                  </div>
                </div>
              ) : (
                <>
                  <div className="flex justify-between items-start mb-2">
                    <div>
                      <h3 className="font-heading text-lg font-bold">{char.names[0]}</h3>
                      <p className="text-xs font-mono text-ink/50">{char.id} · {char.kind}</p>
                    </div>
                    {char.green_conflict === 1 && (
                      <span className="text-xs font-bold bg-success/20 border border-success text-success px-2 py-1 rounded">🟢 GREEN</span>
                    )}
                  </div>

                  <p className="font-body text-sm text-ink/80 mb-3 min-h-[3rem]">{char.appearance || <span className="italic text-ink/40">No appearance description.</span>}</p>

                  <div className="space-y-2 text-xs font-body">
                    <div className="flex items-center gap-2">
                      <span className="font-bold w-20">Significance:</span>
                      <select name={`sig_${char.id}`} value={char.significance}
                        onChange={e => updateSignificance(char.id, e.target.value)}
                        className="flex-1 bg-white border-2 border-ink rounded px-1 py-0.5">
                        <option value="core">Core</option>
                        <option value="supporting">Supporting</option>
                        <option value="minor">Minor</option>
                      </select>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="font-bold w-20">Render:</span>
                      <button onClick={() => updateRender(char.id, char.render === 'drawn' ? 'fetched' : 'drawn')}
                        className={`flex-1 text-center px-2 py-0.5 border-2 rounded font-bold ${
                          char.render === 'fetched' ? 'bg-warn border-warn text-white' : 'bg-panel border-ink/30 text-ink/70'
                        }`}>
                        {char.render === 'fetched' ? '📷 Real Photo' : '🎨 Drawn'}
                      </button>
                    </div>

                    {char.faction && (
                      <div className="flex items-center gap-2">
                        <span className="font-bold w-20">Faction:</span>
                        <span className="text-ink/70">{char.faction}</span>
                      </div>
                    )}
                  </div>

                  <div className="flex justify-end mt-3 pt-2 border-t border-ink/10">
                    <button onClick={() => startEdit(char)} className="text-xs font-heading font-bold hover:text-info">✏️ Edit Details</button>
                  </div>
                </>
              )}
            </div>
          ))}
        </div>
      </Card>

      {staleChars.length > 0 && (
        <Card title={`Stale Characters (${staleChars.length}) - Not found in latest script`}>
          <p className="font-body text-sm text-ink/70 mb-4">These characters were removed from the script. You can review them or dismiss them.</p>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 opacity-60">
            {staleChars.map(char => (
              <div key={char.id} className="p-3 border-2 border-danger/30 rounded-md bg-danger/5">
                <h3 className="font-heading text-base font-bold mb-1">{char.names[0]}</h3>
                <p className="text-xs font-mono text-ink/50 mb-2">{char.id}</p>
                <p className="font-body text-xs text-ink/70 mb-2 line-clamp-2">{char.appearance}</p>
                <div className="flex justify-end">
                  <button className="text-xs font-heading font-bold text-danger hover:underline">🗑 Dismiss</button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
