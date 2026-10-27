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
};

export function Screen({ title, back, route, children, showNav = true }: ScreenProps) {
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
          <h1 className="text-lead font-bold text-ink">{title}</h1>
        ) : (
          <p className="flex items-baseline gap-2">
            <span className="text-lead font-bold text-leaf-800">{APP_NAME}</span>
            <span className="text-body text-ink-muted">{APP_NAME_TH}</span>
          </p>
        )}
      </header>
      <main className="flex-1 overflow-y-auto px-4 pt-4 pb-6">
        <div className="flex flex-col gap-4">{children}</div>
        <Footer />
      </main>
      {showNav && <BottomNav current={route} />}
    </div>
  );
}

export function Footer() {
  return <p className="mt-8 text-center text-caption text-ink-muted">{FOOTER}</p>;
}

type NavItem = { route: Route; label: string; icon: IconName };

// Buffer and alerts join in PR B.
const NAV_ITEMS: NavItem[] = [
  { route: "home", label: NAV.home, icon: "home" },
  { route: "think", label: NAV.think, icon: "think" },
  { route: "settings", label: NAV.settings, icon: "gear" },
];

function BottomNav({ current }: { current: Route }) {
  return (
    <nav aria-label="เมนูหลัก" className="border-t border-line bg-card">
      <ul className="flex">
        {NAV_ITEMS.map((item) => {
          const active = item.route === current;
          return (
            <li key={item.route} className="flex-1">
              <a
                href={`#/${item.route}`}
                aria-current={active ? "page" : undefined}
                className={`flex min-h-16 flex-col items-center justify-center gap-0.5 text-caption font-semibold ${
                  active ? "text-leaf-800" : "text-ink-muted hover:text-leaf-700"
                }`}
              >
                <Icon name={item.icon} size={24} />
                {item.label}
              </a>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
