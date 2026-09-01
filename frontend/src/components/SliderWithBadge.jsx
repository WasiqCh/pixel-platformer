// frontend/src/components/SliderWithBadge.jsx
import { useState, useEffect } from 'react';

export default function SliderWithBadge({ label, value, onChange, min, max, step, badgeText }) {
  const [localVal, setLocalVal] = useState(value);

  useEffect(() => { setLocalVal(value); }, [value]);

  const handleSlider = (e) => {
    const v = Number(e.target.value);
    setLocalVal(v);
    onChange(v);
  };

  const handleInput = (e) => {
    const v = Number(e.target.value);
    if (!isNaN(v)) {
      setLocalVal(v);
      onChange(v);
    }
  };

  return (
    <div className="mb-4">
      <div className="flex justify-between items-center mb-2">
        <label className="font-heading font-bold text-sm">{label}</label>
        <div className="flex items-center gap-2">
          <input 
            type="number" 
            name={`${label}_input`}
            value={localVal} 
            onChange={handleInput}
            className="w-20 bg-white border-2 border-ink rounded px-2 py-1 font-body text-sm text-right"
          />
          {badgeText && (
            <span className="bg-info/20 border-2 border-info text-info text-xs font-bold px-2 py-1 rounded">
              {badgeText}
            </span>
          )}
        </div>
      </div>
      <input 
        type="range" 
        name={`${label}_slider`}
        min={min} max={max} step={step} 
        value={localVal} 
        onChange={handleSlider}
        className="w-full h-2 bg-panel border-2 border-ink rounded-lg appearance-none cursor-pointer accent-primary"
      />
    </div>
  );
}