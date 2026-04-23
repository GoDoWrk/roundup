import type { ReactNode } from "react";
import { BrowserRouter, Link, Navigate, NavLink, Outlet, Route, Routes, useParams } from "react-router-dom";
import { ClusterDetailPage } from "./pages/ClusterDetailPage";
import { ClusterListPage } from "./pages/ClusterListPage";
import { HomePage } from "./pages/HomePage";
import { MetricsPage } from "./pages/MetricsPage";
import { StoryDetailPage } from "./pages/StoryDetailPage";

export function AppLayout({ children }: { children?: ReactNode }) {
  return (
    <div className="inspect-shell">
      <header className="inspect-header">
        <div className="inspect-header__copy">
          <p className="eyebrow">Operator view</p>
          <h1>Roundup Inspector</h1>
          <p>Read-only debug interface for live cluster pipeline output.</p>
        </div>
        <nav className="inspect-nav" aria-label="Inspector navigation">
          <Link to="/">Home</Link>
          <NavLink to="/inspect" end>
            Clusters
          </NavLink>
          <NavLink to="/inspect/metrics">Metrics</NavLink>
        </nav>
      </header>
      <main className="inspect-main">{children ?? <Outlet />}</main>
    </div>
  );
}

function LegacyClusterRedirect() {
  const { clusterId = "" } = useParams();
  return <Navigate to={`/inspect/clusters/${clusterId}`} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/story/:clusterId" element={<StoryDetailPage />} />
      <Route path="/inspect" element={<AppLayout />}>
        <Route index element={<ClusterListPage />} />
        <Route path="clusters/:clusterId" element={<ClusterDetailPage />} />
        <Route path="metrics" element={<MetricsPage />} />
      </Route>
      <Route path="/clusters/:clusterId" element={<LegacyClusterRedirect />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRoutes />
    </BrowserRouter>
  );
}
