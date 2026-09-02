import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

const getPrompt = (text) => {
  const marker = '## 3x3 grid prompt';
  const i = text.indexOf(marker);
  return i === -1 ? '' : text.slice(i + marker.length).trim();
};

export default function S10_Sheets({ currentProject }) {
  const [sheets, setSheets] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const refresh = () => {
    if (currentProject)
      fetch(`/api/v1/projects/${currentProject.id}/sheets`)
        .then(r => r.json())
        .then(rows => {
          setSheets(rows);
          if (!selected && rows.length) setSelected(rows[0].asset_id);
        })
        .catch(() => {});
  };
  useEffect(refresh, [currentProject]);

  const generate = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/sheets/generate`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) alert('Generate failed:\n\n' + (data.detail || 'Unknown error'));
      else { alert(`Sheets written: ${data.characters} characters, ${data.environments} environments.`); refresh(); }
    } catch (e) { alert('Network error: ' + e.message); }
    setLoading(false);
  };

  const copyPrompt = async () => {
    const sheet = sheets.find(s => s.asset_id === selected);
    if (!sheet) return;
    try {
      await navigator.clipboard.writeText(getPrompt(sheet.text));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      alert('Copy failed — select the prompt text manually from the preview.');
    }
  };

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
      </div>
    );
  }

  const chars = sheets.filter(s => s.kind === 'characters');
  const envs = sheets.filter(s => s.kind === 'environments');
  const current = sheets.find(s => s.asset_id === selected);

  const listItem = (s) => (
    <button key={s.asset_id} onClick={() => setSelected(s.asset_id)}
      className={`w-full text-left px-3 py-2 border-2 rounded-md font-heading text-sm font-bold transition-all ${
        selected === s.asset_id ? 'border-primary bg-primary/10' : 'border-ink/20 bg-white hover:border-ink'}`}>
      {s.asset_id} — {s.title.split('— ')[1] || s.title}
      {s.text.includes('Green conflict: YES') && <span className="ml-2 text-success">🟢</span>}
    </button>
  );

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="font-display text-2xl text-ink">Style Sheets (P14/P15)</h2>
        <BlockButton onClick={generate} disabled={loading}>
          {loading ? 'Writing...' : '🎨 Regenerate Sheets'}
        </BlockButton>
      </div>

      {sheets.length === 0 ? (
        <Card title="No Sheets Yet">
          <p className="font-body text-sm text-ink/70">Click "Regenerate Sheets" to write artist briefs for every active character and location.</p>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="space-y-4 md:col-span-1">
            <Card title={`Characters (${chars.length})`}>
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">{chars.map(listItem)}</div>
            </Card>
            <Card title={`Environments (${envs.length})`}>
              <div className="space-y-2 max-h-72 overflow-y-auto pr-1">{envs.map(listItem)}</div>
            </Card>
          </div>

          <div className="md:col-span-2">
            {current && (
              <Card title={current.title} actions={
                <BlockButton variant="secondary" onClick={copyPrompt}>
                  {copied ? '✓ Copied!' : '📋 Copy 3x3 Prompt'}
                </BlockButton>
              }>
                <div className="bg-white border-2 border-ink rounded-md p-4 font-body text-sm whitespace-pre-wrap max-h-[32rem] overflow-y-auto">
                  {current.text}
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
