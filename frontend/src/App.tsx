import { Info, LayoutDashboard, Map as MapIcon, Moon, Route, Sun, TriangleAlert } from "lucide-react";
import { lazy, Suspense } from "react";
import { useStatus } from "./api/hooks";
import { ErrorState, Loading, StartingUp } from "./components/States";
import { href, useRoute } from "./lib/router";
import { useTheme } from "./lib/theme";
import { About } from "./views/About";
import { Alerts } from "./views/Alerts";
import { Overview } from "./views/Overview";
import { RouteDetail, Routes } from "./views/Routes";

// The map library is large; it loads only when the map is opened.
const MapView = lazy(() => import("./views/MapView").then((module) => ({ default: module.MapView })));

const NAV = [
  { key: "", label: "Overview", icon: LayoutDashboard },
  { key: "map", label: "Map", icon: MapIcon },
  { key: "routes", label: "Routes", icon: Route },
  { key: "alerts", label: "Alerts", icon: TriangleAlert },
  { key: "about", label: "About", icon: Info },
] as const;

export function App() {
  const route = useRoute();
  const section = route[0] ?? "";
  const [theme, toggleTheme] = useTheme();
  const status = useStatus();

  // Until the server has answered and loaded its timetable, no view has anything to
  // show. The About page still opens: it explains what is going on.
  const problem = status.data === undefined ? (status.error ?? status.failureReason) : null;
  const starting =
    section !== "about" &&
    ((status.data === undefined && (problem === null || problem.isStarting)) ||
      (status.data !== undefined && status.data.data?.static == null));
  const failed = problem && !problem.isStarting ? problem : null;

  let view;
  if (failed && section !== "about") {
    view = <ErrorState error={failed} onRetry={() => void status.refetch()} />;
  } else if (starting) {
    view = <StartingUp />;
  } else if (section === "map") {
    view = (
      <Suspense fallback={<Loading label="Loading the map" />}>
        <MapView theme={theme} />
      </Suspense>
    );
  } else if (section === "routes") {
    view = route[1] ? <RouteDetail key={route[1]} routeId={route[1]} /> : <Routes />;
  } else if (section === "alerts") {
    view = <Alerts />;
  } else if (section === "about") {
    view = <About />;
  } else {
    view = <Overview />;
  }

  const isMap = section === "map" && !starting && !failed;
  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="topbar">
        <a className="brand" href={href()}>
          <span className="brand-dot" aria-hidden="true" />
          BrisPulse
        </a>
        <nav className="nav" aria-label="Main">
          {NAV.map(({ key, label, icon: Icon }) => (
            <a key={key} href={href(...(key ? [key] : []))} aria-current={section === key ? "page" : undefined}>
              <Icon size={18} aria-hidden="true" />
              {label}
            </a>
          ))}
        </nav>
        <div className="topbar-end">
          <button
            type="button"
            className="icon-button"
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
          >
            {theme === "dark" ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
          </button>
        </div>
      </header>
      <main id="main" className={isMap ? "main is-map" : "main"} tabIndex={-1}>
        {view}
      </main>
    </div>
  );
}
