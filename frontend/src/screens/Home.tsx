/**
 * Screen 2: Home, the debt overview (DESIGN.md section 7.2).
 * This month's total against the budget (tap for every month), the ตรวจสอบก่อนผ่อน
 * button, upcoming over-budget months, the buffer, and every installment grouped by
 * the app the user named. All amounts are API strings.
 */
import { getBuffer, getDebtSummary, getMonths, getSettings, USE_MOCK } from "../api.ts";
import type { BufferOut, DebtSummary, InstallmentLine, MonthsOut, SettingsOut } from "../api-types.ts";
import { HOME, PAYOFF } from "../copy.ts";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Button, Card, ErrorState, Loading, SettingsMissing } from "../components/ui.tsx";
import { groupByPlatform, lineStatus } from "../installmentStatus.ts";
import { PERSONA_NAME } from "../mock/persona.ts";
import { barPermille, formatBaht } from "../money.ts";
import { navigate } from "../router.ts";
import { thaiMonth } from "../thaiMonth.ts";
import { useLoad } from "../useLoad.ts";

const UPCOMING_MONTHS = 6; // this month and the next five

type HomeData =
  | { settings: null }
  | { settings: SettingsOut; summary: DebtSummary; buffer: BufferOut; upcoming: MonthsOut };

async function loadHome(): Promise<HomeData> {
  const settings = await getSettings();
  if (settings === null) return { settings: null };
  const [summary, buffer, upcoming] = await Promise.all([getDebtSummary(), getBuffer(), getMonths(UPCOMING_MONTHS)]);
  return { settings, summary, buffer, upcoming };
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
}: {
  settings: SettingsOut;
  summary: DebtSummary;
  buffer: BufferOut;
  upcoming: MonthsOut;
}) {
  const [thisMonth, ...later] = upcoming.months;
  const overLater = later.filter((m) => m.over_budget);
  const budget = settings.monthly_installment_budget;
  return (
    <>
      <p className="text-lead font-semibold text-ink">{USE_MOCK ? HOME.greeting(PERSONA_NAME) : HOME.greetingPlain}</p>

      {thisMonth !== undefined && (
        <button
          type="button"
          onClick={() => navigate("months")}
          className="flex cursor-pointer flex-col gap-3 rounded-card bg-card p-5 text-left shadow-card hover:bg-leaf-50 focus-visible:outline-2 focus-visible:outline-leaf-600"
        >
          <span className="flex items-center justify-between gap-2">
            <span className="text-body text-ink-muted">{HOME.thisMonthTitle(thaiMonth(thisMonth.month))}</span>
            <span className="text-body font-semibold text-leaf-800">{HOME.seeAllMonths}</span>
          </span>
          {/* Inside a button: spans only (phrasing content). */}
          <span className="text-display font-bold text-ink">{formatBaht(thisMonth.total)}</span>
          <span className="text-body text-ink-muted">{HOME.ofBudget(formatBaht(budget))}</span>
          <span className="block h-3 overflow-hidden rounded-pill bg-leaf-50" role="presentation">
            <span
              className={`block h-full rounded-pill ${thisMonth.over_budget ? "bg-bar-over" : "bg-bar-ok"}`}
              style={{ width: `${barPermille(thisMonth.total, budget) / 10}%` }}
            />
          </span>
          <span
            className={`flex items-center gap-2 text-body font-semibold ${
              thisMonth.over_budget ? "text-warn-ink" : "text-ok-ink"
            }`}
          >
            <Icon name={thisMonth.over_budget ? "alert" : "check"} size={20} />
            {thisMonth.over_budget ? HOME.overBudgetNow : HOME.withinBudgetNow}
          </span>
        </button>
      )}

      <div className="flex flex-col gap-2">
        <Button size="lg" icon="think" onClick={() => navigate("think")}>
          {HOME.thinkCta}
        </Button>
        <p className="text-center text-body text-ink-muted">{HOME.thinkCtaHelp}</p>
      </div>

      <Card className="flex flex-col gap-3">
        <h2 className="text-lead font-bold text-ink">{HOME.upcomingTitle}</h2>
        {overLater.length === 0 ? (
          <p className="flex items-center gap-2 text-body text-ok-ink">
            <Icon name="check" size={20} />
            {HOME.upcomingNone}
          </p>
        ) : (
          <ul className="flex flex-col divide-y divide-line">
            {overLater.map((m) => (
              <li key={m.month} className="flex items-center justify-between gap-3 py-2.5">
                <span className="flex items-center gap-2 text-body font-semibold text-warn-ink">
                  <Icon name="alert" size={20} />
                  {thaiMonth(m.month)}
                </span>
                <span className="text-body text-ink">{HOME.upcomingRow(formatBaht(m.total))}</span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <button
        type="button"
        onClick={() => navigate("payoff")}
        className="flex min-h-16 cursor-pointer items-center gap-4 rounded-card bg-card p-5 text-left shadow-card hover:bg-leaf-50"
      >
        <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-pill bg-leaf-50 text-leaf-700">
          <Icon name="route" size={28} />
        </span>
        <span className="flex flex-col">
          <span className="text-lead font-bold text-ink">{PAYOFF.entry}</span>
          <span className="text-body text-ink-muted">{PAYOFF.entryHelp}</span>
        </span>
      </button>

      <Card className="flex items-center gap-4">
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-pill bg-leaf-50 text-leaf-700">
          <Icon name="shield" size={28} />
        </span>
        <div className="flex flex-col">
          <h2 className="text-body text-ink-muted">{HOME.bufferTitle}</h2>
          <p className="text-title font-bold text-ink">{formatBaht(buffer.balance)}</p>
          <p className="text-body text-ink-muted">
            {buffer.months_covered === null ? HOME.bufferNothingOwed : HOME.bufferCovers(buffer.months_covered)}
          </p>
        </div>
      </Card>

      <Card className="flex flex-col gap-3">
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
      </Card>
    </>
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
