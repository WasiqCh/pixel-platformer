// frontend/src/screens/S04_ScriptStudio.jsx
import { useState } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import SliderWithBadge from '../components/SliderWithBadge';
import useStream from '../hooks/useStream';

export default function S04_ScriptStudio({ currentProject }) {
  const [targetWords, setTargetWords] = useState(1500);
  const [outline, setOutline] = useState(null);
  const [scriptText, setScriptText] = useState('');
  const [loadingOutline, setLoadingOutline] = useState(false);
  const [locked, setLocked] = useState(false);

  const { start, stop, streaming } = useStream();

  const durationMins = Math.round((targetWords / 150) * 10) / 10;
  const currentWordCount = scriptText.trim() ? scriptText.trim().split(/\s+/).length : 0;

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
        <p className="font-body">Go to Home and select a project first.</p>
      </div>
    );
  }

  const generateOutline = async () => {
    setLoadingOutline(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/script/outline`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_words: targetWords })
      });
      const data = await res.json();
      if (data.sections) {
        setOutline(data);
      } else {
        alert('Outline failed: ' + (data.detail || 'Unknown error'));
      }
    } catch (e) {
      alert('Network error: ' + e.message);
    }
    setLoadingOutline(false);
  };

  const streamDraft = () => {
    if (!outline || !outline.sections) {
      alert('Pass 1 first: click Generate Outline.');
      return;
    }
    setScriptText('');
    setLocked(false);
    start(`/api/v1/projects/${currentProject.id}/script/draft`, outline, {
      onDelta: (d) => setScriptText(prev => prev + d),
    });
  };

  const lockScript = async () => {
    if (!scriptText.trim()) return;
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/script/lock`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: scriptText, word_count: currentWordCount })
      });
      const data = await res.json();
      if (data.status === 'locked') {
        setLocked(true);
        alert(`Script locked! ${currentWordCount} words ≈ ${Math.round((data.duration_sec / 60) * 10) / 10} mins. Stage → 'script'.`);
      } else {
        alert('Lock failed: ' + (data.detail || 'Unknown error'));
      }
    } catch (e) {
      alert('Network error: ' + e.message);
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h2 className="font-display text-2xl text-ink">Script Studio</h2>

      <Card
        title="1. Target & Outline"
        actions={
          <BlockButton onClick={generateOutline} disabled={loadingOutline || streaming}>
            {loadingOutline ? 'Structuring...' : 'Generate Outline'}
          </BlockButton>
        }
      >
        <SliderWithBadge
          label="Target Word Count"
          value={targetWords}
          onChange={setTargetWords}
          min={500}
          max={3000}
          step={100}
          badgeText={`~${durationMins} mins`}
        />

        {outline && (
          <div className="mt-4 border-t-2 border-ink/10 pt-4">
            <h4 className="font-heading font-bold mb-2">Outline (Pass 1):</h4>
            <div className="space-y-2">
              {outline.sections.map((s, i) => (
                <div key={i} className="flex justify-between p-2 bg-sky/10 border border-ink/20 rounded text-sm">
                  <span className="font-bold">
                    {s.heading} <span className="text-info text-xs">({s.role})</span>
                  </span>
                  <span className="text-ink/60">{s.target_words} words</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </Card>

      <Card
        title="2. Draft & Edit"
        actions={
          <div className="flex gap-2">
            {streaming && (
              <BlockButton variant="danger" onClick={stop}>Stop</BlockButton>
            )}
            <BlockButton onClick={streamDraft} disabled={!outline || streaming}>
              {streaming ? 'Streaming...' : 'Stream Full Draft'}
            </BlockButton>
          </div>
        }
      >
        <textarea
          name="script_editor"
          value={scriptText}
          onChange={(e) => setScriptText(e.target.value)}
          className="w-full h-96 bg-white border-2 border-ink rounded-md p-4 font-body text-base leading-relaxed focus:outline-none focus:border-info resize-y"
          placeholder="Your script will stream in here... You can also edit it manually!"
        />
        <div className="flex justify-between items-center mt-2 text-sm font-heading">
          <span>Words: {currentWordCount} / {targetWords}</span>
          <span>Duration: {Math.round((currentWordCount / 150) * 10) / 10} mins</span>
        </div>
      </Card>

      {scriptText.trim().length > 100 && !streaming && (
        <Card title="3. Lock & Continue">
          <div className="flex items-center justify-between gap-4">
            <p className="font-body text-sm text-ink/70">
              Locking saves this version, writes 03_script/locked_v1.md, and moves the project stage to 'script'.
            </p>
            <BlockButton onClick={lockScript} disabled={locked}>
              {locked ? '✓ Locked' : '🔒 Lock Script'}
            </BlockButton>
          </div>
        </Card>
      )}
    </div>
  );
}