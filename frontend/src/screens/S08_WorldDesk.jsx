import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

const TYPE_INFO = {
  map_trigger: { icon: '🗺️', color: 'border-info bg-info/10', label: 'Map Triggers' },
  brand_logo:  { icon: '🏷️', color: 'border-warn bg-warn/10', label: 'Brands & Logos' },
  real_person: { icon: '👤', color: 'border-danger bg-danger/10', label: 'Real Persons' },
  meme:        { icon: '😄', color: 'border-success bg-success/10', label: 'Memes' },
};

const MAP_TEMPLATES = ['flag_fill', 'region_highlight', 'paper', 'split'];

export default function S08_WorldDesk({ currentProject }) {
  const [records, setRecords] = useState([]);
  const [selected, setSelected] = useState([]);
  const [loading, setLoading] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [editDraft, setEditDraft] = useState(null);

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/world`)
        .then(r => r.json())
        .then(rows => {
          setRecords(rows);
          setSelected(prev => prev.filter(id => rows.some(r => r.id === id)));
        })
        .catch(() => {});
  };
  useEffect(refresh, [currentProject]);

  const scan = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/world/scan`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) alert('Scan failed:\n\n' + (data.detail || 'Unknown error'));
      else { alert(`Success! Added: ${data.added}, Updated: ${data.updated}`); refresh(); }
    } catch (e) { alert('Network error: ' + e.message); }
    setLoading(false);
  };

  const setStatus = async (recId, status) => {
    await fetch(`/api/v1/projects/${currentProject.id}/world/${recId}/status`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    refresh();
  };

  const remove = async (recId) => {
    if (!confirm('Delete this world record?')) return;
    await fetch(`/api/v1/projects/${currentProject.id}/world/${recId}`, { method: 'DELETE' });
    refresh();
  };

  // ---- bulk actions (i + ii) ----
  const toggleSelect = (id) => {
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]);
  };

  const toggleAll = () => {
    setSelected(prev => prev.length === records.length ? [] : records.map(r => r.id));
  };

  const bulkStatus = async (status) => {
    for (const id of selected) {
      await fetch(`/api/v1/projects/${currentProject.id}/world/${id}/status`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status })
      });
    }
    setSelected([]);
    refresh();
  };

  const bulkDelete = async () => {
    if (!confirm(`Delete ${selected.length} record(s)? This cannot be undone.`)) return;
    for (const id of selected) {
      await fetch(`/api/v1/projects/${currentProject.id}/world/${id}`, { method: 'DELETE' });
    }
    setSelected([]);
    refresh();
  };

  const startEdit = (r) => {
    setEditingId(r.id);
    setEditDraft({
      search_query: r.search_query || '',
      era_hint: r.era_hint || '',
      usage_intent: r.usage_intent || '',
      map_template: r.map_template || '',
    });
  };

  const saveEdit = async (recId) => {
    await fetch(`/api/v1/projects/${currentProject.id}/world/${recId}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(editDraft)
    });
    setEditingId(null);
    refresh();
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
      </div>
    );
  }

  const groups = {};
  for (const r of records) {
    if (!groups[r.type]) groups[r.type] = [];
    groups[r.type].push(r);
  }

  const mapCount = (groups.map_trigger || []).length;
  const memeCount = (groups.meme || []).length;

  const renderCard = (r) => (
    <div key={r.id} className={`p-4 border-2 rounded-md bg-panel shadow-block ${
      r.status === 'approved' ? 'border-success' :
      r.status === 'dismissed' ? 'border-danger opacity-60' : 'border-ink'}`}>
      <div className="flex justify-between items-start mb-2">
        <div className="flex items-start gap-2">
          <input type="checkbox" name={`select_${r.id}`} checked={selected.includes(r.id)}
            onChange={() => toggleSelect(r.id)} className="w-4 h-4 mt-1 accent-primary" />
          <div>
            <h3 className="font-heading text-base font-bold">{r.text}</h3>
            <p className="text-xs font-mono text-ink/50">{r.id} · {r.type}</p>
          </div>
        </div>
        <span className={`text-xs font-bold px-2 py-1 rounded border-2 ${
          r.status === 'approved' ? 'bg-success/20 border-success text-success' :
          r.status === 'dismissed' ? 'bg-danger/20 border-danger text-danger' :
          'bg-warn/20 border-warn text-ink'}`}>
          {r.status.toUpperCase()}
        </span>
      </div>

      {editingId === r.id ? (
        <div className="space-y-2">
          <input name={`edit_sq_${r.id}`} value={editDraft.search_query}
            onChange={e => setEditDraft({ ...editDraft, search_query: e.target.value })}
            className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-body text-sm"
            placeholder="Search query (1-4 words)" />
          <input name={`edit_era_${r.id}`} value={editDraft.era_hint}
            onChange={e => setEditDraft({ ...editDraft, era_hint: e.target.value })}
            className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-body text-sm"
            placeholder="Era hint (e.g. 1498)" />
          <input name={`edit_intent_${r.id}`} value={editDraft.usage_intent}
            onChange={e => setEditDraft({ ...editDraft, usage_intent: e.target.value })}
            className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-body text-sm"
            placeholder="Usage intent" />
          {r.type === 'map_trigger' && (
            <select name={`edit_map_${r.id}`} value={editDraft.map_template}
              onChange={e => setEditDraft({ ...editDraft, map_template: e.target.value })}
              className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-body text-sm">
              <option value="">-- Map template --</option>
              {MAP_TEMPLATES.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          )}
          <div className="flex gap-2 justify-end">
            <BlockButton variant="secondary" onClick={() => setEditingId(null)}>Cancel</BlockButton>
            <BlockButton onClick={() => saveEdit(r.id)}>Save</BlockButton>
          </div>
        </div>
      ) : (
        <>
          <div className="font-body text-sm text-ink/80 space-y-1 mb-3">
            {r.search_query && <p><span className="font-bold">Query:</span> {r.search_query}</p>}
            {r.era_hint && <p><span className="font-bold">Era:</span> {r.era_hint}</p>}
            {r.usage_intent && <p><span className="font-bold">Intent:</span> {r.usage_intent}</p>}
            {r.map_template && (
              <p>
                <span className="font-bold">Map template:</span>{' '}
                <span className="bg-info/20 border border-info px-2 py-0.5 rounded text-xs font-bold">{r.map_template}</span>
              </p>
            )}
          </div>

          <div className="flex flex-wrap gap-2 pt-2 border-t border-ink/10">
            <BlockButton variant="secondary" onClick={() => setStatus(r.id, 'approved')}>✓ Approve</BlockButton>
            <BlockButton variant="secondary" onClick={() => setStatus(r.id, 'dismissed')}>✗ Dismiss</BlockButton>
            <BlockButton variant="secondary" onClick={() => startEdit(r)}>✏️ Edit</BlockButton>
            <button onClick={() => remove(r.id)} className="text-xs font-heading font-bold text-danger hover:underline self-center ml-auto">🗑 Delete</button>
          </div>
        </>
      )}
    </div>
  );

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="font-display text-2xl text-ink">World Desk (P12)</h2>
        <BlockButton onClick={scan} disabled={loading}>
          {loading ? 'Scanning...' : '🔍 Re-Scan World'}
        </BlockButton>
      </div>

      <div className="grid grid-cols-3 gap-4">
        <div className="p-3 border-2 border-info rounded-md bg-info/10">
          <p className="text-xs font-bold text-info mb-1 font-heading">🗺️ MAP TRIGGERS</p>
          <p className="font-display text-2xl font-bold">{mapCount}</p>
          <p className="text-xs text-ink/60">Animated map insert candidates</p>
        </div>
        <div className="p-3 border-2 border-warn rounded-md bg-warn/10">
          <p className="text-xs font-bold text-warn mb-1 font-heading">🏷️ BRANDS & ASSETS</p>
          <p className="font-display text-2xl font-bold">{records.filter(r => r.type !== 'map_trigger' && r.type !== 'meme').length}</p>
          <p className="text-xs text-ink/60">Logos, persons, objects</p>
        </div>
        <div className="p-3 border-2 border-success rounded-md bg-success/10">
          <p className="text-xs font-bold text-success mb-1 font-heading">😄 MEMES</p>
          <p className="font-display text-2xl font-bold">{memeCount}</p>
          <p className="text-xs text-ink/60">Cultural reference candidates</p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 p-3 border-2 border-ink rounded-md bg-panel">
        <label className="flex items-center gap-2 font-heading text-sm font-bold cursor-pointer">
          <input type="checkbox" name="select_all"
            checked={records.length > 0 && selected.length === records.length}
            onChange={toggleAll} className="w-4 h-4 accent-primary" />
          Select All ({records.length})
        </label>
        {selected.length > 0 && (
          <div className="flex items-center gap-2 ml-auto">
            <span className="text-sm font-body text-ink/70">{selected.length} selected →</span>
            <BlockButton variant="secondary" onClick={() => bulkStatus('approved')}>✓ Approve</BlockButton>
            <BlockButton variant="secondary" onClick={() => bulkStatus('dismissed')}>✗ Dismiss</BlockButton>
            <BlockButton variant="danger" onClick={bulkDelete}>🗑 Delete</BlockButton>
          </div>
        )}
      </div>

      {Object.entries(groups).map(([type, recs]) => {
        const info = TYPE_INFO[type] || { icon: '📦', color: 'border-ink bg-panel', label: type };
        return (
          <Card key={type} title={`${info.icon} ${info.label} (${recs.length})`}>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {recs.map(renderCard)}
            </div>
          </Card>
        );
      })}

      {records.length === 0 && (
        <Card title="No World Records Yet">
          <p className="font-body text-sm text-ink/70">Click "Re-Scan World" to find brands, map triggers, real persons and memes.</p>
        </Card>
      )}
    </div>
  );
}
