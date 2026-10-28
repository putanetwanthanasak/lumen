/**
 * Screen 2: Home, ภาพรวมหนี้ (DESIGN.md section 7.2). Card types, by importance:
 * the hero (this month against the budget, with the over-budget strip merged in),
 * the เช็กก่อนผ่อน button, the buffer wallet, the assistant's bubble, consolidation
 * (a one-line banner, or the bank's offer), and the installments list. Which card
 * shows and in which shape comes from homeLayout.ts (UI-33). All amounts are API strings.
 */
import { getAssistantPlan, getBuffer, getDebtSummary, getMonths, getSettings, USE_MOCK } from "../api.ts";
import type { AssistantPlanOut, BufferOut, DebtSummary, InstallmentLine, MonthsOut, SettingsOut } from "../api-types.ts";
import { ACCENT, BUFFER_METER, SOLID } from "../accent.ts";
import { HOME } from "../copy.ts";
import { AiBubbleCard, ConsolidationCard } from "../components/AssistantCards.tsx";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Button, ErrorState, Loading, MarkedText, SettingsMissing } from "../components/ui.tsx";
import { homeView, WALLET_SEGMENTS, type HeroView, type OverStrip, type WalletView } from "../homeLayout.ts";
import { groupByPlatform, lineStatus } from "../installmentStatus.ts";
import { PERSONA_NAME } from "../mock/persona.ts";
import { barPermille, formatBaht, type Money } from "../money.ts";
import { navigate } from "../router.ts";
import { thaiMonth } from "../thaiMonth.ts";
import { useLoad } from "../useLoad.ts";

const UPCOMING_MONTHS = 6; // this month and the next five

type HomeData =
  | { settings: null }
  | { settings: SettingsOut; summary: DebtSummary; buffer: BufferOut; upcoming: MonthsOut; plan: AssistantPlanOut | null };

async function loadHome(): Promise<HomeData> {
  const settings = await getSettings();
  if (settings === null) return { settings: null };
  const [summary, buffer, upcoming, plan] = await Promise.all([
    getDebtSummary(),
    getBuffer(),
    getMonths(UPCOMING_MONTHS),
    // The plan's cards are extras: if it fails, Home still shows the debts.
    getAssistantPlan().catch(() => null),
  ]);
  return { settings, summary, buffer, upcoming, plan };
}

export function HomeScreen() {
  const [load, reload] = useLoad(loadHome);
  return (
    <Screen route="home">
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

function HomeBody({
  settings,
  summary,
  buffer,
  upcoming,
  plan,
}: {
  settings: SettingsOut;
  summary: DebtSummary;
  buffer: BufferOut;
  upcoming: MonthsOut;
  plan: AssistantPlanOut | null;
}) {
  const view = homeView({ months: upcoming.months, plan, buffer, monthlyTotal: summary.monthly_total });
  return (
    <>
      <p className="text-lead font-semibold text-ink">{USE_MOCK ? HOME.greeting(PERSONA_NAME) : HOME.greetingPlain}</p>

      {view.hero !== null && <Hero hero={view.hero} budget={settings.monthly_installment_budget} />}

      <div className="flex flex-col gap-2">
        <Button size="lg" icon="think" onClick={() => navigate("think")}>
          {HOME.thinkCta}
        </Button>
        <p className="text-center text-body text-ink-muted">{HOME.thinkCtaHelp}</p>
      </div>

      <Wallet wallet={view.wallet} />

      {view.assistant && <AiBubbleCard />}

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
            {groupByPlatform(summary.installments.filter((line) => lineStatus(line).counted)).map((group) => (
              <div key={group.label} className="flex flex-col">
                <h3 className="flex items-center gap-2 pt-2 text-body font-bold text-leaf-800">
                  <Icon name="wallet" size={18} />
                  {group.label}
                </h3>
                <ul className="flex flex-col divide-y divide-line">
                  {group.lines.map((line) => (
                    <InstallmentRow key={line.id} line={line} />
                  ))}
                </ul>
              </div>
            ))}
            {summary.installments.some((line) => !lineStatus(line).counted) && (
              <>
                <h3 className="pt-2 text-body font-semibold text-ink-muted">{HOME.notCounted}</h3>
                <ul className="flex flex-col divide-y divide-line opacity-80">
                  {summary.installments
                    .filter((line) => !lineStatus(line).counted)
                    .map((line) => (
                      <InstallmentRow key={line.id} line={line} />
                    ))}
                </ul>
              </>
            )}
          </>
        )}
      </section>
    </>
  );
}

/** The largest card: this month's total, the bar, and one status line or the over-budget strip. */
function Hero({ hero, budget }: { hero: HeroView; budget: Money }) {
  return (
    <section className="flex flex-col overflow-hidden rounded-card bg-card shadow-card">
      <button
        type="button"
        onClick={() => navigate("months")}
        className="flex cursor-pointer flex-col gap-3 p-6 text-left hover:bg-leaf-50 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-leaf-600"
      >
        <span className="flex items-center justify-between gap-2">
          <span className="text-body text-ink-muted">{HOME.thisMonthTitle(thaiMonth(hero.month))}</span>
          <span className="text-body font-semibold text-leaf-800">{HOME.seeAllMonths}</span>
        </span>
        {/* Inside a button: spans only (phrasing content). */}
        <span className="text-display font-bold text-ink">{formatBaht(hero.total)}</span>
        <span className="text-body text-ink-muted">{HOME.ofBudget(formatBaht(budget))}</span>
        <span className="block h-3 overflow-hidden rounded-pill bg-leaf-50" role="presentation">
          <span
            className={`block h-full rounded-pill ${hero.barOver ? "bg-bar-over" : "bg-bar-ok"}`}
            style={{ width: `${barPermille(hero.total, budget) / 10}%` }}
          />
        </span>
        <MarkedText item={hero.line} className="font-semibold" />
      </button>
      {hero.strip !== null && <Strip strip={hero.strip} />}
    </section>
  );
}

/** Amber, under the bar: each month over budget and by how much, and the buffer. */
function Strip({ strip }: { strip: OverStrip }) {
  return (
    <div className={`flex flex-col gap-3 border-t-2 px-6 py-4 ${ACCENT.warn.tint} ${ACCENT.warn.line}`}>
      <MarkedText item={strip.title} className="font-bold" />
      <ul className="grid grid-cols-2 gap-2">
        {strip.chips.map((chip) => (
          <li key={chip.month} className={`flex flex-col rounded-field border-2 bg-card px-3 py-1.5 ${ACCENT.warn.line}`}>
            <span className={`flex items-center gap-1.5 text-body font-semibold ${ACCENT[chip.accent].ink}`}>
              <Icon name={chip.icon} size={18} />
              {chip.text}
            </span>
            <span className="text-body font-bold text-ink">
              <span aria-hidden="true">{chip.amount}</span>
              <span className="sr-only">{chip.spoken}</span>
            </span>
          </li>
        ))}
      </ul>
      {strip.more !== null && <p className={`text-body font-semibold ${ACCENT.warn.ink}`}>{strip.more}</p>}
      {/* text-pretty: an amount's "บาท" never sits alone on the last line. */}
      {strip.shortfall !== null && <p className="text-body font-semibold text-pretty text-ink">{strip.shortfall}</p>}
      {strip.buffer !== null && <MarkedText item={strip.buffer} className="text-pretty" />}
      <Button
        variant={strip.link.accent === "buffer" ? "buffer" : "secondary"}
        icon={strip.link.icon}
        onClick={() => navigate(strip.link.route)}
      >
        {strip.link.text}
      </Button>
    </div>
  );
}

/** The buffer as a wallet: shield, label and balance on the left, months covered on the right. */
function Wallet({ wallet }: { wallet: WalletView }) {
  return (
    <button
      type="button"
      onClick={() => navigate("buffer")}
      className={`flex w-full cursor-pointer items-center gap-3 rounded-card border-2 p-4 text-left hover:shadow-card active:opacity-90 focus-visible:outline-2 focus-visible:outline-leaf-600 ${ACCENT.buffer.tint} ${ACCENT.buffer.line}`}
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

function InstallmentRow({ line }: { line: InstallmentLine }) {
  const { label } = lineStatus(line);
  return (
    <li className="flex items-start justify-between gap-3 py-3">
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-body font-semibold text-ink">{line.item_name || HOME.unnamed}</span>
        <span className="text-caption text-ink-muted">
          {line.platform_name !== null && !lineStatus(line).counted ? `${line.platform_name} · ` : ""}
          {HOME.monthsLeft(line.months)}
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
