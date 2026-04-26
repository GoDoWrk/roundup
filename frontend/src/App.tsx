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
  { label: "Home", to: "/", icon: "H", end: true },
  { label: "Clusters", to: "/clusters", icon: "C" },
  { label: "Saved", to: "/saved", icon: "S" },
  { label: "Search", to: "/search", icon: "Q" },
  { label: "Alerts", to: "/alerts", icon: "A" },
  { label: "Settings", to: "/settings", icon: "G" }
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
                  {item.icon}
                </span>
                <span>{item.label}</span>
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
              I
            </span>
            <span>Inspector</span>
          </NavLink>
        </nav>

        <nav className="app-sidebar__section app-sidebar__section--topics" aria-label="Topics">
          <p>Topics</p>
          {topicLinks.map((topic) => (
            <NavLink key={topic.slug} to={`/topic/${topic.slug}`} className="app-topic-link">
              {topic.label}
            </NavLink>
          ))}
        </nav>

        <div className="app-sidebar__bottom">
          <NavLink to="/settings" className="app-nav-link">
            <span className="app-nav-link__icon" aria-hidden="true">
              G
            </span>
            <span>Settings</span>
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
      <p>This topic route is reserved for live topic filtering. It does not hardcode story content.</p>
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
