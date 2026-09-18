import { useState, useEffect, useCallback } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import { playSfx } from '../lib/sfx';

// Prompt library + run inspector.
// Left: the 18 recipes that drive every AI call.
// Right: the recipe text (editable, versioned) and the recent runs of it.

const TIER_STYLE = {
  high: 'bg-primary/15 text-primary border-primary/40',
  medium: 'bg-warn/20 text-ink border-warn/50',
  light: 'bg-sky/40 text-ink border-ink/30',
};

function TierBadge({ tier, temp, stream }) {
  return (
    <span className={`text-xs font-heading font-bold px-2 py-0.5 rounded border ${TIER_STYLE[tier] || TIER_STYLE.light}`}>
      {tier}{typeof temp === 'number' ? ` · ${temp}` : ''}{stream ? ' · stream' : ''}
    </span>
  );
}

export default function S18_Prompts() {
  const [recipes, setRecipes] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [content, setContent] = useState('');
  const [version, setVersion] = useState(null);
  const [dirty, setDirty] = useState(false);

  const [runs, setRuns] = useState([]);
  const [openRun, setOpenRun] = useState(null);
  const [runDetail, setRunDetail] = useState(null);
  const [stats, setStats] = useState(null);

  const [status, setStatus] = useState('idle'); // idle | loading | saving | saved | error
  const [msg, setMsg] = useState('');

  const loadRecipes = useCallback(() => {
    fetch('/api/v1/recipes')
      .then(r => r.json())
      .then(data => {
        setRecipes(Array.isArray(data) ? data : []);
        if (!selected && data.length) setSelected(data[0].job);
      })
      .catch(() => setMsg('Could not load recipes. Is the backend running?'));
  }, [selected]);

  useEffect(() => { loadRecipes(); }, []);

  useEffect(() => {
    fetch('/api/v1/runs/stats/summary')
      .then(r => r.json()).then(setStats).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selected) return;
    setStatus('loading');
    fetch(`/api/v1/recipes/${selected}`)
      .then(r => r.json())
      .then(d => {
        setDetail(d);
        setContent(d.content);
        setVersion(d.version);
        setDirty(false);
        setStatus('idle');
      })
      .catch(() => { setStatus('error'); setMsg('Could not load this recipe.'); });
  }, [selected]);

  const loadRuns = useCallback(() => {
    const url = selected ? `/api/v1/runs?limit=25&job_type=${encodeURIComponent(selected)}` : '/api/v1/runs?limit=25';
    fetch(url).then(r => r.json()).then(d => setRuns(Array.isArray(d) ? d : [])).catch(() => setRuns([]));
  }, [selected]);

  useEffect(() => { loadRuns(); }, [loadRuns]);

  const save = async () => {
    setStatus('saving');
    try {
      const res = await fetch(`/api/v1/recipes/${selected}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      });
      const data = await res.json();
      if (!res.ok) { setStatus('error'); setMsg(data.detail || 'Save failed'); playSfx('error'); return; }
      setStatus('saved');
      playSfx('save');
      if (data.status === 'saved') {
        setMsg(`Saved as v${data.version} (previous was v${data.previous_version})`);
        setVersion(data.version);
        setDirty(false);
        loadRecipes();
        loadRuns();
      } else {
        setMsg('No changes to save.');
      }
      setTimeout(() => setStatus('idle'), 2500);
    } catch {
      setStatus('error'); setMsg('Error saving recipe.'); playSfx('error');
    }
  };

  const selectVersion = (v) => {
    fetch(`/api/v1/recipes/${selected}?version=${v}`)
      .then(r => r.json())
      .then(d => { setContent(d.content); setVersion(d.version); setDirty(true); })
      .catch(() => {});
  };

  const openRunDetail = (id) => {
    if (openRun === id) { setOpenRun(null); setRunDetail(null); return; }
    setRunDetail(null);
    setOpenRun(id);
    fetch(`/api/v1/runs/${id}`).then(r => r.json()).then(setRunDetail).catch(() => {});
  };

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-2xl text-ink">Prompts &amp; runs</h2>
        {stats?.total && (
          <p className="font-body text-sm text-ink/60">
            {stats.total.n} runs · {stats.total.bad ?? 0} failed · {stats.total.esc ?? 0} escalated ·{' '}
            {Math.round((stats.total.tok ?? 0) / 1000)}k tokens
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <div className="lg:col-span-2">
          <Card title="Recipes">
            <div className="flex flex-col gap-1 max-h-[70vh] overflow-y-auto">
              {recipes.map(r => (
                <button
                  key={r.job}
                  onClick={() => { playSfx('pop'); setSelected(r.job); setOpenRun(null); setRunDetail(null); }}
                  className={`flex items-center justify-between gap-2 p-2 rounded border-2 text-left transition-all ${
                    selected === r.job ? 'bg-sky/30 border-ink' : 'border-transparent hover:bg-sky/10'
                  }`}
                >
                  <span className="font-mono text-sm text-ink truncate">
                    {r.job}
                    {!r.has_recipe && <span className="text-danger"> (missing)</span>}
                  </span>
                  <TierBadge tier={r.tier} temp={r.temperature} stream={r.stream} />
                </button>
              ))}
            </div>
          </Card>
        </div>

        <div className="lg:col-span-3 space-y-6">
          <Card
            title={detail ? `${selected} — v${version}` : 'Recipe'}
            actions={
              <div className="flex items-center gap-2">
                {detail?.versions?.length > 1 && (
                  <select
                    value={version ?? ''}
                    onChange={e => selectVersion(Number(e.target.value))}
                    className="bg-white border-2 border-ink rounded-md px-2 py-1 font-body text-sm"
                  >
                    {detail.versions.map(v => <option key={v} value={v}>v{v}</option>)}
                  </select>
                )}
                <BlockButton onClick={save} disabled={status === 'saving' || !dirty}>
                  {status === 'saving' ? 'Saving…' : status === 'saved' ? '✓ Saved' : 'Save as new version'}
                </BlockButton>
              </div>
            }
          >
            <textarea
              value={content}
              onChange={e => { setContent(e.target.value); setDirty(true); }}
              rows={16}
              spellCheck={false}
              className="w-full bg-white border-2 border-ink rounded-md px-3 py-2 font-mono text-xs text-ink focus:outline-none focus:border-info"
            />
            <div className="flex items-center justify-between mt-2">
              <p className="text-xs text-ink/60">
                {dirty ? 'Unsaved changes — saving creates a new version, old ones are kept.' : 'No changes.'}
              </p>
              {msg && <p className="text-xs font-heading text-primary">{msg}</p>}
            </div>
          </Card>

          <Card title={`Recent runs${selected ? ` — ${selected}` : ''}`}>
            {runs.length === 0 && <p className="text-sm text-ink/60">No runs recorded yet.</p>}
            <div className="flex flex-col gap-1">
              {runs.map(run => (
                <div key={run.id} className="border-2 border-ink/10 rounded-md">
                  <button
                    onClick={() => openRunDetail(run.id)}
                    className="w-full flex items-center justify-between gap-2 p-2 text-left hover:bg-sky/10"
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <span className={`w-2.5 h-2.5 rounded-full ${run.ok ? 'bg-success' : 'bg-danger'}`} />
                      <span className="font-mono text-xs text-ink/70">#{run.id}</span>
                      <span className="font-mono text-xs text-ink truncate">{run.model}</span>
                      {run.escalated && (
                        <span className="text-xs font-heading font-bold px-1.5 py-0.5 rounded bg-warn/25 border border-warn/50">
                          escalated
                        </span>
                      )}
                    </span>
                    <span className="font-mono text-xs text-ink/60 shrink-0">
                      {run.duration_ms != null ? `${(run.duration_ms / 1000).toFixed(1)}s` : '—'}
                      {' · '}
                      {(run.tokens_in ?? 0) + (run.tokens_out ?? 0)} tok
                    </span>
                  </button>
                  {openRun === run.id && runDetail && (
                    <div className="p-3 border-t-2 border-ink/10 bg-white space-y-2">
                      {runDetail.error && (
                        <div>
                          <p className="font-heading text-xs font-bold text-danger">Validation error</p>
                          <pre className="text-xs whitespace-pre-wrap font-mono text-danger/90">{runDetail.error}</pre>
                        </div>
                      )}
                      <div>
                        <p className="font-heading text-xs font-bold text-ink/70">Raw model output</p>
                        <pre className="text-xs whitespace-pre-wrap font-mono max-h-48 overflow-y-auto text-ink/80">
                          {runDetail.raw_output}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
