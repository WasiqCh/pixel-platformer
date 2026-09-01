import { useState } from 'react';
import useStream from '../hooks/useStream';
import Card from './Card';
import BlockButton from './BlockButton';

export default function StreamLab() {
  const { start, stop, streaming } = useStream();
  const [text, setText] = useState('');

  const run = () => {
    setText('');
    start('/api/v1/llm/stream-test', {}, {
      onDelta: d => setText(t => t + d),
    });
  };

  return (
    <Card title="Stream Lab (dev tool — removed when Script Studio lands)">
      <div className="flex gap-2 mb-3">
        <BlockButton onClick={run} disabled={streaming}>
          {streaming ? 'Streaming…' : 'Run stream test'}
        </BlockButton>
        {streaming && (
          <BlockButton variant="danger" onClick={stop}>Stop</BlockButton>
        )}
      </div>
      <pre className="whitespace-pre-wrap font-body text-sm bg-white border-2 border-ink rounded-md p-3 min-h-[120px]">
        {text || 'Output appears here live…'}
      </pre>
    </Card>
  );
}