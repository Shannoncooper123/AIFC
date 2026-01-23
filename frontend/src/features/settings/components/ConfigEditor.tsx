/**
 * 配置项内联编辑组件
 */
import { Edit2, X, Check } from 'lucide-react';

export interface EditingState {
  section: string;
  key: string;
  value: string;
}

interface ConfigEditorProps {
  configKey: string;
  value: unknown;
  isEditing: boolean;
  editValue: string;
  onEditValueChange: (value: string) => void;
  onStartEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  isSaving: boolean;
}

/**
 * 配置项内联编辑组件
 */
export function ConfigEditor({
  configKey,
  value,
  isEditing,
  editValue,
  onEditValueChange,
  onStartEdit,
  onSave,
  onCancel,
  isSaving,
}: ConfigEditorProps) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') onSave();
    if (e.key === 'Escape') onCancel();
  };

  return (
    <div className="group flex items-center justify-between py-2 border-b border-neutral-800 last:border-0 gap-4">
      <span className="text-neutral-300 shrink-0">{configKey}</span>

      {isEditing ? (
        <div className="flex items-center gap-2 flex-1 justify-end">
          <input
            type="text"
            value={editValue}
            onChange={(e) => onEditValueChange(e.target.value)}
            className="bg-neutral-800 text-white px-3 py-1 rounded border border-neutral-700 focus:border-neutral-500 focus:outline-none font-mono text-sm min-w-[200px] transition-all duration-200"
            autoFocus
            onKeyDown={handleKeyDown}
          />
          <button
            onClick={onSave}
            disabled={isSaving}
            className="p-1 text-emerald-500/80 hover:text-emerald-400 disabled:opacity-50 transition-all duration-200"
          >
            <Check size={18} />
          </button>
          <button onClick={onCancel} className="p-1 text-rose-500/80 hover:text-rose-400 transition-all duration-200">
            <X size={18} />
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <span className="text-white font-mono text-sm max-w-[300px] truncate">
            {typeof value === 'object' ? JSON.stringify(value) : String(value)}
          </span>
          <button
            onClick={onStartEdit}
            className="p-1 text-neutral-400 hover:text-white opacity-0 group-hover:opacity-100 transition-all duration-200"
          >
            <Edit2 size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
