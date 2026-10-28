/**
 * The screen shell inside the phone frame: header, scrolling body, the prototype
 * footer (every screen), and the bottom navigation.
 *
 * Layers (UI-27): the body, the action bar and the nav are each their own layer
 * (`isolate`), drawn in that order, so the nav is always the top one. Nothing in the
 * body can rise over the raised centre button, whatever lifts it (a `relative` bubble,
 * an `opacity` list, a z-index): it stays inside the body's layer. Only the Demo
 * panel, an overlay, sits above the nav.
 */
import type { ReactNode } from "react";
import { ACCENT, type Accent } from "../accent.ts";
import { APP_NAME, APP_NAME_TH, FOOTER, NAV } from "../copy.ts";
import { navigate, type Route } from "../router.ts";
import { DemoButton } from "./DemoPanel.tsx";
import { Icon, type IconName } from "./Icon.tsx";
import { LogoBean } from "./Logo.tsx";
import { bottomPads, NAV_TABS, navActive, navIconClass, navLabelClass, type NavTab } from "../navStyle.ts";

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
        className={`phone-scroll isolate min-h-0 flex-1 overflow-y-auto px-4 pt-4 ${pads.main} focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-leaf-600`}
      >
        <div className="flex flex-col gap-4">{children}</div>
        <Footer />
      </main>
      {actions !== undefined && <div className={`isolate shrink-0 border-t border-line bg-card px-4 pt-3 shadow-card ${pads.actions}`}>{actions}</div>}
      {showNav && <BottomNav current={route} />}
    </div>
  );
}

const HEADER_BUTTON =
  "relative inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-pill text-leaf-800 hover:bg-leaf-50";

/** Top right: the notifications bell, and settings as a gear. */
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

/** The bell opens the list. The API keeps no seen-or-not state, so it carries no badge. */
function Bell() {
  return (
    <a href="#/alerts" className={HEADER_BUTTON} aria-label={NAV.alerts}>
      <Icon name="bell" />
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
    <nav aria-label={NAV.menu} className="isolate shrink-0 border-t border-line bg-card">
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
