// frontend/src/App.jsx
import { useState, useEffect } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import S17_Settings from './screens/S17_Settings'
import S01_Home from './screens/S01_Home' // <--- ADD

function App() {
  const [status, setStatus] = useState('loading')
  const [activeNode, setActiveNode] = useState('home')
  
  // New State for Session
  const [currentChannel, setCurrentChannel] = useState(null)
  const [currentProject, setCurrentProject] = useState(null)

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

            {activeNode === 'settings' && <S17_Settings />}

            {activeNode !== 'home' && activeNode !== 'settings' && (
              <div className="card max-w-2xl mx-auto mt-12 text-center">
                <h2 className="font-display text-xl mb-4">{activeNode.toUpperCase()} STUDIO</h2>
                <p className="font-body mb-6">This screen is under construction.</p>
                <p className="text-sm text-ink/60 mb-6">
                  Current Project: <span className="font-bold">{currentProject?.id || 'None'}</span>
                </p>
                <button 
                  onClick={() => setActiveNode('home')}
                  className="btn-primary"
                >
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