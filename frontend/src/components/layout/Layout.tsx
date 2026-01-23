import { useState } from 'react';
import { Menu, X } from 'lucide-react';
import { Sidebar } from './Sidebar';

interface LayoutProps {
  children: React.ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#0a0a0a]">
      <button
        className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-[#141414] border border-[#2a2a2a] rounded-lg text-neutral-400 hover:text-white hover:bg-[#1a1a1a] transition-all duration-200 active:scale-95"
        onClick={() => setSidebarOpen(!sidebarOpen)}
      >
        {sidebarOpen ? <X size={20} /> : <Menu size={20} />}
      </button>

      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <main className="lg:ml-64 min-h-screen">
        <div className="p-6 animate-fade-in">{children}</div>
      </main>
    </div>
  );
}
