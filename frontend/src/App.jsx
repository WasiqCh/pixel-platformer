// frontend/src/App.jsx
import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
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
import S17_Settings from './screens/S17_Settings'

function App() {
  const [status, setStatus] = useState('loading')
  const [activeNode, setActiveNode] = useState('home')
  const [currentChannel, setCurrentChannel] = useState(null)
  const [currentProject, setCurrentProject] = useState(null)

  const routed = ['home', 'idea', 'title', 'script', 'cast', 'variants', 'locations', 'world', 'beats', 'sheets', 'library', 'settings']

  useEffect(() => {
    fetch('/api/v1/settings')
      .then(res => res.json())
      .then(data => setStatus(data.api_key ? 'ready' : 'no_key'))
      .catch(() => setStatus('error'))
  }, [])

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
          staleCounts={{}}
        />

        <main className="flex-1 p-8 overflow-y-auto">
          <div className="max-w-6xl mx-auto">

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
              <S04_ScriptStudio currentProject={currentProject} />
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

            {activeNode === 'settings' && <S17_Settings />}

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