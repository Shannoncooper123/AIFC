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
    <div className="flex items-center justify-between py-2 border-b border-slate-700 last:border-0 gap-4">
      <span className="text-slate-300 shrink-0">{configKey}</span>

      {isEditing ? (
        <div className="flex items-center gap-2 flex-1 justify-end">
          <input
            type="text"
            value={editValue}
            onChange={(e) => onEditValueChange(e.target.value)}
            className="bg-slate-700 text-white px-3 py-1 rounded border border-slate-600 focus:border-blue-500 focus:outline-none font-mono text-sm min-w-[200px]"
            autoFocus
            onKeyDown={handleKeyDown}
          />
          <button
            onClick={onSave}
            disabled={isSaving}
            className="p-1 text-green-400 hover:text-green-300 disabled:opacity-50"
          >
            <Check size={18} />
          </button>
          <button onClick={onCancel} className="p-1 text-red-400 hover:text-red-300">
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
            className="p-1 text-slate-400 hover:text-white opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <Edit2 size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
