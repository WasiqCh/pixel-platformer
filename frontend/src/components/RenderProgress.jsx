// frontend/src/components/RenderProgress.jsx
// D5+D10-T03 — plain-words render progress (shared by Beats + My Video).
// Speaks no jargon: "Making your video… 12 of 30 scenes", never "segments"
// or "job". Errors name the scene + the fix, with Resume (POST /render
// resumes the same persisted row where it stopped — existing endpoint only).
// Polls the existing GET .../render/status (persisted row, reload-safe) and
// GET .../render/check for the structured not-ready list on 409.
import { useState, useEffect, useRef } from 'react';
import BlockButton from './BlockButton';

const safeJson = async (res) => {
  const t = await res.text();
  try { return JSON.parse(t); } catch { return { detail: t.slice(0, 300) || `HTTP ${res.status}` }; }
};

const beatOf = (s) => {
  const m = String(s || '').match(/beat\s+(B\d+)/i);
  return m ? m[1].toUpperCase() : '';
};

const shortErr = (s) => String(s || 'unknown hiccup').replace(/^Error:\s*/i, '').slice(0, 140);

// Layman error: name the scene + the fix, always ending at Resume.
function plainRenderError(errorStr) {
  const e = String(errorStr || '');
  const beat = beatOf(e);
  const at = beat ? `scene ${beat.replace(/^B0*/, '')}` : '';
  if (/no scene row|plan scenes first/i.test(e)) return {
    title: beat ? `Stopped at ${at} — its scene isn't planned yet.` : 'Stopped — a scene isn\'t planned yet.',
    fix: 'Go to Beats and press ① Plan scenes, then press Resume.',
  };
  if (/scene not approved/i.test(e)) return {
    title: beat ? `Stopped at ${at} — that scene isn't approved yet.` : 'Stopped — a scene isn\'t approved yet.',
    fix: 'Approve it on the Beats page, then press Resume.',
  };
  if (/scene stale|re-review/i.test(e)) return {
    title: beat ? `Stopped at ${at} — it changed and needs another look.` : 'Stopped — a scene changed.',
    fix: 'Re-approve it on the Beats page, then press Resume.',
  };
  if (/voiceover|WAV|narration|no duration/i.test(e)) return {
    title: beat ? `Stopped at ${at} — it has no narration yet.` : 'Stopped — some narration is missing.',
    fix: 'Press Narrate on the Beats page, then press Resume.',
  };
  if (/preview missing/i.test(e)) return {
    title: beat ? `Stopped at ${at} — its picture couldn't be made.` : 'Stopped — a picture couldn\'t be made.',
    fix: 'Check its assets on the Beats page, then press Resume.',
  };
  if (/ffmpeg not found/i.test(e)) return {
    title: 'Stopped — the video tool is missing.',
    fix: 'Open Setup and press Fix next to FFmpeg, then press Resume.',
  };
  if (/no fresh beats|all stale/i.test(e)) return {
    title: 'Stopped — your beats need a fresh look.',
    fix: 'Go to Beats and re-extract or clear stale flags, then press Render.',
  };
  if (/segment missing|concat blocked|frames dir not empty|final MP4 missing/i.test(e)) return {
    title: beat ? `Stopped at ${at} — the video tool stumbled.` : 'Stopped — the video tool stumbled.',
    fix: 'Just press Resume — it picks up where it stopped.',
  };
  if (beat) return {
    title: `Stopped at ${at} — ${shortErr(e)}`,
    fix: 'Fix it, then press Resume to carry on where it stopped.',
  };
  return {
    title: `Something stopped the video — ${shortErr(e)}`,
    fix: 'Press Resume to try again where it stopped.',
  };
}

// Layman not-ready (409 gate): structured check -> plain fix list.
function plainGate(check) {
  if (!check || typeof check.total_beats !== 'number') return 'Not ready yet — check the Beats page, then try again.';
  if ((check.total_beats || 0) === 0) {
    if ((check.stale_beats || []).length > 0) return 'Not ready yet — your beats changed. Go to Beats and re-extract or clear stale flags, then press Render.';
    return 'Not ready yet — no beats. Go to Beats and press Re-Extract Beats first.';
  }
  const bits = [];
  if ((check.unapproved || []).length > 0) bits.push(`${check.unapproved.length} of ${check.total_beats} scenes need approval`);
  if ((check.stale_scenes || []).length > 0) bits.push(`${check.stale_scenes.length} changed — needs another look`);
  if ((check.missing_audio || []).length > 0) bits.push(`${check.missing_audio.length} need narration`);
  if ((check.stale_beats || []).length > 0) bits.push(`${check.stale_beats.length} beats changed`);
  if (bits.length === 0) return 'Not ready yet — check the Beats page, then try again.';
  return `Not ready yet — ${bits.join(' · ')}. Approve scenes + press Narrate on the Beats page, then press Render.`;
}

export default function RenderProgress({ currentProject, onRunningChange }) {
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [notice, setNotice] = useState('');
  const pollRef = useRef(null);

  const pid = currentProject?.id;

  const load = async () => {
    if (!pid) { setLoading(false); return; }
    try {
      const res = await fetch(`/api/v1/projects/${pid}/render/status`);
      const data = await safeJson(res);
      if (res.ok) setJob(data);
    } catch { /* next poll retries */ }
    setLoading(false);
  };

  useEffect(() => {
    setJob(null); setNotice(''); setLoading(true);
    load();
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  useEffect(() => {
    if (onRunningChange) onRunningChange(!!job?.running);
  }, [job?.running, onRunningChange]);

  useEffect(() => {
    if (!pid) return;
    if (job?.running && !pollRef.current) {
      pollRef.current = setInterval(async () => {
        try {
          const r = await fetch(`/api/v1/projects/${pid}/render/status`);
          const s = await safeJson(r);
          if (!r.ok) return;
          setJob(s);
          if (!s.running && pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
        } catch { /* keep polling */ }
      }, 2000);
    }
    if (!job?.running && pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    return () => { if (!job?.running && pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [job?.running, pid]);

  const start = async () => {
    if (busy || !pid) return;
    setBusy('start'); setNotice('');
    try {
      const res = await fetch(`/api/v1/projects/${pid}/render`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) {
        if (res.status === 409) {
          try {
            const chk = await (await fetch(`/api/v1/projects/${pid}/render/check`)).json();
            setNotice(plainGate(chk));
          } catch { setNotice(plainGate(null)); }
        } else {
          setNotice(`Couldn't start — ${shortErr(data.detail || data.message)}. Try again.`);
        }
        return;
      }
      setJob(data);
      if (!data.running && data.status !== 'done') load();
      else if (data.running && !pollRef.current) {
        pollRef.current = setInterval(async () => {
          try {
            const r = await fetch(`/api/v1/projects/${pid}/render/status`);
            const s = await safeJson(r);
            if (!r.ok) return;
            setJob(s);
            if (!s.running && pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
          } catch { /* keep polling */ }
        }, 2000);
      }
    } catch (e) { setNotice('Network hiccup — try again. (' + e.message + ')'); }
    setBusy(null);
  };

  const cancel = async () => {
    if (busy || !pid) return;
    setBusy('cancel');
    try {
      const res = await fetch(`/api/v1/projects/${pid}/render/cancel`, { method: 'POST' });
      const data = await safeJson(res);
      if (!res.ok) { setNotice(`Couldn't pause — ${shortErr(data.detail)}. Try again.`); return; }
      setJob(data);
    } catch (e) { setNotice('Network hiccup — try again. (' + e.message + ')'); }
    setBusy(null);
  };

  if (!pid) return <p className="font-body text-sm text-ink/70">Pick a project first.</p>;
  if (loading && !job) return <p className="font-body text-sm text-ink/70">Checking your video…</p>;

  const total = job?.total_segments || 0;
  const cur = job?.current_segment || 0;
  const pct = total > 0 ? Math.round((cur / total) * 100) : 0;
  const fileName = String(job?.output_path || '').split('/').pop();
  const resumable = job && (job.status === 'cancelled' || job.status === 'error');

  return (
    <div className="space-y-2">
      {!job?.has_job && (
        <p className="font-body text-sm text-ink/70">No video yet — when your scenes are approved, press Render and it will appear here.</p>
      )}
      {job?.has_job && job.running && total > 0 && (
        <div>
          <p className="font-heading text-sm font-bold">Making your video… {cur} of {total} scenes</p>
          <div className="mt-1 w-full h-3 border-2 border-ink rounded bg-white overflow-hidden">
            <div className="h-full bg-success" style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-1 text-xs font-mono text-ink/60">{pct}% · scene {Math.min(cur + 1, total)} of {total} now</p>
        </div>
      )}
      {job?.has_job && job.status === 'done' && (
        <p className="font-heading text-sm font-bold text-success">Your video is ready! 🎉 All {total} scenes are in.{fileName ? ` (${fileName})` : ''}</p>
      )}
      {job?.has_job && job.status === 'cancelled' && (
        <p className="font-heading text-sm font-bold">Paused at scene {cur} of {total} — press Resume to carry on where it stopped.</p>
      )}
      {job?.has_job && job.status === 'error' && (() => {
        const lay = plainRenderError(job.error);
        return (
          <div className="p-2 border-2 border-danger bg-danger/10 rounded">
            <p className="font-heading text-sm font-bold">{lay.title}</p>
            <p className="font-body text-xs text-ink/80 mt-1">{lay.fix}</p>
          </div>
        );
      })()}
      {notice && <p className="font-body text-xs text-ink/80">{notice}</p>}
      <div className="flex gap-2 flex-wrap">
        {(!job?.has_job || job.status === 'done') && (
          <BlockButton onClick={start} disabled={busy !== null}>
            {busy === 'start' ? 'Starting…' : job?.status === 'done' ? '🎬 Make another version (keeps this one)' : '🎬 Render my video'}
          </BlockButton>
        )}
        {resumable && (
          <BlockButton onClick={start} disabled={busy !== null}>
            {busy === 'start' ? 'Resuming…' : '▶ Resume where it stopped'}
          </BlockButton>
        )}
        {job?.running && (
          <BlockButton variant="secondary" onClick={cancel} disabled={busy !== null}>
            {busy === 'cancel' ? 'Pausing…' : '⏸ Pause'}
          </BlockButton>
        )}
      </div>
    </div>
  );
}
