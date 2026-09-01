// frontend/src/screens/S01_Home.jsx
import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import StatusDot from '../components/StatusDot';
import KitWizard from '../components/KitWizard';

export default function S01_Home({ currentChannel, currentProject, onSelectChannel, onSelectProject, onNavigate }) {
  const [channels, setChannels] = useState([]);
  const [projects, setProjects] = useState([]);
  const [newChName, setNewChName] = useState('');
  const [newProjSlug, setNewProjSlug] = useState('');

  useEffect(() => {
    fetch('/api/v1/channels').then(r => r.json()).then(setChannels);
  }, []);

  const refreshProjects = () => {
    if (currentChannel)
      fetch(`/api/v1/channels/${currentChannel.id}/projects`).then(r => r.json()).then(setProjects);
    else setProjects([]);
  };
  useEffect(refreshProjects, [currentChannel]);

  const createChannel = async () => {
    if (!newChName) return;
    try {
      const res = await fetch('/api/v1/channels', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newChName })
      });
      if (!res.ok) { alert('Backend error: ' + ((await res.json()).detail || res.status)); return; }
      const ch = await res.json();
      setChannels([ch, ...channels]);
      onSelectChannel(ch);
      setNewChName('');
    } catch (e) { alert('Network error: ' + e.message); }
  };

  const createProject = async () => {
    if (!newProjSlug || !currentChannel) return;
    const res = await fetch(`/api/v1/channels/${currentChannel.id}/projects`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slug: newProjSlug })
    });
    const proj = await res.json();
    setNewProjSlug('');
    refreshProjects();
    onSelectProject(proj);
  };

  const renameProject = async (e, p) => {
    e.stopPropagation();
    const name = prompt('Rename project (folder path stays stable):', p.slug);
    if (!name || name === p.slug) return;
    await fetch(`/api/v1/projects/${p.id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slug: name })
    });
    refreshProjects();
  };

  const forkProject = async (e, p) => {
    e.stopPropagation();
    const name = prompt('Fork as new project named:', p.slug + ' (fork)');
    if (!name) return;
    await fetch(`/api/v1/projects/${p.id}/duplicate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ slug: name })
    });
    refreshProjects();
  };

  const deleteProject = async (e, p) => {
    e.stopPropagation();
    if (!confirm(`Delete ${p.slug} (${p.id})?\nRemoves DB row AND folder. No undo.`)) return;
    await fetch(`/api/v1/projects/${p.id}`, { method: 'DELETE' });
    if (currentProject?.id === p.id) onSelectProject(null);
    refreshProjects();
  };

  const rescan = async () => {
    const res = await fetch('/api/v1/projects/scan', { method: 'POST' });
    const d = await res.json();
    alert(`Rescan complete.\nRecovered folders: ${d.added.length}\nRemoved ghost rows: ${d.removed.length}`);
    refreshProjects();
  };

  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <h2 className="font-display text-3xl text-ink">Production Office</h2>

      <Card title="1. Select Channel">
        {channels.length === 0 ? (
          <p className="mb-4 text-ink/70">No channels yet. Create your first one to start.</p>
        ) : (
          <div className="flex flex-wrap gap-2 mb-4">
            {channels.map(ch => (
              <button key={ch.id} onClick={() => onSelectChannel(ch)}
                className={`px-4 py-2 border-2 border-ink rounded font-heading font-bold transition-all ${currentChannel?.id === ch.id ? 'bg-primary text-white shadow-block' : 'bg-panel hover:bg-sky/20'
                  }`}>
                {ch.name}
              </button>
            ))}
          </div>
        )}
        <div className="flex gap-2 mt-4 pt-4 border-t-2 border-ink/10">
          <input type="text" name="new_channel" placeholder="New channel name..."
            value={newChName} onChange={e => setNewChName(e.target.value)}
            className="flex-1 bg-white border-2 border-ink rounded px-3 py-2 font-body" />
          <BlockButton onClick={createChannel}>Create Channel</BlockButton>
        </div>
      </Card>

      {currentChannel && (
        <Card title={`2. Select Project (${currentChannel.name})`}
          actions={<BlockButton variant="secondary" onClick={rescan}>🔄 Rescan</BlockButton>}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            {projects.map(p => (
              <div key={p.id} onClick={() => onSelectProject(p)}
                className={`p-4 border-2 border-ink rounded cursor-pointer transition-all ${currentProject?.id === p.id ? 'bg-success/20 shadow-block' : 'bg-panel hover:shadow-hover hover:-translate-x-[2px] hover:-translate-y-[2px]'
                  }`}>
                <div className="flex justify-between items-start mb-2">
                  <span className="font-heading font-bold text-lg">{p.slug}</span>
                  <StatusDot status="approved" />
                </div>
                <div className="text-xs font-mono text-ink/60 mb-2">{p.id} · {p.stage}</div>
                <div className="flex gap-2 pt-2 border-t border-ink/10 text-xs font-heading">
                  <button onClick={(e) => renameProject(e, p)} className="hover:text-info">✏️ Rename</button>
                  <button onClick={(e) => forkProject(e, p)} className="hover:text-info">⧉ Fork</button>
                  <button onClick={(e) => deleteProject(e, p)} className="hover:text-danger">🗑 Delete</button>
                </div>
              </div>
            ))}
          </div>
          <div className="flex gap-2 pt-4 border-t-2 border-ink/10">
            <input type="text" name="new_project" placeholder="New project title..."
              value={newProjSlug} onChange={e => setNewProjSlug(e.target.value)}
              className="flex-1 bg-white border-2 border-ink rounded px-3 py-2 font-body" />
            <BlockButton onClick={createProject}>Create Project</BlockButton>
          </div>
        </Card>
      )}

      {currentChannel && <KitWizard channel={currentChannel} />}

      {currentProject && (
        <div className="space-y-4">
          <h3 className="font-heading text-2xl font-bold text-ink">3. Start Production</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <button onClick={() => onNavigate('idea')} className="card text-left group hover:shadow-hover hover:-translate-x-[2px] hover:-translate-y-[2px] transition-all">
              <div className="font-display text-xs text-info mb-2">STEP 1</div>
              <h4 className="font-heading text-xl font-bold mb-2 group-hover:text-primary">Start with Idea</h4>
              <p className="text-sm text-ink/70">Brainstorm concepts, hooks, and scope.</p>
            </button>
            <button onClick={() => onNavigate('title')} className="card text-left group hover:shadow-hover hover:-translate-x-[2px] hover:-translate-y-[2px] transition-all">
              <div className="font-display text-xs text-info mb-2">STEP 1</div>
              <h4 className="font-heading text-xl font-bold mb-2 group-hover:text-primary">Start with Title</h4>
              <p className="text-sm text-ink/70">I already have a killer headline.</p>
            </button>
            <button onClick={() => onNavigate('script')} className="card text-left group hover:shadow-hover hover:-translate-x-[2px] hover:-translate-y-[2px] transition-all">
              <div className="font-display text-xs text-info mb-2">STEP 1</div>
              <h4 className="font-heading text-xl font-bold mb-2 group-hover:text-primary">Start with Script</h4>
              <p className="text-sm text-ink/70">I have a draft ready to go.</p>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}