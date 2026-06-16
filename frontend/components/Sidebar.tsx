import type { ElementType } from 'react';
import { Bookmark, Briefcase, CheckCircle2, ChevronRight, Clock, HelpCircle, MessageCircle, Sparkles, Store, Zap } from 'lucide-react';

type MenuItem = {
  label: string;
  iconName: string;
};

const iconMap: Record<string, ElementType> = {
  Sparkles,
  MessageCircle,
  Store,
  Briefcase,
  HelpCircle,
  CheckCircle2,
  Zap,
  Clock,
  Bookmark,
  ChevronRight,
};

export function Sidebar({ menuItems }: { menuItems: MenuItem[] }) {
  return (
    <aside className="hidden lg:flex lg:flex-col rounded-[32px] border border-white/80 bg-panel p-6 shadow-soft">
      <div className="mb-8 flex items-center gap-3">
        <div className="flex h-12 w-12 items-center justify-center rounded-3xl bg-primary/10 text-primary shadow-soft">
          <Sparkles className="h-6 w-6" />
        </div>
        <div>
          <p className="text-xs uppercase tracking-[0.28em] text-secondary">Bookly</p>
          <p className="text-lg font-semibold">AI Appointment Agent</p>
        </div>
      </div>

      <nav className="space-y-2">
        {menuItems.map((item, index) => {
          const Icon = iconMap[item.iconName] ?? ChevronRight;
          return (
            <button
              key={item.label}
              className={
                'flex w-full items-center gap-3 rounded-3xl px-4 py-3 text-sm font-medium transition ' +
                (index === 0
                  ? 'border border-primary bg-primary/10 text-primary'
                  : 'border border-white/70 bg-white/70 text-text hover:border-primary hover:text-primary')
              }
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
