import { Search, Settings, Trash2, GitPullRequest } from 'lucide-react';
import { Button } from '../ui/Button';

interface FloatingControlsProps {
  onClear: () => void;
  onOpenSettings: () => void;
  isClearing?: boolean;
}

export function FloatingControls({ onClear, onOpenSettings, isClearing }: FloatingControlsProps) {
  return (
    <div className="absolute left-0 top-1/2 -translate-y-1/2 z-50 group px-2 py-8">
      {/* Invisible trigger area */}
      <div className="flex flex-col gap-2 p-2 bg-surface/80 backdrop-blur-sm border border-subtle rounded-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 shadow-sm translate-x-[-100%] group-hover:translate-x-0">
        <Button variant="ghost" size="icon" className="w-8 h-8 rounded-lg text-tertiary hover:text-primary hover:bg-subtle" title="Search">
          <Search className="w-4 h-4" />
        </Button>
        <Button variant="ghost" size="icon" className="w-8 h-8 rounded-lg text-tertiary hover:text-primary hover:bg-subtle" title="Graph View">
          <GitPullRequest className="w-4 h-4" />
        </Button>
        <Button variant="ghost" size="icon" onClick={onOpenSettings} className="w-8 h-8 rounded-lg text-tertiary hover:text-primary hover:bg-subtle" title="Settings">
          <Settings className="w-4 h-4" />
        </Button>
        <div className="w-full h-px bg-subtle my-1" />
        <Button variant="ghost" size="icon" onClick={onClear} disabled={isClearing} className="w-8 h-8 rounded-lg text-tertiary hover:text-status-error hover:bg-subtle" title="Purge Memories">
          <Trash2 className="w-4 h-4" />
        </Button>
      </div>
    </div>
  );
}
