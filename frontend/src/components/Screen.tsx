/**
 * The screen shell inside the phone frame: header, scrolling body, the prototype
 * footer (every screen), and the bottom navigation.
 */
import type { ReactNode } from "react";
import { APP_NAME, APP_NAME_TH, FOOTER, NAV } from "../copy.ts";
import { navigate, type Route } from "../router.ts";
import { Icon, type IconName } from "./Icon.tsx";
import { LogoBean } from "./Logo.tsx";

type ScreenProps = {
  title?: string;
  back?: Route;
  route: Route;
  children: ReactNode;
  showNav?: boolean;
  /** A bar fixed under the scrolling body, above the nav (the result screen's buttons). */
  actions?: ReactNode;
};

export function Screen({ title, back, route, children, showNav = true, actions }: ScreenProps) {
  return (
    <div className="flex h-full flex-col bg-surface">
      <header className="flex min-h-16 items-center gap-2 border-b border-line bg-card px-4">
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
          <h1 className="flex-1 text-lead font-bold text-ink">{title}</h1>
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
      <main tabIndex={0} className="phone-scroll flex-1 overflow-y-auto px-4 pt-4 pb-6 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-leaf-600">
        <div className="flex flex-col gap-4">{children}</div>
        <Footer />
      </main>
      {actions !== undefined && <div className="border-t border-line bg-card px-4 py-3 shadow-card">{actions}</div>}
      {showNav && <BottomNav current={route} />}
    </div>
  );
}

const HEADER_BUTTON =
  "relative inline-flex h-11 w-11 cursor-pointer items-center justify-center rounded-pill text-leaf-800 hover:bg-leaf-50";

/** Top right: settings as a gear (PR B adds the notifications bell next to it). */
function HeaderActions({ route }: { route: Route }) {
  return (
    <div className="-mr-2 flex items-center">
      {route !== "settings" && (
        <a href="#/settings" className={HEADER_BUTTON}>
          <Icon name="gear" label={NAV.settings} />
        </a>
      )}
    </div>
  );
}

export function Footer() {
  return <p className="mt-8 text-center text-caption text-ink-muted">{FOOTER}</p>;
}

type NavItem = { route: Route; label: string; icon: IconName; primary?: boolean };

// กันชน and ผู้ช่วยปลดหนี้ join in PR B. ตรวจสอบก่อนผ่อน is the most prominent item.
const NAV_ITEMS: NavItem[] = [
  { route: "home", label: NAV.home, icon: "home" },
  { route: "think", label: NAV.think, icon: "think", primary: true },
];

function BottomNav({ current }: { current: Route }) {
  return (
    <nav aria-label={NAV.menu} className="border-t border-line bg-card">
      <ul className="flex">
        {NAV_ITEMS.map((item) => {
          const active = item.route === current || (item.route === "think" && current === "result");
          return (
            <li key={item.route} className={item.primary === true ? "flex-[1.3]" : "flex-1"}>
              <a
                href={`#/${item.route}`}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-16 flex-col items-center justify-center gap-0.5 text-center text-caption font-semibold leading-tight ${
                  item.primary === true
                    ? "text-leaf-800"
                    : active
                      ? "text-leaf-800"
                      : "text-ink-muted hover:text-leaf-700"
                }`}
              >
                {item.primary === true ? (
                  <span
                    className={`-mt-5 mb-0.5 inline-flex h-14 w-14 items-center justify-center rounded-pill bg-leaf-700 text-white shadow-card ring-4 ring-card ${
                      active ? "bg-leaf-800" : "hover:bg-leaf-800"
                    }`}
                  >
                    <Icon name={item.icon} size={28} />
                  </span>
                ) : (
                  <Icon name={item.icon} size={24} />
                )}
                {item.label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
