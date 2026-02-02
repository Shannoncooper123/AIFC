import { Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Bell,
  TrendingUp,
  Activity,
  Settings,
  Wifi,
  WifiOff,
  FlaskConical,
  ArrowLeftRight,
} from 'lucide-react';
import { useAppStore } from '../../stores';

const navItems = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/alerts', label: 'Alerts', icon: Bell },
  { path: '/positions', label: 'Positions', icon: TrendingUp },
  { path: '/workflow', label: 'Workflow', icon: Activity },
  { path: '/backtest', label: 'Backtest', icon: FlaskConical },
  { path: '/reverse', label: 'Reverse', icon: ArrowLeftRight },
  { path: '/settings', label: 'Settings', icon: Settings },
];

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

export function Sidebar({ isOpen, onClose }: SidebarProps) {
  const location = useLocation();
  const isConnected = useAppStore((state) => state.isConnected);

  return (
    <>
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 bg-[#0a0a0a] border-r border-[#1a1a1a] transform transition-all duration-300 ease-out lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-center h-16 border-b border-[#1a1a1a]">
            <h1 className="text-lg font-semibold tracking-tight text-white">Crypto Monitor</h1>
          </div>

          <nav className="flex-1 px-3 py-6 space-y-1">
            {navItems.map((item, index) => {
              const isActive = location.pathname === item.path;
              const Icon = item.icon;
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={onClose}
                  style={{ animationDelay: `${index * 50}ms` }}
                  className={`group flex items-center gap-3 px-4 py-2.5 rounded-lg transition-all duration-200 animate-slide-in ${
                    isActive
                      ? 'bg-white text-black'
                      : 'text-neutral-400 hover:bg-[#1a1a1a] hover:text-white'
                  }`}
                >
                  <Icon 
                    size={18} 
                    className={`transition-transform duration-200 ${!isActive && 'group-hover:scale-110'}`}
                  />
                  <span className="font-medium text-sm">{item.label}</span>
                  {isActive && (
                    <div className="ml-auto w-1.5 h-1.5 rounded-full bg-black" />
                  )}
                </Link>
              );
            })}
          </nav>

          <div className="px-4 py-4 border-t border-[#1a1a1a]">
            <div className="flex items-center gap-2 text-sm">
              {isConnected ? (
                <>
                  <span className="relative flex h-2 w-2">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                  </span>
                  <Wifi size={14} className="text-neutral-500" />
                  <span className="text-neutral-400 text-xs">Connected</span>
                </>
              ) : (
                <>
                  <span className="h-2 w-2 rounded-full bg-neutral-600" />
                  <WifiOff size={14} className="text-neutral-600" />
                  <span className="text-neutral-500 text-xs">Disconnected</span>
                </>
              )}
            </div>
          </div>
        </div>
      </aside>

      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/60 backdrop-blur-sm lg:hidden animate-fade-in"
          onClick={onClose}
        />
      )}
    </>
  );
}
