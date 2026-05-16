import { useState } from 'react';
import { MessageSquare, Database, GitBranch, Search, Activity, Settings, Trash2 } from 'lucide-react';

interface LeftRailProps {
  onClear: () => void;
  onOpenSettings: () => void;
  isClearing?: boolean;
}

type NavItem = {
  icon: typeof MessageSquare;
  id: string;
  title: string;
};

const navItems: NavItem[] = [
  { icon: MessageSquare, id: 'chat', title: 'Chat' },
  { icon: Database, id: 'memory', title: 'Memory' },
  { icon: GitBranch, id: 'graph', title: 'Graph' },
  { icon: Search, id: 'search', title: 'Search' },
  { icon: Activity, id: 'health', title: 'System Health' },
];

export function LeftRail({ onClear, onOpenSettings, isClearing }: LeftRailProps) {
  const [active, setActive] = useState('chat');

  return (
    <div className="w-[48px] h-full bg-base border-r border-subtle flex flex-col items-center py-4 shrink-0 z-20">
      {/* Nav icons */}
      <div className="flex flex-col gap-1 flex-1">
        {navItems.map(({ icon: Icon, id, title }) => (
          <button
            key={id}
            title={title}
            onClick={() => setActive(id)}
            className={`w-9 h-9 flex items-center justify-center rounded transition-colors cursor-pointer ${
              active === id
                ? 'text-accent'
                : 'text-tertiary hover:text-secondary'
            }`}
          >
            <Icon className="w-4 h-4" />
          </button>
        ))}
      </div>

      {/* Bottom actions */}
      <div className="flex flex-col gap-1 mt-auto">
        <button
          title="Settings"
          onClick={onOpenSettings}
          className="w-9 h-9 flex items-center justify-center rounded text-tertiary hover:text-secondary transition-colors cursor-pointer"
        >
          <Settings className="w-4 h-4" />
        </button>
        <button
          title="Purge Memories"
          onClick={onClear}
          disabled={isClearing}
          className="w-9 h-9 flex items-center justify-center rounded text-tertiary hover:text-red-500 transition-colors cursor-pointer disabled:opacity-40"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
