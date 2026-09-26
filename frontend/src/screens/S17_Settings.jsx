import { useState, useEffect } from 'react';
import Card from '../components/Card';
import BlockButton from '../components/BlockButton';
import StatusDot from '../components/StatusDot';
import StreamLab from '../components/StreamLab';
import { playSfx, setSfxEnabled } from '../lib/sfx';

export default function S17_Settings() {
  const [settings, setSettings] = useState({
    endpoint: '',
    api_key: '',
    use_single_model: false,
    models: { light: '', medium: '', high: '' },
    sfx: false
  });
  
  const [showKey, setShowKey] = useState(false);
  const [status, setStatus] = useState('idle'); // idle, saving, saved, testing, test_success, test_error
  const [testMsg, setTestMsg] = useState('');

  // SCENES-MP4 D4-T02: provider switch (Gemini default; Kokoro offered only
  // when its deps import cleanly). Voice names differ per provider — stored
  // per-provider, never mixed.
  const [voiceCfg, setVoiceCfg] = useState({ voice: 'Kore', enabled: true, provider: 'gemini', kokoro_voice: 'af_heart' });
  const [kokoroStatus, setKokoroStatus] = useState({ available: false, reason: 'checking…', voices: [] });
  const [voiceMsg, setVoiceMsg] = useState('');

  // Load current settings on mount
  useEffect(() => {
    fetch('/api/v1/settings')
      .then(res => res.json())
      .then(data => setSettings(data))
      .catch(err => console.error("Failed to load settings", err));
    fetch('/api/v1/settings/voice')
      .then(res => res.json())
      .then(data => setVoiceCfg(v => ({ ...v, ...data })))
      .catch(err => console.error("Failed to load voice settings", err));
    fetch('/api/v1/settings/voice/kokoro-status')
      .then(res => res.json())
      .then(data => setKokoroStatus(data))
      .catch(err => console.error("Failed to probe kokoro", err));
  }, []);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    if (name === 'sfx') {
      // Apply immediately and play a blip so the toggle is obviously working.
      setSfxEnabled(checked);
      if (checked) playSfx('coin');
    }
    if (name.startsWith('model_')) {
      const tier = name.split('_')[1];
      setSettings(prev => ({
        ...prev,
        models: { ...prev.models, [tier]: value }
      }));
    } else {
      setSettings(prev => ({
        ...prev,
        [name]: type === 'checkbox' ? checked : value
      }));
    }
  };

  const handleSave = async () => {
    setStatus('saving');
    try {
      const res = await fetch('/api/v1/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      if (res.ok) {
        setStatus('saved');
        playSfx('save');
        setTimeout(() => setStatus('idle'), 2000);
      } else {
        setStatus('idle');
        playSfx('error');
        alert("Failed to save settings");
      }
    } catch (err) {
      setStatus('idle');
      playSfx('error');
      alert("Error saving settings");
    }
  };

  const saveVoice = async () => {
    setVoiceMsg('saving…');
    try {
      const res = await fetch('/api/v1/settings/voice', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(voiceCfg)
      });
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setVoiceMsg('✓ voice settings saved');
        playSfx('save');
      } else {
        setVoiceMsg('Save failed: ' + (data.detail || 'Unknown error'));
        playSfx('error');
      }
    } catch (err) {
      setVoiceMsg('Network error: ' + err.message);
      playSfx('error');
    }
  };

  const handleTest = async () => {
    setStatus('testing');
    setTestMsg('');
    try {
      const res = await fetch('/api/v1/settings/test-connection', { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        setStatus('test_success');
        setTestMsg(`Success! Connected to ${data.model}`);
        playSfx('success');
      } else {
        setStatus('test_error');
        setTestMsg(`Failed: ${data.error}`);
        playSfx('error');
      }
    } catch (err) {
      setStatus('test_error');
      setTestMsg("Network error. Is the backend running?");
      playSfx('error');
    }
  };

  const inputClass = "w-full bg-white border-2 border-ink rounded-md px-3 py-2 font-body text-ink focus:outline-none focus:border-info shadow-sm";
  const labelClass = "block font-heading font-bold text-sm mb-1 text-ink";

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <h2 className="font-display text-2xl text-ink">Settings</h2>

      <Card title="LLM Configuration">
        <div className="space-y-4">
          <div>
            <label className={labelClass}>Endpoint URL</label>
            <input 
              type="text" 
              name="endpoint" 
              value={settings.endpoint} 
              onChange={handleChange} 
              className={inputClass}
              placeholder="https://api.openai.com/v1"
            />
          </div>

          <div>
            <label className={labelClass}>API Key</label>
            <div className="flex gap-2">
              <input 
                type={showKey ? "text" : "password"} 
                name="api_key" 
                value={settings.api_key} 
                onChange={handleChange} 
                className={inputClass}
                placeholder="sk-..."
              />
              <BlockButton variant="secondary" onClick={() => setShowKey(!showKey)}>
                {showKey ? 'Hide' : 'Show'}
              </BlockButton>
            </div>
          </div>

          <div className="flex items-center gap-2 p-3 bg-sky/10 border-2 border-ink rounded-md">
            <input 
              type="checkbox" 
              id="use_single" 
              name="use_single_model" 
              checked={settings.use_single_model} 
              onChange={handleChange} 
              className="w-5 h-5 accent-primary"
            />
            <label htmlFor="use_single" className="font-heading font-bold cursor-pointer">
              Use one model for everything (High tier)
            </label>
          </div>

          <div className={`grid grid-cols-1 md:grid-cols-3 gap-4 ${settings.use_single_model ? 'opacity-50 pointer-events-none' : ''}`}>
            <div>
              <label className={labelClass}>Light (Drafts)</label>
              <input type="text" name="model_light" value={settings.models.light} onChange={handleChange} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>Medium (Analysis)</label>
              <input type="text" name="model_medium" value={settings.models.medium} onChange={handleChange} className={inputClass} />
            </div>
            <div>
              <label className={labelClass}>High (Finals)</label>
              <input type="text" name="model_high" value={settings.models.high} onChange={handleChange} className={inputClass} />
            </div>
          </div>
        </div>
      </Card>

      <Card title="Preferences">
         <div className="flex items-center gap-2">
            <input 
              type="checkbox" 
              id="sfx" 
              name="sfx" 
              checked={settings.sfx} 
              onChange={handleChange} 
              className="w-5 h-5 accent-primary"
            />
            <label htmlFor="sfx" className="font-heading font-bold cursor-pointer">
              Enable 8-bit Sound Effects
            </label>
          </div>
          <p className="mt-2 text-xs text-ink/60 font-body">
            Blips are generated live in your browser (Web Audio), so there are no sound
            files to download. Enable it to hear a preview; buttons and navigation will
            then click.
          </p>
      </Card>

      <Card title="Voiceover (Narration) — provider + per-provider voice">
        <div className="space-y-4">
          <div className="flex flex-col gap-2">
            <label className="flex items-center gap-2 font-heading font-bold cursor-pointer">
              <input
                type="radio"
                name="voice_provider"
                value="gemini"
                checked={(voiceCfg.provider || 'gemini') === 'gemini'}
                onChange={() => setVoiceCfg(v => ({ ...v, provider: 'gemini' }))}
                className="w-5 h-5 accent-primary"
              />
              Gemini TTS (cloud, default)
            </label>
            <label className={`flex items-center gap-2 font-heading font-bold ${kokoroStatus.available ? 'cursor-pointer' : 'opacity-50 cursor-not-allowed'}`}>
              <input
                type="radio"
                name="voice_provider"
                value="kokoro"
                checked={(voiceCfg.provider || 'gemini') === 'kokoro'}
                disabled={!kokoroStatus.available}
                onChange={() => setVoiceCfg(v => ({ ...v, provider: 'kokoro' }))}
                className="w-5 h-5 accent-primary"
              />
              Kokoro (local, free)
            </label>
            {!kokoroStatus.available && (
              <p className="text-xs font-body text-danger">
                Kokoro unavailable: {kokoroStatus.reason || 'deps missing'}
              </p>
            )}
            {kokoroStatus.available && (
              <p className="text-xs font-body text-ink/60">
                Kokoro ready — {kokoroStatus.voices?.length || 0} voices, weights present.
              </p>
            )}
          </div>

          <div>
            <label className={labelClass}>Gemini voice (cloud)</label>
            <input
              type="text"
              value={voiceCfg.voice || 'Kore'}
              onChange={e => setVoiceCfg(v => ({ ...v, voice: e.target.value }))}
              className={inputClass}
              placeholder="Kore"
            />
          </div>

          <div>
            <label className={labelClass}>Kokoro voice (local)</label>
            {kokoroStatus.available && kokoroStatus.voices?.length > 0 ? (
              <select
                value={voiceCfg.kokoro_voice || 'af_heart'}
                onChange={e => setVoiceCfg(v => ({ ...v, kokoro_voice: e.target.value }))}
                className={inputClass}
              >
                {kokoroStatus.voices.map(vn => (
                  <option key={vn} value={vn}>{vn}</option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                value={voiceCfg.kokoro_voice || 'af_heart'}
                onChange={e => setVoiceCfg(v => ({ ...v, kokoro_voice: e.target.value }))}
                className={inputClass}
                placeholder="af_heart"
                disabled={!kokoroStatus.available}
              />
            )}
          </div>

          <div className="flex items-center gap-3">
            <BlockButton variant="secondary" onClick={saveVoice}>💾 Save voice settings</BlockButton>
            {voiceMsg && <span className="text-xs font-heading font-bold">{voiceMsg}</span>}
          </div>
          <p className="text-xs text-ink/60 font-body">
            Same per-beat WAVs either way (24kHz mono 16-bit + measured durations) —
            the render gate and MP4 mux treat both providers identically.
          </p>
        </div>
      </Card>

      <StreamLab />

      <div className="flex items-center justify-between gap-4">
        <div className="flex gap-3">
          <BlockButton onClick={handleSave} disabled={status === 'saving'}>
            {status === 'saving' ? 'Saving...' : status === 'saved' ? '✓ Saved!' : 'Save Settings'}
          </BlockButton>
          <BlockButton variant="secondary" onClick={handleTest} disabled={!settings.api_key || status === 'testing'}>
            {status === 'testing' ? 'Testing...' : 'Test Connection'}
          </BlockButton>
        </div>

        {(status === 'test_success' || status === 'test_error') && (
          <div className={`flex items-center gap-2 font-body text-sm font-bold ${
            status === 'test_success' ? 'text-[#1E7A38] pixel-outline' : 'text-danger'
          }`}>
            <StatusDot status={status === 'test_success' ? 'approved' : 'rejected'} />
            {testMsg}
          </div>
        )}
      </div>
    </div>
  );
}