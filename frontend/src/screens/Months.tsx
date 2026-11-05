/**
 * "ภาระผ่อนรายเดือน" (DESIGN.md section 7.2b), opened from Home's this-month card.
 * Every month from this month to the last month with an installment: the total
 * against the budget, a bar, and the status as icon + text. Tap a month for its
 * installments ("งวดที่ x จาก y", "งวดสุดท้าย"). A month over budget says whether
 * money was moved from the buffer for it (GET /buffer/shortfalls, UI-46). One quiet
 * line at the bottom says what to do when the app's amount differs (UI-48). All
 * numbers come from the API; nothing is added up here.
 */
import { useState } from "react";
import { getAssistantPlan, getMonths, getSettings, getShortfalls } from "../api.ts";
import type { AssistantPlanOut, MonthDetail, MonthsOut, SettingsOut, ShortfallsOut } from "../api-types.ts";
import { ACCENT } from "../accent.ts";
import { planLines } from "../assistantText.ts";
import { barSegments } from "../barSegments.ts";
import { openBufferAt, shortfallsByMonth, type ShortfallView } from "../bufferState.ts";
import { ASSIST, BUFFER_STATE, HOME, MONTHS_VIEW } from "../copy.ts";
import { BarParts } from "../components/BarParts.tsx";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Button, Card, ErrorState, Loading, MarkedText, SettingsMissing, StatusChip } from "../components/ui.tsx";
import { monthChip } from "../monthStatus.ts";
import { barPermille, formatBaht, largest, type Money } from "../money.ts";
import { navigate } from "../router.ts";
import { thaiMonth } from "../thaiMonth.ts";
import { useLoad } from "../useLoad.ts";

type MonthsData = { settings: SettingsOut; months: MonthsOut; plan: AssistantPlanOut | null; shortfalls: ShortfallsOut | null };

async function loadMonths(): Promise<MonthsData | null> {
  const settings = await getSettings();
  if (settings === null) return null;
  // The plan and the buffer states are extras: the months show without them.
  const [months, plan, shortfalls] = await Promise.all([
    getMonths(),
    getAssistantPlan().catch(() => null),
    getShortfalls().catch(() => null),
  ]);
  return { settings, months, plan, shortfalls };
}

export function MonthsScreen() {
  const [load, reload] = useLoad(loadMonths);
  return (
    <Screen route="months" title={MONTHS_VIEW.title} back="home">
      {load.state === "loading" && <Loading lines={4} />}
      {load.state === "error" && <ErrorState onRetry={reload} />}
      {load.state === "ready" &&
        (load.data === null ? (
          <SettingsMissing onSetUp={() => navigate("settings")} />
        ) : (
          <>
            {load.data.plan !== null && <PlanCard plan={load.data.plan} />}
            <MonthList
              months={load.data.months.months}
              budget={load.data.settings.monthly_installment_budget}
              buffer={shortfallsByMonth(load.data.shortfalls)}
            />
            <p className="px-1 pt-2 text-caption text-ink-muted">{MONTHS_VIEW.scamCheck}</p>
          </>
        ))}
    </Screen>
  );
}

/** From GET /assistant/plan: back in budget, and how much more fits (L69: no ranking of debts). */
function PlanCard({ plan }: { plan: AssistantPlanOut }) {
  const lines = planLines(plan);
  return (
    <Card className={`flex flex-col gap-2 border-2 ${lines.pauseNow ? "border-warn-line" : "border-transparent"}`}>
      <p className="flex items-center gap-2 text-lead font-bold text-ink">
        <Icon name={plan.back_in_budget_month === null ? "check" : "calendar"} size={22} className="text-leaf-700" />
        {lines.back}
      </p>
      <p className={`flex items-start gap-2 text-body ${lines.pauseNow ? "font-semibold text-warn-ink" : "text-ink"}`}>
        <Icon name={lines.pauseNow ? "alert" : "info"} size={20} className="mt-0.5" />
        {lines.safe}
      </p>
      <p className="text-caption text-ink-muted">{ASSIST.safeTerm(plan.safe_new_months)}</p>
    </Card>
  );
}

export function MonthList({ months, budget, buffer }: { months: MonthDetail[]; budget: Money; buffer: ReadonlyMap<string, ShortfallView> }) {
  const [open, setOpen] = useState<string | null>(null);
  if (months.length === 0) {
    return (
      <Card>
        <p className="text-body text-ink">{MONTHS_VIEW.empty}</p>
      </Card>
    );
  }
  // One scale for every bar, so months compare at a glance; the budget mark sits on it.
  const scale = largest([budget, ...months.map((m) => m.total)]);
  const budgetMark = barPermille(budget, scale) / 10;
  return (
    <>
      <p className="text-body text-ink-muted">{MONTHS_VIEW.intro}</p>
      <ul className="flex flex-col gap-3">
        {months.map((month) => (
          <MonthCard
            key={month.month}
            month={month}
            budget={budget}
            scale={scale}
            budgetMark={budgetMark}
            buffer={buffer.get(month.month) ?? null}
            expanded={open === month.month}
            onToggle={() => setOpen((o) => (o === month.month ? null : month.month))}
          />
        ))}
      </ul>
    </>
  );
}

type MonthCardProps = {
  month: MonthDetail;
  budget: Money;
  scale: Money;
  budgetMark: number;
  buffer: ShortfallView | null; // over budget: the buffer state (UI-46)
  expanded: boolean;
  onToggle: () => void;
};

function MonthCard({ month, budget, scale, budgetMark, buffer, expanded, onToggle }: MonthCardProps) {
  const chip = monthChip(month, buffer?.state ?? null);
  const segments = barSegments({
    total: month.total,
    budget,
    scale,
    row: buffer?.row ?? null,
    overBudget: month.over_budget,
    overOneThird: month.over_one_third,
  });
  const panelId = `month-${month.month}`;
  return (
    <li className="overflow-hidden rounded-card bg-card shadow-card">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={panelId}
        className="flex w-full cursor-pointer flex-col gap-2 p-4 text-left hover:bg-leaf-50 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-leaf-600"
      >
        <span className="flex items-center justify-between gap-2">
          <span className="text-lead font-bold text-ink">{thaiMonth(month.month)}</span>
          <StatusChip chip={chip} />
        </span>
        <span className="text-body text-ink">{MONTHS_VIEW.ofBudget(formatBaht(month.total), formatBaht(budget))}</span>
        {/* Over one third of income: a red ring, whatever the buffer covered (the chip says why). */}
        <span
          className={`relative block h-3 rounded-pill bg-leaf-50${month.over_one_third ? " ring-2 ring-bar-risk ring-offset-1 ring-offset-card" : ""}`}
          role="presentation"
        >
          <BarParts segments={segments} />
          <span
            className="absolute -top-1 -bottom-1 w-0.5 bg-ink-muted ring-1 ring-card"
            style={{ left: `calc(${budgetMark}% - 1px)` }}
          />
        </span>
        <span className="flex items-center gap-1 text-body font-semibold text-leaf-800">
          {expanded ? MONTHS_VIEW.hideItems : MONTHS_VIEW.showItems}
          <Icon name="down" size={18} className={expanded ? "rotate-180" : ""} />
        </span>
      </button>
      {buffer !== null && (
        <div className="flex flex-col gap-2 px-4 pb-4">
          <MarkedText item={buffer.line} className="font-semibold" />
          {buffer.prepare !== null && (
            <Button
              variant="bufferOutline"
              icon={ACCENT.buffer.icon}
              onClick={() => {
                openBufferAt(month.month);
                navigate("buffer");
              }}
            >
              {BUFFER_STATE.use}
            </Button>
          )}
        </div>
      )}
      {expanded && (
        <ul id={panelId} className="flex flex-col divide-y divide-line border-t border-line px-4">
          {month.installments.map((item) => (
            <li key={item.installment_id} className="flex items-start justify-between gap-3 py-3">
              <span className="flex min-w-0 flex-col">
                <span className="truncate text-body font-semibold text-ink">
                  {item.item_name || HOME.unnamed}
                  {item.platform_name !== null && <span className="font-normal text-ink-muted"> · {item.platform_name}</span>}
                </span>
                <span className="text-caption text-ink-muted">
                  {MONTHS_VIEW.instalmentOf(item.installment_no, item.installments_total)}
                </span>
                {item.is_last && (
                  <span className="mt-1 inline-flex items-center gap-1 self-start rounded-pill bg-ok-bg px-2 py-0.5 text-caption font-semibold text-ok-ink">
                    <Icon name="check" size={14} />
                    {MONTHS_VIEW.lastInstalment}
                  </span>
                )}
              </span>
              <span className="shrink-0 text-body font-semibold text-ink">{formatBaht(item.monthly_amount)}</span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
