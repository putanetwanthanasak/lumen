/**
 * The screen shell inside the phone frame: header, scrolling body, the prototype
 * footer (every screen), and the bottom navigation.
 */
import type { ReactNode } from "react";
import { ACCENT, type Accent } from "../accent.ts";
import { getNotifications } from "../api.ts";
import { APP_NAME, APP_NAME_TH, FOOTER, NAV } from "../copy.ts";
import { navigate, type Route } from "../router.ts";
import { DemoButton } from "./DemoPanel.tsx";
import { Icon, type IconName } from "./Icon.tsx";
import { LogoBean } from "./Logo.tsx";
import { bottomPads, NAV_TABS, navActive, navIconClass, navLabelClass, type NavTab } from "../navStyle.ts";
import { useLoad } from "../useLoad.ts";

type ScreenProps = {
  title?: string;
  back?: Route;
  route: Route;
  children: ReactNode;
  showNav?: boolean;
  /** A bar fixed under the scrolling body, above the nav (the result's buttons, the form's check). */
  actions?: ReactNode;
  /** The feature's colour on the header, with its icon before the title (the buffer). */
  accent?: Accent;
};

export function Screen({ title, back, route, children, showNav = true, actions, accent }: ScreenProps) {
  const look = accent === undefined ? null : ACCENT[accent];
  const pads = bottomPads(showNav, actions !== undefined);
  return (
    <div className="flex h-full flex-col bg-surface">
      <header
        className={`flex min-h-16 shrink-0 items-center gap-2 border-b px-4 ${look === null ? "border-line bg-card" : `${look.line} ${look.tint}`}`}
      >
        {back !== undefined ? (
          <button
            type="button"
            onClick={() => navigate(back)}
            className="-ml-2 inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-pill text-leaf-800 hover:bg-leaf-50"
          >
            <Icon name="back" label={NAV.back} />
          </button>
        ) : (
          <LogoBean size={36} />
        )}
        {title !== undefined ? (
          <h1 className={`flex flex-1 items-center gap-2 text-lead font-bold ${look === null ? "text-ink" : look.ink}`}>
            {look !== null && <Icon name={look.icon} size={22} />}
            {title}
          </h1>
        ) : (
          <p className="flex flex-1 items-baseline gap-2">
            <span className="text-lead font-bold text-leaf-800">{APP_NAME}</span>
            <span className="text-body text-ink-muted">{APP_NAME_TH}</span>
          </p>
        )}
        <HeaderActions route={route} />
      </header>
      {/* The scrollbar is hidden inside the phone frame only (index.css); the body
          still scrolls by wheel, touchpad, touch and keyboard (it takes focus). */}
      <main
        tabIndex={0}
        className={`phone-scroll min-h-0 flex-1 overflow-y-auto px-4 pt-4 ${pads.main} focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-leaf-600`}
      >
        <div className="flex flex-col gap-4">{children}</div>
        <Footer />
      </main>
      {actions !== undefined && <div className={`shrink-0 border-t border-line bg-card px-4 pt-3 shadow-card ${pads.actions}`}>{actions}</div>}
      {showNav && <BottomNav current={route} />}
    </div>
  );
}

const HEADER_BUTTON =
  "relative inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-pill text-leaf-800 hover:bg-leaf-50";

/** Top right: the notifications bell with its unread count, and settings as a gear. */
function HeaderActions({ route }: { route: Route }) {
  return (
    <div className="-mr-2 flex items-center gap-1">
      <DemoButton />
      {route !== "alerts" && <Bell />}
      {route !== "settings" && (
        <a href="#/settings" className={HEADER_BUTTON}>
          <Icon name="gear" label={NAV.settings} />
        </a>
      )}
    </div>
  );
}

/** The unread count is the API's (`unread_count`); opening the list marks it read. */
function Bell() {
  const [load] = useLoad(getNotifications);
  const unread = load.state === "ready" ? load.data.unread_count : 0;
  return (
    <a href="#/alerts" className={HEADER_BUTTON} aria-label={unread > 0 ? NAV.alertsUnread(unread) : NAV.alerts}>
      <Icon name="bell" />
      {unread > 0 && (
        <span
          aria-hidden="true"
          className="absolute top-1 right-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-pill bg-risk-ink px-1 text-[0.75rem] leading-none font-bold text-white ring-2 ring-card"
        >
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </a>
  );
}

export function Footer() {
  return <p className="mt-8 text-center text-caption text-ink-muted">{FOOTER}</p>;
}

// The tabs and which is selected live in navStyle.ts (UI-30); here only their look.
const NAV_LOOK: Record<NavTab, { label: string; icon: IconName }> = {
  home: { label: NAV.home, icon: "home" },
  think: { label: NAV.think, icon: "think" },
  buffer: { label: NAV.buffer, icon: "shield" },
};

function BottomNav({ current }: { current: Route }) {
  return (
    <nav aria-label={NAV.menu} className="shrink-0 border-t border-line bg-card">
      <ul className="flex">
        {NAV_TABS.map((tab) => {
          const item = { ...tab, ...NAV_LOOK[tab.route] };
          const active = navActive(tab.route, current);
          const primary = tab.primary;
          return (
            <li key={item.route} className="min-w-0 flex-1">
              <a
                href={`#/${item.route}`}
                aria-current={active ? "page" : undefined}
                className="group flex min-h-16 flex-col items-center justify-center gap-0.5 text-center text-caption leading-tight"
              >
                <span className={navIconClass(item.route, active)}>
                  <Icon name={item.icon} size={primary ? 28 : 22} />
                </span>
                <span className={navLabelClass(item.route, active)}>{item.label}</span>
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
