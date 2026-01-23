import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useCallback } from 'react';
import { Layout } from './components/layout';
import {
  DashboardPage,
  AlertsPage,
  PositionsPage,
  WorkflowPage,
  SettingsPage,
} from './pages';
import { useWebSocket } from './hooks';
import { useAppStore } from './stores';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function AppContent() {
  const setIsConnected = useAppStore((state) => state.setIsConnected);
  const handleWebSocketEvent = useAppStore((state) => state.handleWebSocketEvent);

  const onOpen = useCallback(() => {
    setIsConnected(true);
  }, [setIsConnected]);

  const onClose = useCallback(() => {
    setIsConnected(false);
  }, [setIsConnected]);

  useWebSocket('/ws/events', {
    onOpen,
    onClose,
    onMessage: handleWebSocketEvent,
  });

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/positions" element={<PositionsPage />} />
        <Route path="/workflow" element={<WorkflowPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </Layout>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppContent />
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
