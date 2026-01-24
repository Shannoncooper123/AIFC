import { useState, useCallback } from 'react';
import { Image, X, ZoomIn } from 'lucide-react';
import type { WorkflowArtifact } from '../../../types';
import { formatTime } from '../../../utils';

interface ArtifactsGalleryProps {
  artifacts: WorkflowArtifact[];
  runId: string;
}

interface LightboxState {
  isOpen: boolean;
  artifact: WorkflowArtifact | null;
}

function ArtifactCard({
  artifact,
  onExpand,
}: {
  artifact: WorkflowArtifact;
  onExpand: (artifact: WorkflowArtifact) => void;
}) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  const imageUrl = `/api/workflow/artifacts/${artifact.artifact_id}`;

  return (
    <div className="group relative rounded-lg overflow-hidden bg-[#1a1a1a] border border-neutral-800 hover:border-neutral-600 transition-all duration-200">
      <div className="aspect-video relative bg-neutral-900">
        {!loaded && !error && (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-8 h-8 border-2 border-neutral-700 border-t-neutral-400 rounded-full animate-spin" />
          </div>
        )}
        {error ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-neutral-500 gap-2">
            <Image size={32} className="opacity-50" />
            <span className="text-xs">加载失败</span>
          </div>
        ) : (
          <img
            src={imageUrl}
            alt={`${artifact.symbol || 'Unknown'} ${artifact.interval || ''}`}
            className={`w-full h-full object-cover transition-opacity duration-300 ${
              loaded ? 'opacity-100' : 'opacity-0'
            }`}
            onLoad={() => setLoaded(true)}
            onError={() => setError(true)}
          />
        )}

        <div
          className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity duration-200 flex items-center justify-center cursor-pointer"
          onClick={() => onExpand(artifact)}
        >
          <ZoomIn size={32} className="text-white" />
        </div>
      </div>

      <div className="p-3 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          {artifact.symbol && (
            <span className="px-2 py-0.5 text-xs font-medium rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
              {artifact.symbol}
            </span>
          )}
          {artifact.interval && (
            <span className="px-2 py-0.5 text-xs font-medium rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
              {artifact.interval}
            </span>
          )}
        </div>

        {artifact.created_at && (
          <div className="text-xs text-neutral-500 truncate">
            {formatTime(artifact.created_at)}
          </div>
        )}
      </div>
    </div>
  );
}

function Lightbox({
  artifact,
  onClose,
}: {
  artifact: WorkflowArtifact;
  onClose: () => void;
}) {
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState(false);

  const imageUrl = `/api/workflow/artifacts/${artifact.artifact_id}`;

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) {
        onClose();
      }
    },
    [onClose]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    },
    [onClose]
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm"
      onClick={handleBackdropClick}
      onKeyDown={handleKeyDown}
      tabIndex={0}
      role="dialog"
      aria-modal="true"
    >
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2 rounded-full bg-neutral-800/80 hover:bg-neutral-700 text-white transition-colors duration-200 z-10"
        aria-label="Close"
      >
        <X size={24} />
      </button>

      <div className="max-w-[90vw] max-h-[90vh] relative">
        <div className="absolute top-4 left-4 flex items-center gap-2 z-10">
          {artifact.symbol && (
            <span className="px-3 py-1 text-sm font-medium rounded bg-purple-500/30 text-purple-200 border border-purple-500/40 backdrop-blur-sm">
              {artifact.symbol}
            </span>
          )}
          {artifact.interval && (
            <span className="px-3 py-1 text-sm font-medium rounded bg-blue-500/30 text-blue-200 border border-blue-500/40 backdrop-blur-sm">
              {artifact.interval}
            </span>
          )}
        </div>

        {!loaded && !error && (
          <div className="flex items-center justify-center w-96 h-64">
            <div className="w-12 h-12 border-3 border-neutral-700 border-t-neutral-400 rounded-full animate-spin" />
          </div>
        )}

        {error ? (
          <div className="flex flex-col items-center justify-center w-96 h-64 text-neutral-400 gap-3">
            <Image size={48} className="opacity-50" />
            <span>图像加载失败</span>
          </div>
        ) : (
          <img
            src={imageUrl}
            alt={`${artifact.symbol || 'Unknown'} ${artifact.interval || ''}`}
            className={`max-w-[90vw] max-h-[90vh] object-contain rounded-lg shadow-2xl transition-opacity duration-300 ${
              loaded ? 'opacity-100' : 'opacity-0'
            }`}
            onLoad={() => setLoaded(true)}
            onError={() => setError(true)}
          />
        )}

        {artifact.created_at && loaded && (
          <div className="absolute bottom-4 left-4 text-sm text-neutral-400 bg-black/60 px-3 py-1 rounded backdrop-blur-sm">
            {formatTime(artifact.created_at)}
          </div>
        )}
      </div>
    </div>
  );
}

export function ArtifactsGallery({ artifacts, runId }: ArtifactsGalleryProps) {
  const [lightbox, setLightbox] = useState<LightboxState>({
    isOpen: false,
    artifact: null,
  });

  const handleExpand = useCallback((artifact: WorkflowArtifact) => {
    setLightbox({ isOpen: true, artifact });
  }, []);

  const handleClose = useCallback(() => {
    setLightbox({ isOpen: false, artifact: null });
  }, []);

  if (artifacts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-neutral-500 gap-4">
        <Image size={48} className="opacity-30" />
        <div className="text-center">
          <p className="text-sm font-medium">暂无图像</p>
          <p className="text-xs text-neutral-600 mt-1">
            运行 ID: {runId}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        {artifacts.map((artifact) => (
          <ArtifactCard
            key={artifact.artifact_id}
            artifact={artifact}
            onExpand={handleExpand}
          />
        ))}
      </div>

      {lightbox.isOpen && lightbox.artifact && (
        <Lightbox artifact={lightbox.artifact} onClose={handleClose} />
      )}
    </div>
  );
}
