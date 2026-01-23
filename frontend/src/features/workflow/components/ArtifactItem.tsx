import { useState } from 'react';
import type { WorkflowArtifact } from '../../../types';

interface ArtifactItemProps {
  artifact: WorkflowArtifact;
}

export function ArtifactItem({ artifact }: ArtifactItemProps) {
  const [showImage, setShowImage] = useState(false);

  return (
    <div className="border-l-2 border-purple-500/50 pl-3 py-1">
      <div
        className="flex items-center gap-2 cursor-pointer hover:bg-slate-800/30 rounded px-2 py-1"
        onClick={() => setShowImage(!showImage)}
      >
        <span className="text-sm">🖼️</span>
        <span className="text-sm text-purple-300">
          {artifact.symbol} · {artifact.interval}
        </span>
        <span className="text-xs text-slate-500 ml-auto">
          {showImage ? '▼' : '▶'}
        </span>
      </div>

      {showImage && (
        <div className="mt-2 ml-6">
          <img
            src={`/api/workflow/artifacts/${artifact.artifact_id}`}
            alt={artifact.artifact_id}
            className="max-w-full rounded border border-slate-700"
          />
        </div>
      )}
    </div>
  );
}
