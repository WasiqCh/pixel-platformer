import { useState, useEffect } from 'react';
import Card from './Card';
import BlockButton from './BlockButton';

export default function KitWizard({ channel }) {
  const [refs, setRefs] = useState([]);
  const [descriptor, setDescriptor] = useState('');
  const [presets, setPresets] = useState([]);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  const load = () => {
    fetch(`/api/v1/channels/${channel.id}/kit/refs`).then(r => r.json()).then(setRefs);
    fetch(`/api/v1/channels/${channel.id}`).then(r => r.json()).then(ch => setDescriptor(ch.descriptor || ''));
    fetch('/api/v1/channels/kit/presets').then(r => r.json()).then(setPresets).catch(() => setPresets([]));
  };
  useEffect(() => { load(); }, [channel.id]);

  const applyPreset = (id) => {
    const p = presets.find(x => x.id === id);
    if (!p || !p.body) return;
    setDescriptor(p.body);
    setMsg(`Preset "${p.name}" filled — edit freely, then press Save Kit to keep it.`);
  };

  const upload = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;
    const fd = new FormData();
    files.forEach(f => fd.append('files', f));
    setBusy(true);
    await fetch(`/api/v1/channels/${channel.id}/kit/refs`, { method: 'POST', body: fd });
    setBusy(false);
    e.target.value = '';
    load();
  };

  const draft = async () => {
    setBusy(true); setMsg('');
    const res = await fetch(`/api/v1/channels/${channel.id}/kit/descriptor`, { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      setDescriptor(data.parsed);
      // Auto-persist so navigating away NEVER loses the draft
      await fetch(`/api/v1/channels/${channel.id}/kit`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ descriptor: data.parsed })
      });
      setMsg('Drafted AND saved automatically. Edit freely, then press Save Kit to keep your edits.');
    } else {
      setMsg('AI draft unavailable — write it manually below, then press Save Kit.');
    }
    setBusy(false);
  };

  const save = async () => {
    setBusy(true);
    await fetch(`/api/v1/channels/${channel.id}/kit`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ descriptor })
    });
    setBusy(false);
    setMsg('Kit saved — version bumped.');
  };

  return (
    <Card title="Style Kit (P08)">
      <p className="text-sm text-ink/70 mb-3">Upload 2–4 sample images of your fixed style. They anchor every prompt this channel ever writes.</p>
      
      <input type="file" accept="image/*" multiple onChange={upload} className="mb-3 font-body" />
      
      {refs.length > 0 && (
        <div className="flex gap-2 mb-4">
          {refs.map(name => (
            <img key={name} src={`/api/v1/channels/${channel.id}/kit/refs/${name}`} alt={name}
                 className="w-20 h-20 object-cover border-2 border-ink rounded" />
          ))}
        </div>
      )}

      <div className="flex gap-2 mb-3">
        <BlockButton variant="secondary" onClick={draft} disabled={busy || refs.length === 0}>
          {busy ? 'Thinking...' : 'Draft Descriptor with AI'}
        </BlockButton>
        <BlockButton onClick={save} disabled={busy}>Save Kit</BlockButton>
      </div>

      {msg && <p className="text-sm font-bold text-info mb-2">{msg}</p>}

      <div className="flex gap-2 mb-3 items-center">
        <label className="text-sm font-bold">Start from a preset:</label>
        <select
          onChange={e => { if (e.target.value) applyPreset(e.target.value); e.target.value = ''; }}
          defaultValue=""
          className="bg-white border-2 border-ink rounded-md px-2 py-1 font-body text-sm focus:outline-none focus:border-info"
        >
          <option value="">Pick a style preset…</option>
          {presets.map(p => (
            <option key={p.id} value={p.id} disabled={!p.body}>
              {p.name}{p.body ? '' : ' (owner wording pending)'}
            </option>
          ))}
        </select>
      </div>

      <textarea
        value={descriptor}
        onChange={e => setDescriptor(e.target.value)}
        rows={6}
        placeholder="LINE QUALITY / COLOR BEHAVIOR / SHADING / PROPORTIONS / BACKGROUNDS / NEVER-DOES..."
        className="w-full bg-white border-2 border-ink rounded-md px-3 py-2 font-body text-sm focus:outline-none focus:border-info"
      />
    </Card>
  );
}