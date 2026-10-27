/**
 * Screen 2: Home, the debt overview (DESIGN.md section 7.2).
 * This month's total against the budget, the คิดก่อน button, upcoming over-budget
 * months, the buffer, and every installment. All amounts are API strings.
 */
import { getBuffer, getDebtSummary, getSettings, getUpcomingMonths, USE_MOCK } from "../api.ts";
import type { BufferOut, DebtSummary, InstallmentLine, SettingsOut, UpcomingMonthsOut } from "../api-types.ts";
import { HOME } from "../copy.ts";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Button, Card, ErrorState, Loading, SettingsMissing } from "../components/ui.tsx";
import { lineStatus } from "../installmentStatus.ts";
import { PERSONA_NAME } from "../mock/persona.ts";
import { barPermille, formatBaht } from "../money.ts";
import { navigate } from "../router.ts";
import { thaiMonth } from "../thaiMonth.ts";
import { useLoad } from "../useLoad.ts";

type HomeData =
  | { settings: null }
  | { settings: SettingsOut; summary: DebtSummary; buffer: BufferOut; upcoming: UpcomingMonthsOut };

async function loadHome(): Promise<HomeData> {
  const settings = await getSettings();
  if (settings === null) return { settings: null };
  const [summary, buffer, upcoming] = await Promise.all([getDebtSummary(), getBuffer(), getUpcomingMonths()]);
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
  upcoming: UpcomingMonthsOut;
}) {
  const [thisMonth, ...later] = upcoming.months;
  const overLater = later.filter((m) => m.over_budget);
  const budget = settings.monthly_installment_budget;
  return (
    <>
      <p className="text-lead font-semibold text-ink">{USE_MOCK ? HOME.greeting(PERSONA_NAME) : HOME.greetingPlain}</p>

      {thisMonth !== undefined && (
        <Card className="flex flex-col gap-3">
          <p className="text-body text-ink-muted">
            {HOME.thisMonthTitle(thaiMonth(thisMonth.month))}
          </p>
          <p className="text-display font-bold text-ink">{formatBaht(thisMonth.total)}</p>
          <p className="text-body text-ink-muted">{HOME.ofBudget(formatBaht(budget))}</p>
          <div
            className="h-3 overflow-hidden rounded-pill bg-leaf-50"
            role="presentation"
          >
            <div
              className={`h-full rounded-pill ${thisMonth.over_budget ? "bg-bar-over" : "bg-bar-ok"}`}
              style={{ width: `${barPermille(thisMonth.total, budget) / 10}%` }}
            />
          </div>
          <p
            className={`flex items-center gap-2 text-body font-semibold ${
              thisMonth.over_budget ? "text-warn-ink" : "text-ok-ink"
            }`}
          >
            <Icon name={thisMonth.over_budget ? "alert" : "check"} size={20} />
            {thisMonth.over_budget ? HOME.overBudgetNow : HOME.withinBudgetNow}
          </p>
        </Card>
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
            <ul className="flex flex-col divide-y divide-line">
              {summary.installments
                .filter((line) => lineStatus(line).counted)
                .map((line) => (
                  <InstallmentRow key={line.id} line={line} />
                ))}
            </ul>
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

const VENDOR_NAMES: Record<string, string> = { shopdemo: "ShopDemo" };

function InstallmentRow({ line }: { line: InstallmentLine }) {
  const source = line.vendor === "manual" ? HOME.manual : (VENDOR_NAMES[line.vendor] ?? line.vendor);
  const { label } = lineStatus(line);
  return (
    <li className="flex items-start justify-between gap-3 py-3">
      <div className="flex min-w-0 flex-col">
        <span className="truncate text-body font-semibold text-ink">{line.item_name || HOME.unnamed}</span>
        <span className="text-caption text-ink-muted">
          {source} · {HOME.monthsLeft(line.months)}
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
