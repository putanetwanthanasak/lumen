/**
 * The phone frame (390x844 on a desktop, full screen on a phone) and the routes.
 * With no route in the address bar, a user without settings starts on screen 1.
 */
import { useEffect } from "react";
import { getSettings } from "./api.ts";
import { Loading } from "./components/ui.tsx";
import { navigate, useRoute, type Route } from "./router.ts";
import { HomeScreen } from "./screens/Home.tsx";
import { MonthsScreen } from "./screens/Months.tsx";
import { ResultScreen } from "./screens/Result.tsx";
import { SettingsScreen } from "./screens/Settings.tsx";
import { ThinkFirstScreen } from "./screens/ThinkFirst.tsx";

const SCREENS: Record<Route, () => React.JSX.Element> = {
  settings: SettingsScreen,
  home: HomeScreen,
  think: ThinkFirstScreen,
  result: ResultScreen,
  months: MonthsScreen,
};

export function App() {
  const route = useRoute();

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
      <div className="relative h-dvh w-full overflow-hidden bg-surface sm:h-[844px] sm:max-h-[calc(100dvh-2rem)] sm:w-[390px] sm:rounded-[44px] sm:border-[10px] sm:border-ink sm:shadow-phone">
        {Current === null ? (
          <div className="p-4">
            <Loading lines={3} />
          </div>
        ) : (
          <Current key={route} />
        )}
      </div>
    </div>
  );
}
