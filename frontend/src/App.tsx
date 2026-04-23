import type { ReactNode } from "react";
import { Link, Route, Routes, BrowserRouter } from "react-router-dom";
import { ClusterDetailPage } from "./pages/ClusterDetailPage";
import { ClusterListPage } from "./pages/ClusterListPage";
import { MetricsPage } from "./pages/MetricsPage";

export function AppLayout({ children }: { children: ReactNode }) {
  return (
    <div className="app">
      <header className="app-header">
        <h1>Roundup Inspection/Debug Interface</h1>
        <p>Read-only operator view for live cluster pipeline output.</p>
        <nav>
          <Link to="/">Clusters</Link>
          <Link to="/metrics">Metrics</Link>
        </nav>
      </header>
      <main>{children}</main>
    </div>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<ClusterListPage />} />
      <Route path="/clusters/:clusterId" element={<ClusterDetailPage />} />
      <Route path="/metrics" element={<MetricsPage />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout>
        <AppRoutes />
      </AppLayout>
    </BrowserRouter>
  );
}
