/**
 * Screen 2: Home, ภาพรวมหนี้ (DESIGN.md section 7.2). Card types, by importance:
 * the hero (this month against the budget, one warning line and one buffer line), the
 * เช็กก่อนผ่อน button, the buffer wallet, the assistant's bubble, consolidation (a
 * one-line banner, or the bank's offer), and the installments list. Which card shows
 * and in which shape comes from homeLayout.ts (UI-33). All amounts are API strings.
 */
import { Fragment, useId, useState } from "react";
import { getAssistantPlan, getBuffer, getDebtSummary, getMonths, getSettings, getShortfalls } from "../api.ts";
import type { AssistantPlanOut, BufferOut, DebtSummary, InstallmentLine, MonthsOut, SettingsOut, ShortfallsOut } from "../api-types.ts";
import { ACCENT, BUFFER_METER, EDGE, SOLID } from "../accent.ts";
import { barSegments } from "../barSegments.ts";
import { openBufferAt } from "../bufferState.ts";
import { BUFFER_STATE, HOME } from "../copy.ts";
import { AiBubbleCard, ConsolidationCard } from "../components/AssistantCards.tsx";
import { BarParts } from "../components/BarParts.tsx";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Button, ErrorState, Loading, MarkedText, SettingsMissing } from "../components/ui.tsx";
import { homeView, WALLET_SEGMENTS, type HeroView, type WalletView } from "../homeLayout.ts";
import { groupByPlatform, lineStatus, scheduleText } from "../installmentStatus.ts";
import { barPermille, formatBaht, largest, type Money } from "../money.ts";
import { currentPersona } from "../personas.ts";
import { navigate } from "../router.ts";
import { thaiMonth } from "../thaiMonth.ts";
import { useLoad } from "../useLoad.ts";

type HomeData =
  | { settings: null }
  | {
      settings: SettingsOut;
      summary: DebtSummary;
      buffer: BufferOut;
      months: MonthsOut;
      plan: AssistantPlanOut | null;
      shortfalls: ShortfallsOut | null;
    };

async function loadHome(): Promise<HomeData> {
  const settings = await getSettings();
  if (settings === null) return { settings: null };
  const [summary, buffer, months, plan, shortfalls] = await Promise.all([
    getDebtSummary(),
    getBuffer(),
    // Every month to the last one due: the hero counts the months over budget, and
    // each installment finds its "หมด" month (UI-42, UI-43).
    getMonths(),
    // The plan's cards are extras: if it fails, Home still shows the debts.
    getAssistantPlan().catch(() => null),
    // The hero's buffer line is an extra too.
    getShortfalls().catch(() => null),
  ]);
  return { settings, summary, buffer, months, plan, shortfalls };
}

export function HomeScreen() {
  const [load, reload] = useLoad(loadHome);
  return (
    <Screen route="home">
      {/* Back to the host app's home; KidNee's logo stays in the header. */}
      <a
        href="#/account"
        className="-mt-1 -ml-1 inline-flex min-h-11 items-center gap-1 self-start rounded-field px-1 text-body font-semibold text-leaf-800 hover:underline"
      >
        <Icon name="back" size={20} />
        {HOME.toAccount}
      </a>
      {load.state === "loading" && <Loading lines={4} />}
      {load.state === "error" && <ErrorState onRetry={reload} />}
      {load.state === "ready" &&
        (load.data.settings === null ? (
          <SettingsMissing onSetUp={() => navigate("settings")} />
        ) : (
          <HomeBody {...load.data} />
        ))}
    </Screen>
  );
}

export function HomeBody({
  settings,
  summary,
  buffer,
  months,
  plan,
  shortfalls,
}: {
  settings: SettingsOut;
  summary: DebtSummary;
  buffer: BufferOut;
  months: MonthsOut;
  plan: AssistantPlanOut | null;
  shortfalls: ShortfallsOut | null;
}) {
  const view = homeView({ months: months.months, plan, buffer, shortfalls });
  const name = currentPersona().name;
  const counted = summary.installments.filter((line) => lineStatus(line).counted);
  const finished = summary.installments.filter((line) => !lineStatus(line).counted && line.status === "paid_off");
  // Cancelled, or reported "not me": not counted either, but never under "ผ่อนครบแล้ว".
  const others = summary.installments.filter((line) => !lineStatus(line).counted && line.status !== "paid_off");
  return (
    <>
      <p className="text-lead font-semibold text-ink">{name === null ? HOME.greetingPlain : HOME.greeting(name)}</p>

      {view.hero !== null && <Hero hero={view.hero} budget={settings.monthly_installment_budget} />}

      <div className="flex flex-col gap-2">
        <Button size="lg" icon="think" onClick={() => navigate("think")}>
          {HOME.thinkCta}
        </Button>
        <p className="text-center text-body text-ink-muted">{HOME.thinkCtaHelp}</p>
      </div>

      <Wallet wallet={view.wallet} />

      {view.assistant && plan !== null && <AiBubbleCard plan={plan} />}

      {view.consolidation !== null && <ConsolidationCard view={view.consolidation} />}

      {/* Reference, lowest emphasis: flat, no shadow. */}
      <section className="flex flex-col gap-3 rounded-card border border-line bg-card p-5">
        <div className="flex flex-col">
          <h2 className="text-lead font-bold text-ink">{HOME.installments}</h2>
          <span className="text-body text-ink-muted">{HOME.totalPerMonth(formatBaht(summary.monthly_total))}</span>
        </div>
        {summary.installments.length === 0 ? (
          <p className="text-body text-ink-muted">{HOME.emptyInstallments}</p>
        ) : (
          <>
            {groupByPlatform(counted).map((group) => (
              <div key={group.label} className="flex flex-col">
                <h3 className="flex items-center gap-2 pt-2 text-body font-bold text-leaf-800">
                  <Icon name="wallet" size={18} />
                  {group.label}
                </h3>
                <ul className="flex flex-col divide-y divide-line">
                  {group.lines.map((line) => (
                    <InstallmentRow key={line.id} line={line} schedule={scheduleText(line.id, months.months)} />
                  ))}
                </ul>
              </div>
            ))}
            {others.length > 0 && (
              <>
                <h3 className="pt-2 text-body font-semibold text-ink-muted">{HOME.notCounted}</h3>
                <ul className="flex flex-col divide-y divide-line">
                  {others.map((line) => (
                    <InstallmentRow key={line.id} line={line} schedule={null} />
                  ))}
                </ul>
              </>
            )}
            {finished.length > 0 && <Finished lines={finished} />}
          </>
        )}
      </section>
    </>
  );
}

/**
 * The largest card, one card (UI-42): this month's total, the bar against the budget,
 * one status or warning line, and one buffer line. The whole card opens the months
 * (its button's ::after covers the card); the buffer link sits above that cover.
 */
function Hero({ hero, budget }: { hero: HeroView; budget: Money }) {
  const buffer = hero.buffer;
  return (
    <section className="relative flex flex-col gap-3 rounded-card bg-card p-6 shadow-card has-[>button:hover]:bg-leaf-50">
      <button
        type="button"
        onClick={() => navigate("months")}
        className="flex cursor-pointer flex-col gap-3 text-left after:absolute after:inset-0 after:rounded-card focus-visible:outline-none focus-visible:after:outline-2 focus-visible:after:outline-offset-[-2px] focus-visible:after:outline-leaf-600"
      >
        <span className="flex items-center justify-between gap-2">
          <span className="text-body text-ink-muted">{HOME.thisMonthTitle(thaiMonth(hero.month))}</span>
          <Icon name="next" size={24} className="text-leaf-800" />
          <span className="sr-only">{HOME.seeAllMonths}</span>
        </span>
        {/* Inside a button: spans only (phrasing content). */}
        <span className="text-display font-bold text-ink">{formatBaht(hero.total)}</span>
        <span className="text-body text-ink-muted">{HOME.ofBudget(formatBaht(budget))}</span>
        <BudgetBar hero={hero} budget={budget} />
        {hero.line !== null && <MarkedText item={hero.line} className="font-semibold" />}
        {hero.warning !== null && <MarkedText item={hero.warning} className="font-semibold" />}
      </button>
      {buffer !== null && (
        <div className="flex flex-col gap-2">
          <MarkedText item={buffer.line} className="font-semibold" />
          {buffer.prepare !== null && (
            // Above the card's cover: it opens the buffer at this month, never the months.
            <div className="relative">
              <Button
                variant="buffer"
                icon={ACCENT.buffer.icon}
                onClick={() => {
                  openBufferAt(buffer.month);
                  navigate("buffer");
                }}
              >
                {BUFFER_STATE.use}
              </Button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

/**
 * This month against the budget on one scale, the larger of the two: green up to the
 * budget, then teal for what was moved from the buffer for this month and amber (red
 * over one third of income) for the gap left, and a mark where the budget is (UI-42,
 * UI-53). The parts are barSegments of this month's own shortfall row, never the first
 * month over budget. Widths come from barPermille (exact, BigInt); the flags are the API's.
 */
function BudgetBar({ hero, budget }: { hero: HeroView; budget: Money }) {
  const scale = largest([budget, hero.total]);
  const mark = barPermille(budget, scale) / 10;
  const segments = barSegments({
    total: hero.total,
    budget,
    scale,
    row: hero.barRow,
    overBudget: hero.barOver,
    overOneThird: hero.overOneThird,
  });
  return (
    <span className="relative my-1 block h-3 rounded-pill bg-leaf-50" role="presentation">
      <BarParts segments={segments} />
      {/* A white halo: ink on the buffer's teal alone is under 3:1 (UI-35). */}
      <span className="absolute -inset-y-1 w-0.5 -translate-x-1/2 rounded-pill bg-ink ring-1 ring-card" style={{ left: `${mark}%` }} />
    </span>
  );
}

/**
 * The buffer as a wallet: shield, label and balance on the left, months covered on the
 * right. Framed in `EDGE.buffer` (at least 3:1, UI-35), like the buffer screen's card.
 */
function Wallet({ wallet }: { wallet: WalletView }) {
  return (
    <button
      type="button"
      onClick={() => navigate("buffer")}
      className={`flex w-full cursor-pointer items-center gap-3 rounded-card p-4 text-left hover:shadow-card active:opacity-90 focus-visible:outline-2 focus-visible:outline-leaf-600 ${ACCENT.buffer.tint} ${EDGE.buffer}`}
    >
      <span className={`inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-pill ${SOLID.buffer}`}>
        <Icon name={wallet.title.icon} size={26} />
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className={`text-body font-semibold ${ACCENT[wallet.title.accent].ink}`}>{wallet.title.text}</span>
        <span className="text-title font-bold text-ink">{formatBaht(wallet.balance)}</span>
      </span>
      <span className="flex shrink-0 flex-col items-end gap-1.5">
        {/* One segment per month covered; the caption says it in words. */}
        <span aria-hidden="true" className="flex gap-1">
          {Array.from({ length: WALLET_SEGMENTS }, (_, i) => (
            <span key={i} className={`h-5 w-2.5 rounded-sm ${i < wallet.filled ? BUFFER_METER.on : BUFFER_METER.off}`} />
          ))}
        </span>
        <span className={`text-body font-semibold ${ACCENT.buffer.ink}`}>{wallet.caption}</span>
      </span>
    </button>
  );
}

function InstallmentRow({ line, schedule }: { line: InstallmentLine; schedule: string | null }) {
  const { label, counted } = lineStatus(line);
  return (
    <li className="flex items-start justify-between gap-3 py-3">
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-body font-semibold text-ink">{line.item_name || HOME.unnamed}</span>
        <span className="text-caption text-ink-muted">
          {line.platform_name !== null && !counted ? `${line.platform_name} · ` : ""}
          <WholeParts text={schedule ?? HOME.monthsLeft(line.months)} />
        </span>
        {label !== null && (
          <span className="mt-1 inline-flex items-center gap-1 self-start rounded-pill bg-info-bg px-2 py-0.5 text-caption font-semibold text-info-ink">
            <Icon name="info" size={14} />
            {label}
          </span>
        )}
      </div>
      <div className="flex shrink-0 flex-col items-end">
        <span className="text-body font-semibold text-ink">{HOME.perMonth(formatBaht(line.monthly_amount))}</span>
        <span className="text-caption text-ink-muted">{HOME.remaining(formatBaht(line.remaining))}</span>
      </div>
    </li>
  );
}

/** "งวดที่ 4 จาก 6 · หมด ธ.ค. 2569": a line breaks only at the dot, so "หมด ธ.ค. 2569" stays whole. */
function WholeParts({ text }: { text: string }) {
  return text.split(" · ").map((part, i) => (
    <Fragment key={i}>
      {i > 0 && " · "}
      <span className="whitespace-nowrap">{part}</span>
    </Fragment>
  ));
}

/** Paid off: one line "ผ่อนครบแล้ว {n} รายการ" that opens to the names, each with a check (UI-43). */
function Finished({ lines }: { lines: InstallmentLine[] }) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  return (
    <div className="flex flex-col border-t border-line pt-1">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen(!open)}
        className="flex min-h-11 cursor-pointer items-center justify-between gap-2 text-left text-body font-semibold text-ink-muted hover:text-ink"
      >
        {HOME.finished(lines.length)}
        <Icon name={open ? "down" : "next"} size={20} />
      </button>
      <ul id={listId} hidden={!open} className="flex flex-col divide-y divide-line">
        {lines.map((line) => (
          <li key={line.id} className="flex items-center gap-2 py-2.5">
            <Icon name="check" size={18} className="text-ok-ink" />
            <span className="truncate text-body text-ink">{line.item_name || HOME.unnamed}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
