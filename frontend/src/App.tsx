import { useMemo, type ReactNode } from "react";
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
import { FollowedStoriesProvider, useFollowedStories } from "./context/FollowedStoriesContext";
import { SavedStoriesProvider } from "./context/SavedStoriesContext";
import { UserPreferencesProvider, useUserPreferences } from "./context/UserPreferencesContext";
import { ClusterDetailPage } from "./pages/ClusterDetailPage";
import { ClusterListPage } from "./pages/ClusterListPage";
import { AlertsPage } from "./pages/AlertsPage";
import { HomePage } from "./pages/HomePage";
import { MetricsPage } from "./pages/MetricsPage";
import { SavedStoriesPage } from "./pages/SavedStoriesPage";
import { SearchPage } from "./pages/SearchPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StoryDetailPage } from "./pages/StoryDetailPage";
import { formatUnreadCount } from "./utils/followedStories";

const primaryNavItems = [
  { label: "Home", to: "/", icon: "home", end: true },
  { label: "Clusters", to: "/clusters", icon: "clusters" },
  { label: "Saved", to: "/saved", icon: "saved" },
  { label: "Search", to: "/search", icon: "search" },
  { label: "Alerts", to: "/alerts", icon: "alerts" },
  { label: "Settings", to: "/settings", icon: "settings" }
];

const topicLinks = [
  { label: "World", slug: "world" },
  { label: "U.S.", slug: "us" },
  { label: "Politics", slug: "politics" },
  { label: "Business", slug: "business" },
  { label: "Technology", slug: "technology" },
  { label: "Science", slug: "science" },
  { label: "Health", slug: "health" },
  { label: "More", slug: "more" }
];

function RoundupMark() {
  return (
    <span className="roundup-mark" aria-hidden="true">
      <span />
    </span>
  );
}

function NavIcon({ name }: { name: string }) {
  return (
    <svg className="app-nav-link__icon-svg" viewBox="0 0 24 24" focusable="false" aria-hidden="true">
      {name === "home" && <path d="M4 11.5 12 5l8 6.5V20h-5v-5.5H9V20H4z" />}
      {name === "clusters" && <path d="M5 5h6v6H5zM13 5h6v6h-6zM5 13h6v6H5zM13 13h6v6h-6z" />}
      {name === "saved" && <path d="M6 4h12v17l-6-3.5L6 21z" />}
      {name === "search" && <path d="M10.5 5a5.5 5.5 0 0 1 4.35 8.86l4.15 4.15-1.41 1.41-4.15-4.15A5.5 5.5 0 1 1 10.5 5zm0 2a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7z" />}
      {name === "alerts" && <path d="M12 4a5 5 0 0 0-5 5v3.4L5 16v1h14v-1l-2-3.6V9a5 5 0 0 0-5-5zm-2 15a2 2 0 0 0 4 0z" />}
      {name === "settings" && <path d="M10.8 3h2.4l.5 2.4 2.1.9 2-1.3 1.7 1.7-1.3 2 .9 2.1 2.4.5v2.4l-2.4.5-.9 2.1 1.3 2-1.7 1.7-2-1.3-2.1.9-.5 2.4h-2.4l-.5-2.4-2.1-.9-2 1.3-1.7-1.7 1.3-2-.9-2.1-2.4-.5v-2.4l2.4-.5.9-2.1-1.3-2L6.2 5l2 1.3 2.1-.9zm1.2 6a3 3 0 1 0 0 6 3 3 0 0 0 0-6z" />}
      {name === "inspector" && <path d="M5 4h14v4H5zM5 10h14v10H5zm3 3v2h8v-2zm0 4h5v-2H8z" />}
    </svg>
  );
}

function AppShell() {
  const { preferences, resolvedTheme, updatePreferences } = useUserPreferences();
  const { unreadCount } = useFollowedStories();
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
          {primaryNavItems.map((item) => {
            const showAlertsBadge = item.to === "/alerts" && unreadCount > 0;

            return (
              <NavLink key={item.to} to={item.to} end={item.end} className="app-nav-link">
                <span className="app-nav-link__icon" aria-hidden="true">
                  <NavIcon name={item.icon} />
                </span>
                <span className="app-nav-link__label">{item.label}</span>
                {showAlertsBadge && (
                  <span className="app-nav-link__badge" aria-hidden="true">
                    {formatUnreadCount(unreadCount)}
                  </span>
                )}
              </NavLink>
            );
          })}
          <NavLink to="/inspect" className="app-nav-link app-nav-link--operator">
            <span className="app-nav-link__icon" aria-hidden="true">
              <NavIcon name="inspector" />
            </span>
            <span className="app-nav-link__label">Inspector</span>
          </NavLink>
        </nav>

        <nav className="app-sidebar__section app-sidebar__section--topics" aria-label="Topics">
          <p>Topics</p>
          {topicLinks.map((topic) => (
            <NavLink
              key={topic.slug}
              to={`/topic/${topic.slug}`}
              className="app-topic-link"
              aria-label={topic.label}
              title="Topic pages are reserved for live filtering and are not available yet."
            >
              {topic.label}
              <span className="app-topic-link__status">Soon</span>
            </NavLink>
          ))}
        </nav>

        <div className="app-sidebar__bottom">
          <NavLink to="/settings" className="app-nav-link">
            <span className="app-nav-link__icon" aria-hidden="true">
              <NavIcon name="settings" />
            </span>
            <span className="app-nav-link__label">Settings</span>
          </NavLink>
          <label className="theme-switch">
            <span>Dark mode</span>
            <input
              type="checkbox"
              checked={darkMode}
              onChange={(event) => updatePreferences({ theme: event.target.checked ? "dark" : "light" })}
              aria-label="Dark mode"
            />
            <span className="theme-switch__track" aria-hidden="true" />
          </label>
        </div>
      </aside>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

function PlaceholderPage({ title, eyebrow, children }: { title: string; eyebrow?: string; children: ReactNode }) {
  return (
    <div className="placeholder-page">
      <section className="placeholder-panel">
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        <div>{children}</div>
      </section>
    </div>
  );
}

function ClustersPlaceholderPage() {
  return (
    <PlaceholderPage title="Clusters" eyebrow="Story clusters">
      <p>
        The live home feed already shows the current public clusters. A dedicated cluster browsing view can build on the
        same API without changing the backend contract.
      </p>
      <div className="placeholder-actions">
        <Link className="primary-button" to="/">
          View top stories
        </Link>
        <Link className="secondary-button" to="/inspect">
          Open inspector
        </Link>
      </div>
    </PlaceholderPage>
  );
}

function TopicPlaceholderPage() {
  const { topicSlug = "" } = useParams();
  const topic = useMemo(
    () => topicLinks.find((item) => item.slug === topicSlug)?.label ?? topicSlug.replace(/-/g, " "),
    [topicSlug]
  );

  return (
    <PlaceholderPage title={topic || "Topic"} eyebrow="Topic">
      <p>
        Topic pages are not available yet. Use the Topic control on Top Stories to filter the live feed without
        hardcoded story content.
      </p>
      <div className="placeholder-actions">
        <Link className="primary-button" to="/">
          Open top stories
        </Link>
      </div>
    </PlaceholderPage>
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
              <FollowedStoriesProvider>
                <AppShell />
              </FollowedStoriesProvider>
            </SavedStoriesProvider>
          </UserPreferencesProvider>
        }
      >
        <Route path="/" element={<HomePage />} />
        <Route path="/story/:clusterId" element={<StoryDetailPage />} />
        <Route path="/clusters" element={<ClustersPlaceholderPage />} />
        <Route path="/saved" element={<SavedStoriesPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/topic/:topicSlug" element={<TopicPlaceholderPage />} />
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
