/**
 * "ภาระผ่อนรายเดือน" (DESIGN.md section 7.2b), opened from Home's this-month card.
 * Every month from this month to the last month with an installment: the total
 * against the budget, a bar, and the status as icon + text. Tap a month for its
 * installments ("งวดที่ x จาก y", "งวดสุดท้าย"). All numbers come from the API
 * (TODO(backend): GET /debts/months); nothing is added up here.
 */
import { useState } from "react";
import { getMonths, getSettings } from "../api.ts";
import type { MonthDetail, MonthsOut, SettingsOut } from "../api-types.ts";
import { HOME, MONTHS_VIEW } from "../copy.ts";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Card, ErrorState, Loading, SettingsMissing } from "../components/ui.tsx";
import { monthStatus, type MonthStatus } from "../monthStatus.ts";
import { barPermille, formatBaht, largest, type Money } from "../money.ts";
import { navigate } from "../router.ts";
import { thaiMonth } from "../thaiMonth.ts";
import { useLoad } from "../useLoad.ts";

async function loadMonths(): Promise<{ settings: SettingsOut; months: MonthsOut } | null> {
  const settings = await getSettings();
  if (settings === null) return null;
  return { settings, months: await getMonths() };
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
          <MonthList months={load.data.months.months} budget={load.data.settings.monthly_installment_budget} />
        ))}
    </Screen>
  );
}

const TONE: Record<MonthStatus["tone"], { text: string; bar: string; chip: string }> = {
  ok: { text: "text-ok-ink", bar: "bg-bar-ok", chip: "bg-ok-bg text-ok-ink" },
  over: { text: "text-warn-ink", bar: "bg-bar-over", chip: "bg-warn-bg text-warn-ink" },
  risk: { text: "text-risk-ink", bar: "bg-bar-risk", chip: "bg-risk-bg text-risk-ink" },
};

function MonthList({ months, budget }: { months: MonthDetail[]; budget: Money }) {
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
  expanded: boolean;
  onToggle: () => void;
};

function MonthCard({ month, budget, scale, budgetMark, expanded, onToggle }: MonthCardProps) {
  const status = monthStatus(month);
  const tone = TONE[status.tone];
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
          <span className={`inline-flex items-center gap-1 rounded-pill px-2.5 py-0.5 text-caption font-semibold ${tone.chip}`}>
            <Icon name={status.icon} size={16} />
            {status.label}
          </span>
        </span>
        <span className="text-body text-ink">{MONTHS_VIEW.ofBudget(formatBaht(month.total), formatBaht(budget))}</span>
        <span className="relative block h-3 rounded-pill bg-leaf-50" role="presentation">
          <span
            className={`block h-full rounded-pill ${tone.bar}`}
            style={{ width: `${barPermille(month.total, scale) / 10}%` }}
          />
          <span
            className="absolute -top-1 -bottom-1 w-0.5 bg-ink-muted"
            style={{ left: `calc(${budgetMark}% - 1px)` }}
          />
        </span>
        <span className="flex items-center gap-1 text-body font-semibold text-leaf-800">
          {expanded ? MONTHS_VIEW.hideItems : MONTHS_VIEW.showItems}
          <Icon name="down" size={18} className={expanded ? "rotate-180" : ""} />
        </span>
      </button>
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
