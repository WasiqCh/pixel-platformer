export default function Card({ title, children, actions, className = '' }) {
  return (
    <div className={`bg-panel border-2 border-ink rounded-md shadow-block p-4 ${className}`}>
      {(title || actions) && (
        <div className="flex justify-between items-center mb-3 border-b-2 border-ink/10 pb-2">
          {title && <h3 className="font-heading text-xl font-bold text-ink">{title}</h3>}
          {actions && <div className="flex gap-2">{actions}</div>}
        </div>
      )}
      <div className="font-body text-ink">{children}</div>
    </div>
  );
}