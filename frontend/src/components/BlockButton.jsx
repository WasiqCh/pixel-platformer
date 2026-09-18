// frontend/src/components/BlockButton.jsx
import { playSfx } from '../lib/sfx';

export default function BlockButton({ children, variant = 'primary', onClick, className = '', disabled = false }) {
  const base = "font-heading font-bold px-4 py-2 border-2 border-ink rounded-md transition-all active:shadow-none active:translate-x-[4px] active:translate-y-[4px]";
  const variants = {
    primary: "bg-primary text-white shadow-block hover:shadow-hover hover:-translate-x-[1px] hover:-translate-y-[1px]",
    secondary: "bg-panel text-ink shadow-block hover:shadow-hover hover:-translate-x-[1px] hover:-translate-y-[1px]",
    danger: "bg-danger text-white shadow-block hover:shadow-hover hover:-translate-x-[1px] hover:-translate-y-[1px]",
  };

  const handleClick = (e) => {
    if (disabled) return;
    playSfx(variant === 'danger' ? 'back' : 'click');
    if (onClick) onClick(e);
  };

  return (
    <button
      onClick={handleClick}
      disabled={disabled}
      className={`${base} ${variants[variant]} ${className} ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
    >
      {children}
    </button>
  );
}