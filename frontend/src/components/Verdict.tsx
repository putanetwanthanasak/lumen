/**
 * The verdict card and the month bars (DESIGN.md sections 5.3 and 5.4).
 *
 * The verdict is never colour only: icon + Thai label + a sentence. Over-budget bars
 * are also striped, and every month is listed in a table for screen readers.
 * Bar heights come from barPermille (exact, BigInt); no amount is computed here.
 */
import type { CSSProperties } from "react";
import type { MonthRow, Verdict } from "../api-types.ts";
import { ADVISORY_NOTE, THINK, VERDICT } from "../copy.ts";
import { barPermille, formatBaht, largest, type Money } from "../money.ts";
import { thaiMonth, thaiMonthShort } from "../thaiMonth.ts";
import { Icon } from "./Icon.tsx";

const VERDICT_STYLE: Record<Verdict, { box: string; badge: string }> = {
  GREEN: { box: "bg-ok-bg border-ok-line text-ok-ink", badge: "bg-leaf-700 text-white" },
  YELLOW: { box: "bg-warn-bg border-warn-line text-warn-ink", badge: "bg-warn-line text-warn-ink" },
  RED: { box: "bg-risk-bg border-risk-line text-risk-ink", badge: "bg-risk-ink text-white" },
};

export function VerdictCard({ verdict }: { verdict: Verdict }) {
  const copy = VERDICT[verdict];
  const style = VERDICT_STYLE[verdict];
  return (
    <div role="status" aria-live="polite" className={`flex flex-col gap-3 rounded-card border-2 p-5 ${style.box}`}>
      <div className="flex items-center gap-3">
        <span className={`inline-flex h-12 w-12 items-center justify-center rounded-pill ${style.badge}`}>
          <Icon name={copy.icon} size={28} />
        </span>
        <VerdictLabel label={copy.label} />
      </div>
      <p className="text-body">{copy.detail}</p>
      <p className="text-body">{ADVISORY_NOTE}</p>
    </div>
  );
}

/** "ไม่ไหว: เกิน 1 ใน 3 ของรายได้" breaks after the colon, never inside a word. */
function VerdictLabel({ label }: { label: string }) {
  const [head, tail] = label.split(": ");
  return (
    <p className="text-title font-bold">
      {tail === undefined ? (
        head
      ) : (
        <>
          {head}: <span className="whitespace-nowrap">{tail}</span>
        </>
      )}
    </p>
  );
}

const STRIPES: CSSProperties = {
  backgroundImage:
    "repeating-linear-gradient(135deg, rgb(255 255 255 / 0.45) 0 4px, transparent 4px 9px)",
};

function barClass(row: MonthRow): string {
  if (row.over_one_third) return "bg-bar-risk";
  if (row.over_budget) return "bg-bar-over";
  return "bg-bar-ok";
}

type BarsProps = { months: MonthRow[]; budget: Money; caption?: string };

export function MonthBars({ months, budget, caption = THINK.monthsTitle }: BarsProps) {
  const scale = largest([budget, ...months.map((m) => m.total)]);
  const budgetLine = barPermille(budget, scale) / 10;
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="text-body font-semibold text-ink">{caption}</figcaption>
      <div className="relative h-40" aria-hidden="true">
        <div
          className="absolute inset-x-0 border-t-2 border-dashed border-ink-muted"
          style={{ bottom: `${budgetLine}%` }}
        />
        <div className="absolute inset-0 flex items-end gap-1.5">
          {months.map((row) => (
            <div key={row.month} className="flex h-full flex-1 flex-col justify-end">
              <div
                className={`w-full rounded-t-md ${barClass(row)}`}
                style={{
                  height: `${Math.max(barPermille(row.total, scale) / 10, 2)}%`, // ui-06-allow: a drawing size
                  ...(row.over_budget ? STRIPES : {}),
                }}
              />
            </div>
          ))}
        </div>
      </div>
      <div className="flex gap-1.5" aria-hidden="true">
        {months.map((row) => (
          <span key={row.month} className="flex-1 text-center text-[0.75rem] leading-tight text-ink-muted">
            {thaiMonthShort(row.month)}
          </span>
        ))}
      </div>
      <p className="text-body text-ink-muted">{THINK.budgetLine(formatBaht(budget))}</p>
      {months.some((m) => m.over_budget) && (
        <p className="flex items-start gap-1.5 text-body font-semibold text-warn-ink">
          <Icon name="alert" size={20} className="mt-0.5" />
          {THINK.overMonths(
            months
              .filter((m) => m.over_budget)
              .map((m) => thaiMonth(m.month))
              .join(", "),
          )}
        </p>
      )}
      <ul className="flex flex-wrap gap-x-4 gap-y-1 text-caption text-ink-muted" aria-hidden="true">
        <li className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-sm bg-bar-ok" />
          {THINK.legendOk}
        </li>
        <li className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-sm bg-bar-over" style={STRIPES} />
          {THINK.legendOver}
        </li>
        <li className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-sm bg-bar-risk" style={STRIPES} />
          {THINK.legendRisk}
        </li>
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
