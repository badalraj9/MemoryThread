// Settings Page

import { useState } from 'react';
import { Settings as SettingsIcon, X, RotateCcw, Search, Download } from 'lucide-react';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';

interface SettingsProps {
  isOpen: boolean;
  onClose: () => void;
  config: {
    autoRecall: boolean;
    topK: number;
    namespace: string;
  };
  onConfigChange: (config: Partial<SettingsProps['config']>) => void;
  onExport: (format: 'md' | 'json') => void;
  onReset: () => void;
}

export function Settings({
  isOpen,
  onClose,
  config,
  onConfigChange,
  onExport,
  onReset,
}: SettingsProps) {
  const [localConfig, setLocalConfig] = useState(config);

  if (!isOpen) return null;

  const handleSave = () => {
    onConfigChange(localConfig);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-[var(--color-bg-surface)] border border-[var(--color-border-subtle)] rounded-lg shadow-lg max-w-md w-full">
        <div className="flex items-center justify-between p-4 border-b border-[var(--color-border-subtle)]">
          <div className="flex items-center gap-2">
            <SettingsIcon className="w-4 h-4 text-[var(--color-accent-primary)]" />
            <h3 className="font-semibold text-[var(--color-text-primary)]">
              Settings
            </h3>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        <div className="p-4 space-y-4">
          <div>
            <label className="text-xs font-medium text-[var(--color-text-secondary)] block mb-2">
              Namespace
            </label>
            <Input
              value={localConfig.namespace}
              onChange={(e) =>
                setLocalConfig({ ...localConfig, namespace: e.target.value })
              }
              placeholder="mt_chat"
            />
          </div>

          <div>
            <label className="text-xs font-medium text-[var(--color-text-secondary)] block mb-2">
              Top-K Memories
            </label>
            <Input
              type="number"
              value={localConfig.topK}
              onChange={(e) =>
                setLocalConfig({ ...localConfig, topK: parseInt(e.target.value) || 8 })
              }
              min={1}
              max={100}
            />
          </div>

          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Search className="w-4 h-4 text-[var(--color-text-tertiary)]" />
              <span className="text-sm text-[var(--color-text-secondary)]">
                Auto-recall on type
              </span>
            </div>
            <button
              onClick={() =>
                setLocalConfig({ ...localConfig, autoRecall: !localConfig.autoRecall })
              }
              className={`w-10 h-5 rounded-full transition-colors ${
                localConfig.autoRecall
                  ? 'bg-[var(--color-accent-primary)]'
                  : 'bg-[var(--color-border-default)]'
              }`}
            >
              <div
                className={`w-4 h-4 rounded-full bg-white transition-transform ${
                  localConfig.autoRecall ? 'translate-x-5' : 'translate-x-0.5'
                }`}
              />
            </button>
          </div>
        </div>

        <div className="p-4 border-t border-[var(--color-border-subtle)] space-y-2">
          <div className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              className="flex-1"
              onClick={() => onExport('md')}
            >
              <Download className="w-3 h-3 mr-1" />
              Markdown
            </Button>
            <Button
              variant="secondary"
              size="sm"
              className="flex-1"
              onClick={() => onExport('json')}
            >
              <Download className="w-3 h-3 mr-1" />
              JSON
            </Button>
          </div>
          <Button
            variant="ghost"
            size="sm"
            className="w-full"
            onClick={onReset}
          >
            <RotateCcw className="w-3 h-3 mr-1" />
            Reset All Data
          </Button>
        </div>

        <div className="flex justify-end gap-2 p-4 border-t border-[var(--color-border-subtle)]">
          <Button variant="ghost" size="sm" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSave}>
            Save
          </Button>
        </div>
      </div>
    </div>
  );
}