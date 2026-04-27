import { type ReactNode } from "react";
import {
  BrowserRouter,
  Link,
  Navigate,
  NavLink,
  Outlet,
  Route,
  Routes,
  useParams
} from "react-router-dom";
import { SavedStoriesProvider } from "./context/SavedStoriesContext";
import { UserPreferencesProvider, useUserPreferences } from "./context/UserPreferencesContext";
import { ClusterDetailPage } from "./pages/ClusterDetailPage";
import { ClusterListPage } from "./pages/ClusterListPage";
import { HomePage } from "./pages/HomePage";
import { MetricsPage } from "./pages/MetricsPage";
import { SavedStoriesPage } from "./pages/SavedStoriesPage";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StoryDetailPage } from "./pages/StoryDetailPage";

const primaryNavItems = [
  { label: "Home", to: "/", icon: "H", end: true },
  { label: "Saved", to: "/saved", icon: "S" },
  { label: "Inspector", to: "/inspect", icon: "I" },
  { label: "Settings", to: "/settings", icon: "G" }
];

function RoundupMark() {
  return (
    <span className="roundup-mark" aria-hidden="true">
      <span />
    </span>
  );
}

function AppShell() {
  const { preferences, resolvedTheme } = useUserPreferences();
  const darkMode = resolvedTheme === "dark";
  const shellClassName = [
    "app-shell",
    darkMode ? "app-shell--dark" : "",
    preferences.compactMode ? "app-shell--compact" : ""
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={shellClassName}>
      <aside className="app-sidebar" aria-label="Roundup navigation">
        <Link className="app-brand" to="/">
          <RoundupMark />
          <span>roundup</span>
        </Link>

        <nav className="app-sidebar__section app-sidebar__section--primary" aria-label="Primary navigation">
          {primaryNavItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className="app-nav-link">
              <span className="app-nav-link__icon" aria-hidden="true">
                {item.icon}
              </span>
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

      </aside>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

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
      <Route
        element={
          <UserPreferencesProvider>
            <SavedStoriesProvider>
              <AppShell />
            </SavedStoriesProvider>
          </UserPreferencesProvider>
        }
      >
        <Route path="/" element={<HomePage />} />
        <Route path="/story/:clusterId" element={<StoryDetailPage />} />
        <Route path="/clusters" element={<Navigate to="/" replace />} />
        <Route path="/saved" element={<SavedStoriesPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/alerts" element={<Navigate to="/saved" replace />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/topic/:topicSlug" element={<Navigate to="/" replace />} />
      </Route>
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
