/**
 * The host shell of #/account (Sessions 21 and 22): a generic bank app's home around
 * KidNee, so the demo shows where KidNee lives and where the buffer's money lands. Its
 * own header, tabs and bottom bar, not KidNee's; no logo, no bank, product or company
 * name.
 *
 * Example controls (UI-64): every button that only stands in for a bank app's feature
 * is an ExampleButton. Pressing one shows "ปุ่มตัวอย่าง ใช้ไม่ได้ในเดโม" in one strip above
 * the bar and does nothing else.
 *
 * Layers as in Screen.tsx (UI-27): the scrolling body, the note strip and the bar are
 * each their own layer (`isolate`), the bar drawn last; no z-index. The bar has no
 * raised button, so the body only needs the plain bottom padding.
 */
import { createContext, useContext, useState, type ReactNode } from "react";
import { HOST } from "../accent.ts";
import { ACCOUNT } from "../copy.ts";
import { SCROLL_PAD_WITHOUT_NAV } from "../navStyle.ts";
import { DemoButton } from "./DemoPanel.tsx";
import { Icon, type IconName } from "./Icon.tsx";
import { LogoBean } from "./Logo.tsx";
import { Footer } from "./Screen.tsx";

const ShowNote = createContext<() => void>(() => undefined);

/** A bank app feature the demo does not have: a press shows the note and nothing else (UI-64). */
export function ExampleButton({ label, className, children }: { label?: string; className: string; children: ReactNode }) {
  const show = useContext(ShowNote);
  return (
    <button type="button" aria-label={label} onClick={() => show()} className={`cursor-pointer ${className} ${HOST.focus}`}>
      {children}
    </button>
  );
}

/**
 * `note` starts with the note shown (the tests render with it; the screen starts without).
 * Each press counts, and the note is keyed on the count, so the status region gets new
 * content and a screen reader announces every press, not only the first.
 */
export function HostScreen({ children, note = false }: { children: ReactNode; note?: boolean }) {
  const [presses, setPresses] = useState(note ? 1 : 0);
  return (
    <ShowNote.Provider value={() => setPresses((n) => n + 1)}>
      <div className={`flex h-full flex-col ${HOST.page}`}>
        <HostHeader />
        <main
          tabIndex={0}
          className={`phone-scroll isolate min-h-0 flex-1 overflow-y-auto px-4 pt-2 ${SCROLL_PAD_WITHOUT_NAV} focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-white`}
        >
          <div className="flex flex-col gap-5">
            <HostTabs />
            {children}
          </div>
          <Footer ink={HOST.muted} />
        </main>
        <div role="status" className="isolate shrink-0">
          {presses > 0 && (
            <p key={presses} className={`flex items-center gap-2 px-4 py-2 text-body ${HOST.strip}`}>
              <Icon name="info" size={20} />
              {ACCOUNT.shortcutNote}
            </p>
          )}
        </div>
        <HostNav />
      </div>
    </ShowNote.Provider>
  );
}

const ROUND = "inline-flex h-11 w-11 items-center justify-center rounded-pill";

/** The profile on the left, the title between, the bell, power and Demo on the right. */
function HostHeader() {
  return (
    <header className="grid min-h-16 shrink-0 grid-cols-[auto_1fr_auto] items-center gap-2 px-4">
      <ExampleButton label={ACCOUNT.header.profile} className={`${ROUND} ${HOST.round}`}>
        <Icon name="person" size={22} />
      </ExampleButton>
      <h1 className="text-center text-lead font-bold">{ACCOUNT.title}</h1>
      <div className="-mr-2 flex items-center">
        <ExampleButton label={ACCOUNT.header.bell} className={`${ROUND} ${HOST.icon}`}>
          <Icon name="bell" size={22} />
        </ExampleButton>
        <ExampleButton label={ACCOUNT.header.power} className={`${ROUND} ${HOST.icon}`}>
          <Icon name="power" size={22} />
        </ExampleButton>
        <DemoButton />
      </div>
    </header>
  );
}

const TAB = "inline-flex min-h-11 items-center rounded-pill px-4 text-body whitespace-nowrap";

/** บัญชี is this screen; the other tabs are examples. */
function HostTabs() {
  const others = ["card", "loan", "invest"] as const;
  return (
    <ul aria-label={ACCOUNT.tabsLabel} className="flex gap-2">
      <li>
        <span aria-current="page" className={`${TAB} ${HOST.tabOn}`}>
          {ACCOUNT.tabs.account}
        </span>
      </li>
      {others.map((key) => (
        <li key={key}>
          <ExampleButton className={`${TAB} ${HOST.tabOff}`}>{ACCOUNT.tabs[key]}</ExampleButton>
        </li>
      ))}
    </ul>
  );
}

const NAV_ITEM = "flex min-h-16 w-full flex-col items-center justify-center gap-1 text-caption leading-tight";
const NAV_EXAMPLES: { key: "history" | "scan" | "profile"; icon: IconName }[] = [
  { key: "history", icon: "history" },
  { key: "scan", icon: "scan" },
  { key: "profile", icon: "person" },
];

/** Five flat items: this screen (selected), three examples and KidNee. Selected is bold, white and underlined, never colour only. */
function HostNav() {
  const [history, scan, profile] = NAV_EXAMPLES.map((n) => (
    <li key={n.key} className="min-w-0 flex-1">
      <ExampleButton className={NAV_ITEM}>
        <Icon name={n.icon} size={22} className={HOST.muted} />
        <span className={`whitespace-nowrap ${HOST.navOff}`}>{ACCOUNT.nav[n.key]}</span>
      </ExampleButton>
    </li>
  ));
  return (
    <nav aria-label={ACCOUNT.nav.menu} className={`isolate shrink-0 ${HOST.bar}`}>
      <ul className="flex">
        <li className="min-w-0 flex-1">
          <a href="#/account" aria-current="page" className={`${NAV_ITEM} ${HOST.focus}`}>
            <Icon name="home" size={22} className="text-white" />
            <span className={`whitespace-nowrap ${HOST.navOn}`}>{ACCOUNT.nav.home}</span>
          </a>
        </li>
        {history}
        {scan}
        <li className="min-w-0 flex-1">
          <a href="#/home" className={`${NAV_ITEM} ${HOST.focus}`}>
            <span aria-hidden="true" className="inline-flex h-[22px] w-[22px] items-center justify-center rounded-pill bg-card">
              <LogoBean size={18} />
            </span>
            <span className={`whitespace-nowrap ${HOST.navOff}`}>{ACCOUNT.nav.kidnee}</span>
          </a>
        </li>
        {profile}
      </ul>
    </nav>
  );
}
