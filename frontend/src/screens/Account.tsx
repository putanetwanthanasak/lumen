/**
 * บัญชีหลัก (#/account, Session 21): the host bank app's home, with KidNee as its focus
 * card. The main account (GET /bank/main-account), this month's installments (the
 * first row of GET /debts/months?count=1) and the buffer (GET /buffer). Every amount
 * is an API string; the sign of a movement is the API's `direction` (UI-51, UI-57).
 * The four shortcuts do nothing but say so.
 */
import { useState } from "react";
import { getBuffer, getMainAccount, getMonths, getSettings } from "../api.ts";
import type { BufferOut, MainAccountOut, MonthRow, Movement } from "../api-types.ts";
import { HOST } from "../accent.ts";
import { ACCOUNT, APP_NAME, APP_NAME_TH } from "../copy.ts";
import { HostScreen } from "../components/HostScreen.tsx";
import { Icon, type IconName } from "../components/Icon.tsx";
import { LogoBean } from "../components/Logo.tsx";
import { ErrorState, Loading, MarkedText, StatusChip } from "../components/ui.tsx";
import { formatAmount, formatBaht } from "../money.ts";
import { monthStatus, STATUS_CHIP } from "../monthStatus.ts";
import { thaiDate, thaiMonth } from "../thaiMonth.ts";
import { useLoad, type Load } from "../useLoad.ts";

export type AccountData = {
  account: MainAccountOut;
  buffer: BufferOut;
  /** This month's row; null before KidNee is set up (no income and budget yet). */
  month: MonthRow | null;
};

async function loadAccount(): Promise<AccountData> {
  const settings = await getSettings();
  const [account, buffer, months] = await Promise.all([
    getMainAccount(),
    getBuffer(),
    settings === null ? Promise.resolve(null) : getMonths(1),
  ]);
  return { account, buffer, month: months?.months[0] ?? null };
}

export function AccountScreen() {
  const [load, reload] = useLoad(loadAccount);
  return <AccountContent load={load} onRetry={reload} />;
}

export function AccountContent({ load, onRetry }: { load: Load<AccountData>; onRetry: () => void }) {
  return (
    <HostScreen>
      {load.state === "loading" && <Loading lines={3} />}
      {load.state === "error" && <ErrorState onRetry={onRetry} />}
      {load.state === "ready" && <AccountBody {...load.data} />}
    </HostScreen>
  );
}

export function AccountBody({ account, buffer, month, note = false }: AccountData & { note?: boolean }) {
  return (
    <>
      <section className={`flex flex-col gap-1 rounded-card p-5 ${HOST.card}`}>
        <h2 className="text-body font-semibold">{ACCOUNT.savings}</h2>
        <p className={`text-caption ${HOST.muted}`}>{ACCOUNT.maskedNumber}</p>
        <p className={`mt-3 text-caption ${HOST.muted}`}>{ACCOUNT.available}</p>
        <p className="flex items-baseline gap-2">
          <span className="text-display font-bold">{formatAmount(account.balance)}</span>
          <span className="text-lead">{ACCOUNT.baht}</span>
        </p>
        <p className={`text-caption ${HOST.muted}`}>{ACCOUNT.mockData}</p>
      </section>

      <Shortcuts note={note} />

      <KidNeeCard buffer={buffer} month={month} />

      <Movements movements={account.movements} />
    </>
  );
}

const SHORTCUTS: { key: keyof typeof ACCOUNT.shortcuts; icon: IconName }[] = [
  { key: "transfer", icon: "transfer" },
  { key: "bill", icon: "bill" },
  { key: "topup", icon: "topup" },
  { key: "scan", icon: "scan" },
];

/** Examples only: pressing one shows the note and nothing else (UI-59). */
export function Shortcuts({ note = false }: { note?: boolean }) {
  const [shown, setShown] = useState(note);
  return (
    <section aria-label={ACCOUNT.shortcutsLabel} className="flex flex-col gap-2">
      <ul className="grid grid-cols-4 gap-2">
        {SHORTCUTS.map((s) => (
          <li key={s.key}>
            <button
              type="button"
              onClick={() => setShown(true)}
              className={`group flex w-full cursor-pointer flex-col items-center gap-1 rounded-field py-1 text-caption ${HOST.focus}`}
            >
              <span className={`inline-flex h-12 w-12 items-center justify-center rounded-pill ${HOST.shortcut}`}>
                <Icon name={s.icon} size={22} />
              </span>
              <span className="whitespace-nowrap">{ACCOUNT.shortcuts[s.key]}</span>
            </button>
          </li>
        ))}
      </ul>
      {shown && (
        <p role="status" className={`text-center text-body ${HOST.muted}`}>
          {ACCOUNT.shortcutNote}
        </p>
      )}
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
    <section className="flex flex-col gap-2">
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
