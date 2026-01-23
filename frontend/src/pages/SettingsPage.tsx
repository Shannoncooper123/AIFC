import { useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Card } from '../components/ui';
import { PageHeader } from '../components/layout';
import {
  ConfigSection,
  ConfigEditor,
  useConfig,
  useReloadConfig,
  useUpdateConfigSection,
  type EditingState,
} from '../features/settings';

export function SettingsPage() {
  const [expandedSection, setExpandedSection] = useState<string | null>(null);
  const [editing, setEditing] = useState<EditingState | null>(null);
  const [editValue, setEditValue] = useState('');

  const { data, isLoading } = useConfig();
  const reloadMutation = useReloadConfig();
  const updateMutation = useUpdateConfigSection(() => {
    setEditing(null);
  });

  const startEditing = (section: string, key: string, currentValue: unknown) => {
    const stringValue =
      typeof currentValue === 'object'
        ? JSON.stringify(currentValue, null, 2)
        : String(currentValue);
    setEditing({ section, key, value: stringValue });
    setEditValue(stringValue);
  };

  const cancelEditing = () => {
    setEditing(null);
    setEditValue('');
  };

  const saveEditing = () => {
    if (!editing) return;

    let parsedValue: unknown;
    try {
      parsedValue = JSON.parse(editValue);
    } catch {
      if (editValue === 'true') parsedValue = true;
      else if (editValue === 'false') parsedValue = false;
      else if (!isNaN(Number(editValue)) && editValue.trim() !== '')
        parsedValue = Number(editValue);
      else parsedValue = editValue;
    }

    updateMutation.mutate({
      section: editing.section,
      data: { [editing.key]: parsedValue },
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <PageHeader title="Settings" />
        <div className="animate-pulse space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-20 bg-slate-800 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        action={
          <button
            onClick={() => reloadMutation.mutate()}
            disabled={reloadMutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg text-white transition-colors"
          >
            <RefreshCw
              size={16}
              className={reloadMutation.isPending ? 'animate-spin' : ''}
            />
            Reload Config
          </button>
        }
      />

      <div className="space-y-4">
        {data?.sections.map((section) => (
          <Card key={section.name}>
            <ConfigSection
              name={section.name}
              isExpanded={expandedSection === section.name}
              onToggle={() =>
                setExpandedSection(
                  expandedSection === section.name ? null : section.name
                )
              }
            >
              <div className="mt-4 space-y-3">
                {Object.entries(section.data).map(([key, value]) => (
                  <ConfigEditor
                    key={key}
                    configKey={key}
                    value={value}
                    isEditing={
                      editing?.section === section.name && editing?.key === key
                    }
                    editValue={editValue}
                    onEditValueChange={setEditValue}
                    onStartEdit={() => startEditing(section.name, key, value)}
                    onSave={saveEditing}
                    onCancel={cancelEditing}
                    isSaving={updateMutation.isPending}
                  />
                ))}
              </div>
            </ConfigSection>
          </Card>
        ))}
      </div>

      <Card>
        <div className="text-center text-slate-400 py-4">
          <p className="text-green-400 mb-2">✓ Hot Reload Enabled</p>
          <p className="text-sm">
            Click on any value to edit. Changes are saved to{' '}
            <code className="bg-slate-700 px-2 py-1 rounded">config.yaml</code> and
            hot-reloaded to running services.
          </p>
        </div>
      </Card>
    </div>
  );
}
