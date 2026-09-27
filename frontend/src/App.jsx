// frontend/src/App.jsx
import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import BlockButton from './components/BlockButton'
import S01_Home from './screens/S01_Home'
import S02_IdeaStudio from './screens/S02_IdeaStudio'
import S03_TitleStudio from './screens/S03_TitleStudio'
import S04_ScriptStudio from './screens/S04_ScriptStudio'
import S05_CastBoard from './screens/S05_CastBoard'
import S06_VariantTimelines from './screens/S06_VariantTimelines'
import S07_ScoutBoard from './screens/S07_ScoutBoard'
import S08_WorldDesk from './screens/S08_WorldDesk'
import S09_BeatBoard from './screens/S09_BeatBoard'
import S10_Sheets from './screens/S10_Sheets'
import S11_Library from './screens/S11_Library'
import S15_Assets from './screens/S15_Assets'
import S16_MyVideo from './screens/S16_MyVideo'
import S12_Export from './screens/S12_Export'
import S13_Checkpoint from './screens/S13_Checkpoint'
import S14_Handoff from './screens/S14_Handoff'
import S17_Settings from './screens/S17_Settings'
import S18_Prompts from './screens/S18_Prompts'
import { setSfxEnabled, playSfx } from './lib/sfx'

function App() {
  const [status, setStatus] = useState('loading')
  const [activeNode, setActiveNode] = useState('home')
  const [currentChannel, setCurrentChannel] = useState(null)
  const [currentProject, setCurrentProject] = useState(null)
  const [stale, setStale] = useState({})
  const [staleBusy, setStaleBusy] = useState(false)
  const [staleMsg, setStaleMsg] = useState('')

  const routed = ['home', 'idea', 'title', 'script', 'cast', 'variants', 'locations', 'world', 'beats', 'sheets', 'library', 'assets', 'myvideo', 'export', 'checkpoint', 'handoff', 'settings', 'prompts']

  useEffect(() => {
    fetch('/api/v1/settings')
      .then(res => res.json())
      .then(data => {
        setStatus(data.api_key ? 'ready' : 'no_key');
        setSfxEnabled(data.sfx);
      })
      .catch(() => setStatus('error'))
  }, [])

  // Stale counts refresh on project change and after any re-extract.
  const loadStale = () => {
    if (!currentProject?.id) { setStale({}); return; }
    fetch(`/api/v1/projects/${currentProject.id}/stale`)
      .then(res => res.json())
      .then(d => setStale(d || {}))
      .catch(() => setStale({}));
  };

  useEffect(() => { loadStale(); }, [currentProject?.id]);

  const staleAction = async (kind) => {
    if (!currentProject?.id) return;
    setStaleBusy(true); setStaleMsg('');
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/stale/${kind}`, { method: 'POST' });
      const data = await res.json();
      if (!res.ok) { setStaleMsg(data.detail || 'Failed'); playSfx('error'); return; }
      if (kind === 'reextract') {
        const failed = data.failed || [];
        setStaleMsg(failed.length ? `Rebuilt, but ${failed.join(', ')} failed` : `Rebuilt ${(data.attempted || []).join(', ')}`);
        playSfx(failed.length ? 'error' : 'success');
      } else {
        setStaleMsg(`Marked ${data.cleared} reviewed`);
        playSfx('save');
      }
      loadStale();
    } catch { setStaleMsg('Network error'); playSfx('error'); }
    setStaleBusy(false);
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-sky">
      <TopBar
        channel={currentChannel?.name}
        project={currentProject?.slug}
        jobQueue={0}
      />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          activeNode={activeNode}
          onNodeClick={setActiveNode}
          staleCounts={stale}
        />

        <main className="flex-1 p-8 overflow-y-auto">
          <div className="max-w-6xl mx-auto">

            {(stale.total > 0) && (
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 p-3 border-2 border-warn bg-warn/15 rounded-md">
                <p className="font-body text-sm text-ink">
                  <span className="font-heading font-bold">{stale.total} artifact{stale.total === 1 ? '' : 's'} went stale</span>
                  {' — the locked script changed, so these need a look: '}
                  <span className="font-mono text-xs">
                    {['cast', 'variants', 'locations', 'world', 'beats', 'sheets']
                      .filter(s => stale[s] > 0).map(s => `${s} ${stale[s]}`).join(' · ')}
                  </span>
                </p>
                <div className="flex items-center gap-2">
                  <BlockButton variant="secondary" disabled={staleBusy} onClick={() => staleAction('clear')}>
                    Mark reviewed
                  </BlockButton>
                  <BlockButton disabled={staleBusy} onClick={() => staleAction('reextract')}>
                    {staleBusy ? 'Rebuilding…' : 'Re-extract stale'}
                  </BlockButton>
                  {staleMsg && <span className="text-xs font-heading text-primary">{staleMsg}</span>}
                </div>
              </div>
            )}

            {activeNode === 'home' && (
              <S01_Home
                currentChannel={currentChannel}
                currentProject={currentProject}
                onSelectChannel={setCurrentChannel}
                onSelectProject={setCurrentProject}
                onNavigate={setActiveNode}
              />
            )}

            {activeNode === 'idea' && (
              <S02_IdeaStudio 
                currentProject={currentProject} 
                currentChannel={currentChannel} 
                onNavigate={setActiveNode}
              />
            )}

            {activeNode === 'title' && (
              <S03_TitleStudio 
                currentProject={currentProject} 
                onNavigate={setActiveNode}
              />
            )}

            {activeNode === 'script' && (
              <S04_ScriptStudio currentProject={currentProject} onNavigate={setActiveNode} />
            )}

            {activeNode === 'cast' && (
              <S05_CastBoard currentProject={currentProject} />
            )}

            {activeNode === 'variants' && (
              <S06_VariantTimelines currentProject={currentProject} />
            )}

            {activeNode === 'locations' && (
              <S07_ScoutBoard currentProject={currentProject} />
            )}

            {activeNode === 'world' && (
              <S08_WorldDesk currentProject={currentProject} />
            )}

            {activeNode === 'beats' && (
              <S09_BeatBoard currentProject={currentProject} />
            )}

            {activeNode === 'sheets' && (
              <S10_Sheets currentProject={currentProject} />
            )}

            {activeNode === 'library' && (
              <S11_Library currentProject={currentProject} />
            )}

            {activeNode === 'assets' && (
              <S15_Assets currentProject={currentProject} />
            )}

            {activeNode === 'myvideo' && (
              <S16_MyVideo currentProject={currentProject} />
            )}

            {activeNode === 'export' && (
              <S12_Export currentProject={currentProject} />
            )}

            {activeNode === 'checkpoint' && (
              <S13_Checkpoint currentProject={currentProject} />
            )}

            {activeNode === 'handoff' && (
              <S14_Handoff currentProject={currentProject} />
            )}

            {activeNode === 'settings' && <S17_Settings />}

            {activeNode === 'prompts' && <S18_Prompts />}

            {!routed.includes(activeNode) && (
              <div className="card max-w-2xl mx-auto mt-12 text-center">
                <h2 className="font-display text-xl mb-4">{activeNode.toUpperCase()} STUDIO</h2>
                <p className="font-body mb-6">This screen is under construction.</p>
                <p className="text-sm text-ink/60 mb-6">
                  Current Project: <span className="font-bold">{currentProject?.id || 'None'}</span>
                </p>
                <button onClick={() => setActiveNode('home')} className="btn-primary">
                  ← Back to Home
                </button>
              </div>
            )}

          </div>
        </main>
      </div>
    </div>
  )
}

export default App