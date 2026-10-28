/**
 * The phone frame (390x844 on a desktop, full screen on a phone) and the routes.
 * With no route in the address bar, a user without settings starts on screen 1.
 */
import { useEffect, useState } from "react";
import { getSettings } from "./api.ts";
import { DemoPanel } from "./components/DemoPanel.tsx";
import { Loading } from "./components/ui.tsx";
import { navigate, useRoute, type Route } from "./router.ts";
import { BufferScreen } from "./screens/Buffer.tsx";
import { HomeScreen } from "./screens/Home.tsx";
import { NotificationsScreen } from "./screens/Notifications.tsx";
import { MonthsScreen } from "./screens/Months.tsx";
import { ResultScreen } from "./screens/Result.tsx";
import { SettingsScreen } from "./screens/Settings.tsx";
import { ThinkFirstScreen } from "./screens/ThinkFirst.tsx";

const SCREENS: Record<Route, () => React.JSX.Element> = {
  settings: SettingsScreen,
  home: HomeScreen,
  think: ThinkFirstScreen,
  buffer: BufferScreen,
  alerts: NotificationsScreen,
  result: ResultScreen,
  months: MonthsScreen,
};

/** Bumped by the Demo panel after a scene change, so the screen on show reloads. */
function useDemoVersion(): number {
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const bump = () => setVersion((v) => v + 1);
    window.addEventListener("kidnee-demo-scene", bump);
    return () => window.removeEventListener("kidnee-demo-scene", bump);
  }, []);
  return version;
}

export function App() {
  const route = useRoute();
  const version = useDemoVersion();

  useEffect(() => {
    if (route !== null) return;
    getSettings().then(
      (settings) => navigate(settings === null ? "settings" : "home"),
      () => navigate("home"), // Home shows the error state with a retry
    );
  }, [route]);

  const Current = route === null ? null : SCREENS[route];
  return (
    <div className="flex min-h-dvh items-center justify-center sm:p-4">
      <div className="relative h-dvh w-full overflow-clip bg-surface sm:h-[844px] sm:max-h-[calc(100dvh-2rem)] sm:w-[390px] sm:rounded-[44px] sm:border-[10px] sm:border-ink sm:shadow-phone">
        {Current === null ? (
          <div className="p-4">
            <Loading lines={3} />
          </div>
        ) : (
          <Current key={`${route}-${version}`} />
        )}
        <DemoPanel />
      </div>
    </div>
  );
}
