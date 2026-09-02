// frontend/src/screens/S04_ScriptStudio.jsx
import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import StatusDot from '../components/StatusDot';
import SliderWithBadge from '../components/SliderWithBadge';
import useStream from '../hooks/useStream';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 200) || `HTTP ${res.status}` }; }
};

export default function S04_ScriptStudio({ currentProject }) {
  const [targetWords, setTargetWords] = useState(1500);
  const [outline, setOutline] = useState(null);
  const [outlineEditing, setOutlineEditing] = useState(false);
  const [scriptText, setScriptText] = useState('');
  const [scriptSource, setScriptSource] = useState('ai');
  const [versions, setVersions] = useState([]);
  const [loadingOutline, setLoadingOutline] = useState(false);
  const [locked, setLocked] = useState(false);

  const [importText, setImportText] = useState('');
  const [fileName, setFileName] = useState('');
  const [importing, setImporting] = useState(false);

  const [punchHeading, setPunchHeading] = useState('');
  const [punchNote, setPunchNote] = useState('');
  const [punching, setPunching] = useState(false);
  const [punch, setPunch] = useState(null);

  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState(null);

  const { start, stop, streaming } = useStream();

  const refreshVersions = () => {
    if (!currentProject) return;
    fetch(`/api/v1/projects/${currentProject.id}/script/versions`)
      .then(r => r.json()).then(setVersions).catch(() => {});
  };

  useEffect(() => {
    setScriptText(''); setOutline(null); setLocked(false); setOutlineEditing(false);
    setPunch(null); setPunchNote(''); setPunchHeading(''); setCheckResult(null);
    setImportText(''); setFileName(''); setScriptSource('ai'); setVersions([]);
    if (!currentProject) return;
    fetch(`/api/v1/projects/${currentProject.id}/script`)
      .then(r => r.json())
      .then(d => {
        if (d.script) {
          setScriptText(d.script.text || '');
          setLocked(!!d.script.locked);
          setScriptSource(d.script.source || 'ai');
        }
      })
      .catch(() => {});
    fetch(`/api/v1/projects/${currentProject.id}/outline`)
      .then(r => r.json())
      .then(d => { if (d.outline) setOutline(d.outline); })
      .catch(() => {});
    refreshVersions();
  }, [currentProject?.id]);

  const durationMins = Math.round((targetWords / 150) * 10) / 10;
  const currentWordCount = scriptText.trim() ? scriptText.trim().split(/\s+/).length : 0;
  const importWords = importText.trim() ? importText.trim().split(/\s+/).length : 0;
  const outlineTotal = outline ? outline.sections.reduce((a, s) => a + Number(s.target_words || 0), 0) : 0;
  const headings = (scriptText.match(/^## .+$/gm) || []).map(l => l.slice(3).trim());
  const hookWords = scriptText.trim() ? scriptText.trim().split(/\s+/).slice(0, 75).join(' ') : '';

  const getSectionSpan = (text, heading) => {
    const marker = `## ${heading}`;
    const startIdx = text.indexOf(marker);
    if (startIdx === -1) return null;
    const next = text.indexOf('\n## ', startIdx + marker.length);
    return { start: startIdx, end: next === -1 ? text.length : next };
  };

  const scriptSections = headings.map(h => {
    const span = getSectionSpan(scriptText, h);
    const txt = span ? scriptText.slice(span.start, span.end) : '';
    const wc = txt.trim() ? txt.trim().split(/\s+/).length : 0;
    const target = outline ? ((outline.sections.find(s => s.heading === h) || {}).target_words || 0) : 0;
    return { heading: h, wc, target };
  });

  useEffect(() => {
    if (!punchHeading && headings.length) setPunchHeading(headings[0]);
  }, [scriptText]);

  if (!currentProject) {
    return (
      <div className="max-w-3xl mx-auto mt-12 text-center card">
        <h2 className="font-display text-xl mb-4">No Project Selected</h2>
        <p className="font-body">Go to Home and select a project first.</p>
      </div>
    );
  }

  const readFile = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    setFileName(f.name);
    const reader = new FileReader();
    reader.onload = () => setImportText(String(reader.result));
    reader.readAsText(f);
  };

  const importScript = async () => {
    setImporting(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/script/import`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: importText })
      });
      const data = await safeJson(res);
      if (!res.ok) { alert('Import failed: ' + (data.detail || 'Unknown error')); return; }
      setScriptText(data.text); setScriptSource('imported'); setLocked(false); setImportText('');
    } catch (e) { alert('Network error: ' + e.message); }
    setImporting(false);
  };

  const generateOutline = async () => {
    setLoadingOutline(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/script/outline`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_words: targetWords })
      });
      const data = await safeJson(res);
      if (res.ok && data.sections) setOutline(data);
      else alert('Outline failed: ' + (data.detail || 'Unknown error'));
    } catch (e) { alert('Network error: ' + e.message); }
    setLoadingOutline(false);
  };

  const refineOutline = async () => {
    const note = prompt('Refine outline (e.g. "add a betrayal turn", "bigger hook"):');
    if (!note) return;
    setLoadingOutline(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/outline/refine`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instruction: note })
      });
      const data = await safeJson(res);
      if (res.ok) setOutline(data);
      else alert('Refine failed: ' + (data.detail || 'Unknown error'));
    } catch (e) { alert('Network error: ' + e.message); }
    setLoadingOutline(false);
  };

  const saveOutline = async () => {
    const res = await fetch(`/api/v1/projects/${currentProject.id}/outline`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sections: outline.sections })
    });
    if (res.ok) {
      setOutlineEditing(false);
      const d = await (await fetch(`/api/v1/projects/${currentProject.id}/outline`)).json();
      if (d.outline) setOutline(d.outline);
    } else alert('Save failed');
  };

  const rebalance = async () => {
    if (!outline) return;
    const total = outline.sections.reduce((a, s) => a + Number(s.target_words || 0), 0);
    if (!total) return;
    const sections = outline.sections.map(s => ({
      ...s,
      target_words: Math.max(50, Math.round((Number(s.target_words) * targetWords / total) / 10) * 10),
    }));
    const diff = targetWords - sections.reduce((a, s) => a + s.target_words, 0);
    sections[sections.length - 1] = {
      ...sections[sections.length - 1],
      target_words: sections[sections.length - 1].target_words + diff,
    };
    const res = await fetch(`/api/v1/projects/${currentProject.id}/outline`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sections })
    });
    if (res.ok) {
      const d = await (await fetch(`/api/v1/projects/${currentProject.id}/outline`)).json();
      if (d.outline) setOutline(d.outline);
    } else alert('Rebalance failed');
  };

  const updateSection = (i, key, value) => {
    const sections = outline.sections.map((s, idx) =>
      idx === i ? { ...s, [key]: key === 'target_words' ? Number(value) : value } : s);
    setOutline({ ...outline, sections });
  };
  const moveSection = (i, dir) => {
    const j = i + dir;
    if (j < 0 || j >= outline.sections.length) return;
    const sections = [...outline.sections];
    [sections[i], sections[j]] = [sections[j], sections[i]];
    setOutline({ ...outline, sections });
  };
  const removeSection = (i) =>
    setOutline({ ...outline, sections: outline.sections.filter((_, idx) => idx !== i) });
  const addSection = () =>
    setOutline({ ...outline, sections: [...outline.sections,
      { heading: 'New Section', summary: '', target_words: 100, role: 'build' }] });

  const streamDraft = () => {
    if (!outline || !outline.sections) { alert('Pass 1 first: click Generate Outline.'); return; }
    setScriptText(''); setLocked(false); setPunch(null); setCheckResult(null); setScriptSource('ai');
    start(`/api/v1/projects/${currentProject.id}/script/draft`, { sections: outline.sections }, {
      onDelta: (d) => setScriptText(prev => prev + d),
    });
  };

  const loadVersion = async (id) => {
    const res = await fetch(`/api/v1/projects/${currentProject.id}/script/versions/${id}`);
    const data = await safeJson(res);
    if (!res.ok) { alert('Version not found'); return; }
    setScriptText(data.text); setLocked(!!data.locked);
    setScriptSource(data.source || 'ai'); setCheckResult(null); setPunch(null);
  };

  const deleteVersion = async (id) => {
    if (!confirm('Delete this script version? The file mirror stays on disk.')) return;
    await fetch(`/api/v1/projects/${currentProject.id}/script/versions/${id}`, { method: 'DELETE' });
    refreshVersions();
  };

  const runPunchup = async () => {
    if (!punchHeading || !punchNote.trim()) { alert('Pick a section and write a note.'); return; }
    setPunching(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/script/punchup`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_text: scriptText, section_heading: punchHeading, note: punchNote })
      });
      const data = await safeJson(res);
      if (!res.ok) { alert('Punch-up failed: ' + (data.detail || 'Unknown error')); return; }
      const span = getSectionSpan(scriptText, punchHeading);
      if (!span) { alert('Section not found in script text.'); return; }
      setPunch({
        heading: punchHeading,
        oldText: scriptText.slice(span.start, span.end),
        newText: `## ${punchHeading}\n${data.rewritten}`,
      });
    } catch (e) { alert('Network error: ' + e.message); }
    setPunching(false);
  };

  const applyPunch = () => {
    const span = getSectionSpan(scriptText, punch.heading);
    if (!span) { alert('Section not found.'); return; }
    setScriptText(scriptText.slice(0, span.start) + punch.newText + scriptText.slice(span.end));
    setLocked(false); setCheckResult(null); setPunch(null); setPunchNote('');
  };

  const runCheck = async () => {
    setChecking(true);
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/script/check`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_text: scriptText })
      });
      const data = await safeJson(res);
      if (res.ok) setCheckResult(data);
      else alert('Check failed: ' + (data.detail || 'Unknown error'));
    } catch (e) { alert('Network error: ' + e.message); }
    setChecking(false);
  };

  const lockScript = async () => {
    if (!scriptText.trim()) return;
    try {
      const res = await fetch(`/api/v1/projects/${currentProject.id}/script/lock`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: scriptText, word_count: currentWordCount, source: scriptSource })
      });
      const data = await safeJson(res);
      if (res.ok && data.status === 'locked') {
        setLocked(true);
        refreshVersions();
        alert(`Locked as v${data.version}!`);
      } else {
        alert('Lock failed: ' + (data.detail || 'Unknown error'));
      }
    } catch (e) { alert('Network error: ' + e.message); }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h2 className="font-display text-2xl text-ink">Script Studio</h2>

      {!scriptText && !streaming && (
        <Card title="0. Import a Script (optional)">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="font-body text-sm text-ink/70 mb-2">Paste an existing script, or load a .txt / .md file:</p>
              <textarea name="import_text" value={importText} onChange={e => setImportText(e.target.value)} rows={6}
                className="w-full bg-white border-2 border-ink rounded-md p-3 font-body text-base focus:outline-none focus:border-info resize-y"
                placeholder="Paste your full narration script here..." />
              <div className="flex items-center gap-3 mt-3">
                <label className="font-heading font-bold text-sm px-4 py-2 border-2 border-ink rounded-md bg-panel shadow-block cursor-pointer hover:shadow-hover hover:-translate-x-[1px] hover:-translate-y-[1px] transition-all">
                  📂 Choose File
                  <input type="file" accept=".txt,.md,text/plain" onChange={readFile} className="hidden" />
                </label>
                <span className="text-xs font-heading font-bold bg-info/20 border-2 border-info text-info px-2 py-1 rounded">
                  {importWords} words · {Math.round((importWords / 150) * 10) / 10} mins
                </span>
              </div>
              {fileName && <p className="text-xs font-body text-ink/60 mt-2">Loaded: {fileName}</p>}
              <BlockButton onClick={importScript} disabled={importing || importWords < 10} className="mt-3">
                {importing ? 'Importing...' : '📥 Import Script'}
              </BlockButton>
            </div>
            <div className="p-3 border-2 border-ink/30 rounded-md bg-sky/10 font-body text-sm text-ink/80 space-y-2">
              <p className="font-heading font-bold text-ink">Why import?</p>
              <p>Imported scripts get <b>every tool</b>: punch-up, sanity check, duration math, lock & versions.</p>
              <p className="text-xs">Just type <code className="bg-panel px-1 rounded">## Heading</code> in the editor to create sections for the tools below.</p>
            </div>
          </div>
        </Card>
      )}

      <Card title="1. Target & Outline" actions={
        <div className="flex gap-2">
          {outline && !outlineEditing && (
            <>
              <BlockButton variant="secondary" onClick={() => setOutlineEditing(true)}>✏️ Edit</BlockButton>
              <BlockButton variant="secondary" onClick={refineOutline} disabled={loadingOutline}>🤖 Refine</BlockButton>
            </>
          )}
          <BlockButton onClick={generateOutline} disabled={loadingOutline || streaming}>
            {loadingOutline ? 'Structuring...' : outline ? 'Regenerate' : 'Generate Outline'}
          </BlockButton>
        </div>
      }>
        <SliderWithBadge label="Target Word Count" value={targetWords} onChange={setTargetWords}
          min={500} max={3000} step={100} badgeText={`~${durationMins} mins`} />

        {outline && (
          <div className="mt-4 border-t-2 border-ink/10 pt-4">
            <div className="flex justify-between items-center mb-2">
              <h4 className="font-heading font-bold">
                Outline <span className="text-info text-xs">v{outline.version}</span>
              </h4>
              <div className="flex items-center gap-3">
                {outlineTotal !== targetWords && (
                  <button onClick={rebalance} className="text-xs font-bold text-warn hover:underline">
                    ⚖ Rebalance to {targetWords}
                  </button>
                )}
                <span className={`text-xs font-mono ${outlineTotal !== targetWords ? 'text-warn font-bold' : 'text-ink/60'}`}>
                  Σ {outlineTotal} / {targetWords} words
                </span>
              </div>
            </div>
            <div className="space-y-2">
              {outline.sections.map((s, i) => {
                const actual = (scriptSections.find(x => x.heading === s.heading) || {}).wc;
                return outlineEditing ? (
                  <div key={i} className="p-2 bg-sky/10 border border-ink/20 rounded text-sm space-y-1">
                    <div className="flex gap-2">
                      <input name={`sec_heading_${i}`} value={s.heading}
                        onChange={e => updateSection(i, 'heading', e.target.value)}
                        className="flex-1 bg-white border-2 border-ink rounded px-2 py-1 font-bold font-body" />
                      <input name={`sec_words_${i}`} type="number" value={s.target_words}
                        onChange={e => updateSection(i, 'target_words', e.target.value)}
                        className="w-24 bg-white border-2 border-ink rounded px-2 py-1 text-right font-body" />
                    </div>
                    <input name={`sec_summary_${i}`} value={s.summary}
                      onChange={e => updateSection(i, 'summary', e.target.value)}
                      className="w-full bg-white border-2 border-ink rounded px-2 py-1 font-body" placeholder="summary" />
                    <div className="flex gap-2 text-xs font-heading">
                      <button onClick={() => moveSection(i, -1)} className="hover:text-info">⬆ Up</button>
                      <button onClick={() => moveSection(i, 1)} className="hover:text-info">⬇ Down</button>
                      <button onClick={() => removeSection(i)} className="hover:text-danger">🗑 Remove</button>
                      <span className="text-ink/50 ml-auto">{s.role}</span>
                    </div>
                  </div>
                ) : (
                  <div key={i} className="flex justify-between p-2 bg-sky/10 border border-ink/20 rounded text-sm">
                    <span className="font-bold font-body">{s.heading} <span className="text-info text-xs">({s.role})</span></span>
                    <span className="text-ink/60 font-body">
                      {actual !== undefined ? `${actual} / ` : ''}{s.target_words} words
                    </span>
                  </div>
                );
              })}
            </div>

            {scriptSections.length > 0 && (
              <div className="mt-3">
                <p className="text-xs font-bold text-ink/60 mb-1 font-heading">PACING STRIP (green = on budget · amber = over · red = under)</p>
                <div className="flex h-4 border-2 border-ink rounded overflow-hidden">
                  {scriptSections.map((s, i) => {
                    const ratio = s.target ? s.wc / s.target : 1;
                    const color = ratio >= 0.9 && ratio <= 1.1 ? 'bg-success' : ratio > 1.1 ? 'bg-warn' : 'bg-danger';
                    return (
                      <div key={i} title={`${s.heading}: ${s.wc}/${s.target}w`}
                        className={`${color} border-r border-ink/30 last:border-r-0`}
                        style={{ flexGrow: Math.max(s.wc, 1) }} />
                    );
                  })}
                </div>
              </div>
            )}

            {outlineEditing && (
              <div className="flex gap-2 mt-3 justify-between">
                <BlockButton variant="secondary" onClick={addSection}>+ Add Section</BlockButton>
                <div className="flex gap-2">
                  <BlockButton variant="secondary" onClick={() => setOutlineEditing(false)}>Cancel</BlockButton>
                  <BlockButton onClick={saveOutline}>Save Edits</BlockButton>
                </div>
              </div>
            )}
          </div>
        )}
      </Card>

      <Card title="2. Draft & Edit" actions={
        <div className="flex gap-2">
          {streaming && <BlockButton variant="danger" onClick={stop}>Stop</BlockButton>}
          <BlockButton onClick={streamDraft} disabled={!outline || streaming}>
            {streaming ? 'Streaming...' : 'Stream Full Draft'}
          </BlockButton>
        </div>
      }>
        {versions.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-3">
            {versions.map(v => (
              <span key={v.id} className="inline-flex items-center border-2 rounded overflow-hidden">
                <button onClick={() => loadVersion(v.id)}
                  className={`text-xs font-heading font-bold px-2 py-1 hover:bg-sky/20 ${
                    v.locked ? 'border-success text-success' : 'border-ink/40 text-ink/60'}`}>
                  v{v.version} · {v.source} · {v.word_count}w {v.locked ? '🔒' : ''}
                </button>
                <button onClick={() => deleteVersion(v.id)} title="Delete version"
                  className="text-xs px-1 py-1 bg-danger/10 text-danger hover:bg-danger hover:text-white">✕</button>
              </span>
            ))}
          </div>
        )}

        {locked && (
          <p className="text-sm font-bold text-success mb-2 font-body">✓ Locked script loaded — editing it unlocks a new version.</p>
        )}

        {hookWords && (
          <div className="mb-2 p-2 bg-info/10 border-2 border-info/40 rounded text-sm font-body">
            <span className="text-xs font-bold text-info font-heading">HOOK · first 75 words: </span>
            <mark className="bg-warn/40 px-1 rounded">{hookWords}</mark>
          </div>
        )}

        <textarea name="script_editor" value={scriptText}
          onChange={(e) => { setScriptText(e.target.value); setLocked(false); setCheckResult(null); }}
          className="w-full h-96 bg-white border-2 border-ink rounded-md p-4 font-body text-base leading-relaxed focus:outline-none focus:border-info resize-y"
          placeholder="Your script will stream in here... or import one above. Type ## Heading to create sections." />
        <div className="flex justify-between items-center mt-2 text-sm font-heading">
          <span>Words: {currentWordCount} / {targetWords} · source: {scriptSource}</span>
          <span>Duration: {Math.round((currentWordCount / 150) * 10) / 10} mins</span>
        </div>
      </Card>

      {scriptText.trim().length > 100 && !streaming && (
        <Card title="3. Punch-up (Pass 3)">
          {headings.length === 0 ? (
            <p className="font-body text-sm text-ink/70">
              No "## " headings found. Type <code className="bg-panel px-1 rounded">## Heading</code> in the editor to create sections for punch-up.
            </p>
          ) : (
            <div className="space-y-3">
              <select name="punch_section" value={punchHeading} onChange={e => setPunchHeading(e.target.value)}
                className="w-full bg-white border-2 border-ink rounded px-2 py-2 font-heading font-bold">
                {headings.map(h => <option key={h} value={h}>{h}</option>)}
              </select>
              <textarea name="punch_note" value={punchNote} onChange={e => setPunchNote(e.target.value)}
                placeholder="Free-text note: 'make it punchier', 'add a dark joke', 'shorten by a third'..."
                className="w-full h-20 bg-white border-2 border-ink rounded-md p-2 font-body text-sm focus:outline-none focus:border-info resize-none" />
              <BlockButton onClick={runPunchup} disabled={punching}>
                {punching ? 'Rewriting...' : '✨ Punch Up Section'}
              </BlockButton>

              {punch && (
                <div className="border-2 border-warn rounded-md p-3 bg-warn/10">
                  <h4 className="font-heading font-bold mb-2">Diff preview — {punch.heading}</h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-3">
                    <div>
                      <p className="text-xs font-bold text-ink/60 mb-1 font-heading">CURRENT</p>
                      <div className="bg-white border-2 border-ink/30 rounded p-2 text-xs font-body whitespace-pre-wrap max-h-64 overflow-y-auto">{punch.oldText}</div>
                    </div>
                    <div>
                      <p className="text-xs font-bold text-success mb-1 font-heading">REWRITTEN</p>
                      <div className="bg-white border-2 border-success rounded p-2 text-xs font-body whitespace-pre-wrap max-h-64 overflow-y-auto">{punch.newText}</div>
                    </div>
                  </div>
                  <div className="flex gap-2 justify-end">
                    <BlockButton variant="secondary" onClick={() => setPunch(null)}>Discard</BlockButton>
                    <BlockButton onClick={applyPunch}>Apply Rewrite</BlockButton>
                  </div>
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {scriptText.trim().length > 100 && !streaming && (
        <Card title="4. Sanity Check (Pass 4)" actions={
          <BlockButton variant="secondary" onClick={runCheck} disabled={checking}>
            {checking ? 'Auditing...' : '🩺 Run Check'}
          </BlockButton>
        }>
          {!checkResult ? (
            <p className="font-body text-sm text-ink/70">
              One-click audit: name consistency, timeline, tone drift vs kit, repetition, narration hazards, hook strength.
            </p>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="font-heading font-bold text-sm">Hook:</span>
                <span className={`text-xs font-bold px-2 py-1 rounded border-2 font-heading ${
                  checkResult.hook_strength === 'strong' ? 'bg-success/20 border-success text-success' :
                  checkResult.hook_strength === 'weak' ? 'bg-danger/20 border-danger text-danger' :
                  'bg-warn/20 border-warn text-ink'}`}>
                  {checkResult.hook_strength.toUpperCase()}
                </span>
                <span className="font-body text-sm text-ink/80 italic">{checkResult.summary}</span>
              </div>
              {checkResult.issues.length === 0 ? (
                <div className="flex items-center gap-2 text-success font-bold text-sm font-body">
                  <StatusDot status="approved" /> Clean pass — no issues found.
                </div>
              ) : (
                <div className="space-y-2">
                  {checkResult.issues.map((iss, i) => (
                    <div key={i} className={`p-2 border-2 rounded text-sm font-body ${
                      iss.severity === 'major' ? 'border-danger bg-danger/10' : 'border-warn bg-warn/10'}`}>
                      <div className="flex items-center gap-2 mb-1">
                        <span className={`text-xs font-bold uppercase ${iss.severity === 'major' ? 'text-danger' : 'text-ink/70'}`}>
                          {iss.severity}
                        </span>
                        <span className="text-xs bg-panel border border-ink px-2 py-0.5 rounded font-bold font-heading">{iss.type}</span>
                        {iss.location && <span className="text-xs text-ink/60">@ {iss.location}</span>}
                      </div>
                      <p>{iss.note}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>
      )}

      {scriptText.trim().length > 100 && !streaming && (
        <Card title="5. Lock & Continue">
          <div className="flex items-center justify-between gap-4">
            <p className="font-body text-sm text-ink/70">
              Locking saves this version, writes 03_script/locked_vN.md, and moves the project stage to 'script'.
            </p>
            <BlockButton onClick={lockScript}>
              {locked ? '🔒 Lock New Version' : '🔒 Lock Script'}
            </BlockButton>
          </div>
        </Card>
      )}
    </div>
  );
}
