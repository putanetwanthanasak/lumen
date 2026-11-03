/**
 * The host shell of #/account (Session 21): a generic bank app's home around KidNee,
 * so the demo shows where KidNee lives and where the buffer's money lands. Its own
 * header and bottom bar, not KidNee's; no logo, no bank, product or company name.
 *
 * Layers as in Screen.tsx (UI-27): the scrolling body and the bar are each their own
 * layer (`isolate`), the bar drawn last; no z-index. The bar has no raised button, so
 * the body only needs the plain bottom padding.
 */
import type { ReactNode } from "react";
import { HOST } from "../accent.ts";
import { ACCOUNT } from "../copy.ts";
import { SCROLL_PAD_WITHOUT_NAV } from "../navStyle.ts";
import { DemoButton } from "./DemoPanel.tsx";
import { Icon } from "./Icon.tsx";
import { LogoBean } from "./Logo.tsx";
import { Footer } from "./Screen.tsx";

export function HostScreen({ children }: { children: ReactNode }) {
  return (
    <div className={`flex h-full flex-col ${HOST.page}`}>
      <header className="grid min-h-16 shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-2 px-4">
        <span aria-hidden="true" />
        <h1 className="text-lead font-bold">{ACCOUNT.title}</h1>
        <div className="-mr-2 flex justify-end">
          <DemoButton />
        </div>
      </header>
      <main
        tabIndex={0}
        className={`phone-scroll isolate min-h-0 flex-1 overflow-y-auto px-4 pt-2 ${SCROLL_PAD_WITHOUT_NAV} focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-white`}
      >
        <div className="flex flex-col gap-5">{children}</div>
        <Footer ink={HOST.muted} />
      </main>
      <HostNav />
    </div>
  );
}

/** Two items: this screen (selected) and KidNee. Selected is bold, white and underlined, never colour only. */
function HostNav() {
  const item = "flex min-h-16 flex-col items-center justify-center gap-1 text-caption leading-tight";
  return (
    <nav aria-label={ACCOUNT.nav.menu} className={`isolate shrink-0 ${HOST.bar}`}>
      <ul className="flex">
        <li className="min-w-0 flex-1">
          <a href="#/account" aria-current="page" className={`${item} ${HOST.focus}`}>
            <Icon name="home" size={22} className="text-white" />
            <span className={`whitespace-nowrap ${HOST.navOn}`}>{ACCOUNT.nav.home}</span>
          </a>
        </li>
        <li className="min-w-0 flex-1">
          <a href="#/home" className={`${item} ${HOST.focus}`}>
            <span aria-hidden="true" className="inline-flex h-[22px] w-[22px] items-center justify-center rounded-pill bg-card">
              <LogoBean size={18} />
            </span>
            <span className={`whitespace-nowrap ${HOST.navOff}`}>{ACCOUNT.nav.kidnee}</span>
          </a>
        </li>
      </ul>
    </nav>
  );
}
