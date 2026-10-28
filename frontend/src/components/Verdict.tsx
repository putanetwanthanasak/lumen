/**
 * The verdict card and the month bars (DESIGN.md sections 5.3 and 5.4).
 *
 * The verdict is never colour only: icon + Thai label + a sentence. The bars are solid;
 * a month above a third of income also has a ⚠ marker, the legend names each colour, a
 * plain line says which months are over budget, and every month is listed in a table
 * for screen readers. Bar heights come from barPermille (exact, BigInt); no amount is
 * computed here.
 */
import type { CSSProperties } from "react";
import type { MonthRow, Verdict } from "../api-types.ts";
import { ADVISORY_NOTE, THINK, VERDICT } from "../copy.ts";
import { barPermille, formatBaht, largest, type Money } from "../money.ts";
import { overRange } from "../monthStatus.ts";
import { thaiMonth, thaiMonthShort } from "../thaiMonth.ts";
import { Icon } from "./Icon.tsx";
import { KeepMonths } from "./ui.tsx";

const VERDICT_STYLE: Record<Verdict, { box: string; badge: string }> = {
  GREEN: { box: "bg-ok-bg border-ok-line text-ok-ink", badge: "bg-leaf-700 text-white" },
  YELLOW: { box: "bg-warn-bg border-warn-line text-warn-ink", badge: "bg-warn-line text-warn-ink" },
  RED: { box: "bg-risk-bg border-risk-line text-risk-ink", badge: "bg-risk-ink text-white" },
};

/** "hero" is the result screen's large card: a bigger icon and label, the same words. */
export function VerdictCard({ verdict, size = "md" }: { verdict: Verdict; size?: "md" | "hero" }) {
  const copy = VERDICT[verdict];
  const style = VERDICT_STYLE[verdict];
  const hero = size === "hero";
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex flex-col rounded-card border-2 ${hero ? "gap-4 px-5 py-6 shadow-card" : "gap-3 p-5"} ${style.box}`}
    >
      <div className={`flex items-center ${hero ? "gap-4" : "gap-3"}`}>
        <span
          className={`inline-flex shrink-0 items-center justify-center rounded-pill ${style.badge} ${hero ? "h-16 w-16" : "h-12 w-12"}`}
        >
          <Icon name={copy.icon} size={hero ? 36 : 28} />
        </span>
        <VerdictLabel label={copy.label} hero={hero} />
      </div>
      <p className="text-body">{copy.detail}</p>
      <p className="text-body">{ADVISORY_NOTE}</p>
    </div>
  );
}

/** "เกินเกณฑ์ที่ ธปท. แนะนำ (1 ใน 3 ของรายได้)" breaks before the brackets, never inside them. */
function VerdictLabel({ label, hero }: { label: string; hero: boolean }) {
  const at = label.indexOf(" (");
  const size = hero ? "text-display" : "text-title";
  if (at === -1) return <p className={`${size} font-bold`}>{label}</p>;
  return (
    <p className="flex flex-col">
      <span className={`${hero ? "text-title" : "text-lead"} font-bold`}>{label.slice(0, at)}</span>
      <span className="text-body font-semibold whitespace-nowrap">{label.slice(at + 1)}</span>
    </p>
  );
}

/** A bar's colours by the API's flags: solid for the month, a pale tint for this item's share. */
const BAR: Record<"ok" | "over" | "risk", { solid: string; share: string }> = {
  ok: { solid: "bg-bar-ok", share: "border-bar-ok bg-leaf-100" },
  over: { solid: "bg-bar-over", share: "border-bar-over bg-warn-bg" },
  risk: { solid: "bg-bar-risk", share: "border-bar-risk bg-risk-bg" },
};

const barTone = (row: MonthRow) => (row.over_one_third ? "risk" : row.over_budget ? "over" : "ok");

// The widest Thai month label is about 29px at 14px (34px with other system fonts), and
// the chart is 298px wide in the 370px frame: up to 7 months, every label fits with
// room between; beyond that, every k-th month gets one, centred under its own bar.
const LABELLED_MONTHS = 7;

/** Every how many months a label shows, so no label clips or touches the next (UI-40). */
export function labelStep(months: number): number {
  return months <= LABELLED_MONTHS ? 1 : Math.ceil(months / LABELLED_MONTHS); // ui-06-allow: a count of months
}

type BarsProps = { months: MonthRow[]; budget: Money; candidate?: Money | null; caption?: string };

/**
 * Bars, labels and the budget line share one grid of equal columns, so each label sits
 * under its own bar at any number of months, and nothing overflows the card (UI-40).
 * `candidate` is this item's monthly amount: the pale top of each bar. Every row of
 * the preview includes it (L65); its height is a share of the bar, never an amount.
 */
export function MonthBars({ months, budget, candidate = null, caption = THINK.monthsTitle }: BarsProps) {
  const scale = largest([budget, ...months.map((m) => m.total)]);
  const step = labelStep(months.length);
  const over = overRange(months);
  const grid: CSSProperties = { gridTemplateColumns: `repeat(${months.length}, minmax(0, 1fr))` };
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="text-body font-semibold text-ink">{caption}</figcaption>
      {/* pt-6: room for the marker above the tallest bar. */}
      <div className="grid grid-rows-[10rem_auto] pt-6" style={grid} aria-hidden="true">
        <div
          className="col-span-full row-start-1 self-end border-t-2 border-dashed border-ink-muted"
          style={{ height: `${barPermille(budget, scale) / 10}%` }}
        />
        {months.map((row, i) => {
          const tone = BAR[barTone(row)];
          return (
            <div
              key={row.month}
              className={`relative row-start-1 flex w-4/5 flex-col self-end justify-self-center rounded-t-md ${tone.solid}`}
              style={{
                gridColumn: i + 1,
                height: `${Math.max(barPermille(row.total, scale) / 10, 2)}%`, // ui-06-allow: a drawing size
              }}
            >
              {candidate !== null && (
                <div
                  className={`shrink-0 rounded-t-md border-2 border-b-0 ${tone.share}`}
                  style={{ height: `${barPermille(candidate, row.total) / 10}%` }}
                />
              )}
              {/* At most 16px and never wider than its bar: the markers of a run of such months never overlap. */}
              {row.over_one_third && (
                <Icon name="alert" size={16} className="absolute bottom-full left-1/2 mb-1 h-auto w-full max-w-4 -translate-x-1/2 text-risk-ink" />
              )}
            </div>
          );
        })}
        {months.map((row, i) =>
          i % step === 0 ? (
            <span
              key={row.month}
              className="row-start-2 justify-self-center pt-1.5 text-caption whitespace-nowrap text-ink-muted"
              style={{ gridColumn: i + 1 }}
            >
              {thaiMonthShort(row.month)}
            </span>
          ) : null,
        )}
      </div>
      <p className="text-body text-ink-muted">{THINK.budgetLine(formatBaht(budget))}</p>
      {/* Plain: the verdict card above holds the warning (UI-41). */}
      {over !== null && (
        <p className="text-body text-ink">
          <KeepMonths text={THINK.overSummary(over.count, thaiMonth(over.first), thaiMonth(over.last), over.together)} />
        </p>
      )}
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-caption text-ink-muted" aria-hidden="true">
        <li className="flex items-center gap-1.5">
          <span className={`inline-block h-3 w-3 rounded-sm ${BAR.ok.solid}`} />
          {THINK.legendOk}
        </li>
        <li className="flex items-center gap-1.5">
          <span className={`inline-block h-3 w-3 rounded-sm ${BAR.over.solid}`} />
          {THINK.legendOver}
        </li>
        <li className="flex items-center gap-1.5">
          <span className={`inline-block h-3 w-3 rounded-sm ${BAR.risk.solid}`} />
          <Icon name="alert" size={14} className="text-risk-ink" />
          {THINK.legendRisk}
        </li>
        {candidate !== null && (
          <li className="flex items-center gap-1.5">
            <span className="inline-flex h-4 w-3 flex-col overflow-hidden rounded-t-sm">
              <span className={`h-1/2 border-2 border-b-0 ${BAR.ok.share}`} />
              <span className={`flex-1 ${BAR.ok.solid}`} />
            </span>
            {THINK.legendCandidate}
          </li>
        )}
      </ul>
      <table className="sr-only">
        <caption>{caption}</caption>
        <tbody>
          {months.map((row) => (
            <tr key={row.month}>
              <th scope="row">{thaiMonth(row.month)}</th>
              <td>{formatBaht(row.total)}</td>
              <td>
                {row.over_one_third ? THINK.legendRisk : row.over_budget ? THINK.legendOver : THINK.legendOk}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
