/**
 * บัญชีหลัก (#/account, Sessions 21 and 22): the host bank app's home, with KidNee as
 * its focus card. The main account (GET /bank/main-account), this month's installments
 * (the first row of GET /debts/months?count=1) and the buffer (GET /buffer). Every
 * amount is an API string; the sign of a movement is the API's `direction` (UI-51,
 * UI-57). The example shortcuts and the other example controls only show their note
 * (UI-64); KidNee opens from its shortcut, its card and the bar (UI-65).
 */
import { getBuffer, getMainAccount, getMonths, getSettings } from "../api.ts";
import type { BufferOut, MainAccountOut, MonthRow, Movement } from "../api-types.ts";
import { HOST } from "../accent.ts";
import { ACCOUNT, APP_NAME, APP_NAME_TH } from "../copy.ts";
import { ExampleButton, HostScreen } from "../components/HostScreen.tsx";
import { Icon, type IconName } from "../components/Icon.tsx";
import { LogoBean } from "../components/Logo.tsx";
import { ErrorState, Loading, MarkedText, StatusChip } from "../components/ui.tsx";
import { formatAmount, formatBaht } from "../money.ts";
import { monthStatus, STATUS_CHIP } from "../monthStatus.ts";
import { thaiDate, thaiMonth, thaiTime } from "../thaiMonth.ts";
import { useLoad, type Load } from "../useLoad.ts";

export type AccountData = {
  account: MainAccountOut;
  buffer: BufferOut;
  /** This month's row; null before KidNee is set up (no income and budget yet). */
  month: MonthRow | null;
  /** When the answers arrived: "ข้อมูล ณ เวลา HH:MM น." (UI-67). */
  loadedAt: Date;
};

export async function loadAccount(): Promise<AccountData> {
  const settings = await getSettings();
  const [account, buffer, months] = await Promise.all([
    getMainAccount(),
    getBuffer(),
    settings === null ? Promise.resolve(null) : getMonths(1),
  ]);
  return { account, buffer, month: months?.months[0] ?? null, loadedAt: new Date() };
}

export function AccountScreen() {
  const [load, reload] = useLoad(loadAccount);
  return <AccountContent load={load} onRetry={reload} />;
}

export function AccountContent({ load, onRetry, note = false }: { load: Load<AccountData>; onRetry: () => void; note?: boolean }) {
  return (
    <HostScreen note={note}>
      {load.state === "loading" && <Loading lines={3} />}
      {load.state === "error" && <ErrorState onRetry={onRetry} />}
      {load.state === "ready" && <AccountBody {...load.data} />}
    </HostScreen>
  );
}

export function AccountBody({ account, buffer, month, loadedAt }: AccountData) {
  return (
    <>
      <div className="flex flex-col gap-2">
        <Passbook balance={account.balance} />
        <div className="flex items-center justify-between gap-2">
          <ExampleButton className="-ml-1 inline-flex min-h-11 items-center gap-1 rounded-field px-1 text-body font-semibold">
            {ACCOUNT.myAccounts}
            <Icon name="next" size={18} />
          </ExampleButton>
          <p className={`text-caption ${HOST.muted}`}>{ACCOUNT.loadedAt(thaiTime(loadedAt))}</p>
        </div>
        <span aria-hidden="true" className="flex justify-center gap-2">
          <span className={`h-2 w-2 rounded-pill ${HOST.dotOn}`} />
          <span className={`h-2 w-2 rounded-pill ${HOST.dotOff}`} />
          <span className={`h-2 w-2 rounded-pill ${HOST.dotOff}`} />
        </span>
      </div>

      <Shortcuts />

      <section className="flex flex-col gap-2">
        <h2 className="text-lead font-bold">{ACCOUNT.services}</h2>
        <KidNeeCard buffer={buffer} month={month} />
      </section>

      <Movements movements={account.movements} />
    </>
  );
}

/** The account card, an open savings passbook of our own: a darker spine, faint horizontal rules (UI-68). */
export function Passbook({ balance }: { balance: string }) {
  return (
    <section aria-label={ACCOUNT.savings} className={`flex overflow-hidden rounded-card ${HOST.card}`}>
      <span aria-hidden="true" className={`w-4 shrink-0 ${HOST.spine}`} />
      <div className={`flex min-w-0 flex-1 flex-col gap-1 p-5 ${HOST.rules}`}>
        <span className="flex items-start justify-between gap-2">
          <h2 className="text-body font-semibold">
            {/* The chevron looks like an account switcher, so it is an example too (UI-64). */}
            <ExampleButton className="-my-2 -ml-1 inline-flex min-h-11 items-center gap-1 rounded-field px-1">
              {ACCOUNT.savings}
              <Icon name="down" size={18} />
            </ExampleButton>
          </h2>
          <Icon name="passbook" size={26} />
        </span>
        <p className={`text-caption ${HOST.muted}`}>{ACCOUNT.maskedNumber}</p>
        <p className={`mt-3 text-caption ${HOST.muted}`}>{ACCOUNT.available}</p>
        <p className="flex items-baseline gap-2">
          <span className="text-display font-bold">{formatAmount(balance)}</span>
          <span className="text-lead">{ACCOUNT.baht}</span>
        </p>
        <p className={`text-caption ${HOST.muted}`}>{ACCOUNT.mockData}</p>
        <button
          type="button"
          onClick={showRecent}
          className={`mt-2 inline-flex min-h-11 cursor-pointer items-center gap-1 self-start text-body font-semibold underline underline-offset-4 ${HOST.focus}`}
        >
          {ACCOUNT.seeRecent}
          <Icon name="next" size={18} />
        </button>
      </div>
    </section>
  );
}

/** The id of รายการล่าสุด, which "ดูรายการล่าสุด ›" scrolls to and focuses (UI-66). */
export const RECENT_ID = "recent";

export function showRecent() {
  const recent = document.getElementById(RECENT_ID);
  if (recent === null) return;
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  recent.scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
  recent.focus({ preventScroll: true });
}

const SHORTCUTS: { key: keyof typeof ACCOUNT.shortcuts; icon: IconName }[] = [
  { key: "transfer", icon: "transfer" },
  { key: "bill", icon: "bill" },
  { key: "topup", icon: "topup" },
  { key: "scan", icon: "scan" },
  { key: "cashout", icon: "cashout" },
  { key: "statement", icon: "statement" },
  { key: "goal", icon: "goal" },
];

const SHORTCUT = "group flex w-full flex-col items-center gap-1 rounded-field py-1 text-center text-caption leading-tight";
const SHORTCUT_ICON = "relative inline-flex h-12 w-12 items-center justify-center rounded-pill";

/** Eight in two rows: seven examples (UI-64), and KidNee, new, which opens its Home (UI-65). */
export function Shortcuts() {
  return (
    <section aria-label={ACCOUNT.shortcutsLabel}>
      <ul className="grid grid-cols-4 gap-x-1 gap-y-3">
        {SHORTCUTS.map((s) => (
          <li key={s.key}>
            <ExampleButton className={SHORTCUT}>
              <span className={`${SHORTCUT_ICON} ${HOST.shortcut}`}>
                <Icon name={s.icon} size={22} />
              </span>
              <span>{ACCOUNT.shortcuts[s.key]}</span>
            </ExampleButton>
          </li>
        ))}
        <li>
          <a href="#/home" className={`${SHORTCUT} ${HOST.focus}`}>
            <span className={`${SHORTCUT_ICON} bg-card`}>
              <span aria-hidden="true" className="inline-flex">
                <LogoBean size={32} />
              </span>
              <span className={`absolute -top-1 -right-3 rounded-pill px-1.5 text-caption leading-tight ${HOST.badge}`}>{ACCOUNT.newBadge}</span>
            </span>
            <span>{APP_NAME}</span>
          </a>
        </li>
      </ul>
    </section>
  );
}

/** The focus of the screen: a white card that opens KidNee's Home. */
export function KidNeeCard({ buffer, month }: { buffer: BufferOut; month: MonthRow | null }) {
  const status = month === null ? null : monthStatus(month);
  return (
    <a
      href="#/home"
      className={`flex flex-col gap-3 rounded-card bg-card p-5 text-ink shadow-card hover:bg-leaf-50 ${HOST.focus}`}
    >
      <span className="flex items-center gap-3">
        <LogoBean size={40} />
        <span className="flex flex-1 items-baseline gap-2">
          <span className="text-lead font-bold text-leaf-800">{APP_NAME}</span>
          <span className="text-body text-ink-muted">{APP_NAME_TH}</span>
        </span>
        <Icon name="next" className="text-leaf-800" />
      </span>
      {month === null || status === null ? (
        <span className="text-body text-ink">{ACCOUNT.setUp}</span>
      ) : (
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-body font-semibold text-ink">{ACCOUNT.thisMonth(formatBaht(month.total))}</span>
          <StatusChip chip={{ icon: status.icon, label: status.label, className: STATUS_CHIP[status.tone] }} />
        </span>
      )}
      <MarkedText item={{ accent: "buffer", icon: "shield", text: ACCOUNT.buffer(formatBaht(buffer.balance)) }} />
    </a>
  );
}

export const RECENT_COUNT = 5;

/** The API's newest movements, in its order; + or − from `direction`, never computed (UI-57). */
export function Movements({ movements }: { movements: Movement[] }) {
  const shown = movements.slice(0, RECENT_COUNT);
  return (
    <section id={RECENT_ID} tabIndex={-1} className={`flex scroll-mt-2 flex-col gap-2 rounded-field ${HOST.focus}`}>
      <h2 className="text-lead font-bold">{ACCOUNT.recent}</h2>
      <div className="rounded-card bg-card px-4 text-ink shadow-card">
        {shown.length === 0 ? (
          <p className="py-4 text-body text-ink-muted">{ACCOUNT.empty}</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line">
            {shown.map((m) => (
              <li key={m.id} className="flex items-start justify-between gap-3 py-3">
                <span className="flex flex-col">
                  <span className="text-body text-ink">
                    {ACCOUNT.movement[m.kind]}
                    {m.for_month !== null && (
                      <>
                        {" "}
                        <span className="whitespace-nowrap">{ACCOUNT.forMonth(thaiMonth(m.for_month))}</span>
                      </>
                    )}
                  </span>
                  <span className="text-caption text-ink-muted">{thaiDate(m.at)}</span>
                </span>
                <span className={`whitespace-nowrap text-body font-bold ${m.direction === "in" ? "text-ok-ink" : "text-ink"}`}>
                  {signed(m)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

/** The row's words as one line of text (the row keeps "สำหรับ {month}" on one line). */
export function movementLabel(m: Pick<Movement, "kind" | "for_month">): string {
  const label = ACCOUNT.movement[m.kind];
  return m.for_month === null ? label : `${label} ${ACCOUNT.forMonth(thaiMonth(m.for_month))}`;
}

/** "+1,500.00" into the main account, "−40.00" (U+2212) out of it: the sign is the API's direction. */
export function signed(m: Pick<Movement, "direction" | "amount">): string {
  return `${m.direction === "in" ? "+" : "−"}${formatAmount(m.amount)}`;
}
