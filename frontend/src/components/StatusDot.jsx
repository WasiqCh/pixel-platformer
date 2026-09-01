export default function StatusDot({ status = 'default' }) {
  const colors = {
    approved: 'bg-success',
    stale: 'bg-warn',
    rejected: 'bg-danger',
    default: 'bg-ink/30',
  };
  return (
    <span 
      className={`inline-block w-3 h-3 rounded-full border-2 border-ink ${colors[status] || colors.default}`} 
      title={status} 
    />
  );
}