/**
 * Home's two assistant cards (DESIGN.md section 7.2): consolidation from the plan
 * (L70), and the assistant's chat bubble. Numbers come from GET /assistant/plan; the
 * summary from POST /assistant/summary (mock example now). Shapes and words come
 * from homeLayout.ts (UI-33). "สนใจรวมหนี้" only shows a message: no form, no request
 * call (L71: the bank decides).
 */
import { useId, useState } from "react";
import { getAssistantSummary } from "../api.ts";
import { ACCENT, type Accent } from "../accent.ts";
import { ratePercent } from "../assistantText.ts";
import { ASSIST, COMMON } from "../copy.ts";
import { aiBubble, type ConsolidationView } from "../homeLayout.ts";
import { formatBaht, type Money } from "../money.ts";
import { useLoad } from "../useLoad.ts";
import { Icon } from "./Icon.tsx";
import { LogoBean } from "./Logo.tsx";
import { Button } from "./ui.tsx";

function ExampleTag({ text, accent }: { text: string; accent: Accent }) {
  const look = ACCENT[accent];
  return (
    <span className={`shrink-0 rounded-pill border-2 border-dashed bg-card px-2 py-0.5 text-caption font-semibold ${look.line} ${look.ink}`}>
      {text}
    </span>
  );
}

export function ConsolidationCard({ view }: { view: ConsolidationView }) {
  const [interested, setInterested] = useState(false);
  const [open, setOpen] = useState(false);
  const reasonId = useId();
  if (view.kind === "banner") {
    // Nothing to act on: one slim line, the reason only on request.
    const look = ACCENT[view.line.accent];
    return (
      <section className={`rounded-field border ${look.tint} ${look.line}`}>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={reasonId}
          onClick={() => setOpen((o) => !o)}
          className={`flex min-h-11 w-full cursor-pointer items-center gap-2 px-4 py-2 text-left text-body ${look.ink}`}
        >
          <Icon name={view.line.icon} size={20} />
          <span className="flex-1">{view.line.text}</span>
          <Icon name="down" size={18} className={open ? "rotate-180" : "-rotate-90"} />
        </button>
        {open && (
          <p id={reasonId} className={`px-4 pb-3 text-body ${look.ink}`}>
            {view.reason}
          </p>
        )}
      </section>
    );
  }
  const e = view.estimate;
  const bank = ACCENT[view.title.accent];
  return (
    <section className={`flex flex-col gap-4 rounded-card border-2 p-5 ${bank.tint} ${bank.line}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className={`flex items-center gap-2 text-lead font-bold ${bank.ink}`}>
          <Icon name={view.title.icon} size={24} />
          {view.title.text}
        </h2>
        <ExampleTag text={ASSIST.exampleTag} accent="bank" />
      </div>
      <p className="text-body text-ink">{ASSIST.worth}</p>
      {/* Both rows on both sides: a lower payment can cost more in total. */}
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
        <Plan title={ASSIST.nowColumn} monthly={view.currentMonthly} total={e.current_remaining_total} />
        <Icon name="arrow" size={20} className={bank.ink} />
        <Plan title={ASSIST.ifConsolidated} monthly={e.monthly_payment} total={e.total_cost} />
      </div>
      <p className="text-body text-ink-muted">{ASSIST.terms(e.term_months, ratePercent(e.annual_rate))}</p>
      <p className="flex items-start gap-2 text-body font-semibold text-ink">
        <Icon name="info" size={20} className="mt-0.5" />
        {ASSIST.extraCost(formatBaht(e.extra_cost))}
      </p>
      {interested ? (
        <div role="status" className={`flex gap-3 rounded-field border-2 bg-card p-4 ${bank.line} ${bank.ink}`}>
          <Icon name="check" className="mt-0.5" />
          <div className="flex flex-col gap-1">
            <p className="text-body font-bold">{ASSIST.bankWillCall}</p>
            <p className="text-body">{ASSIST.bankDecides}</p>
          </div>
        </div>
      ) : (
        <Button variant="bank" onClick={() => setInterested(true)}>
          {ASSIST.interested}
        </Button>
      )}
    </section>
  );
}

function Plan({ title, monthly, total }: { title: string; monthly: Money; total: Money }) {
  return (
    <div className="flex h-full flex-col rounded-field bg-card p-3">
      {/* Two lines for every title, so both columns' numbers line up. */}
      <span className="min-h-10 text-caption font-semibold text-ink-muted">{title}</span>
      <span className="text-lead font-bold text-ink">{formatBaht(monthly)}</span>
      <span className="text-caption text-ink-muted">{COMMON.perMonth}</span>
      <span className="mt-2 text-caption text-ink-muted">{ASSIST.totalAll}</span>
      <span className="text-body font-semibold text-ink">{formatBaht(total)}</span>
    </div>
  );
}

/** The assistant speaks: the mascot on the left, the summary's first line in a bubble. */
export function AiBubbleCard() {
  const [load, reload] = useLoad(getAssistantSummary);
  const [open, setOpen] = useState(false);
  const restId = useId();
  const bubble = aiBubble(load);
  const ai = ACCENT.ai;
  return (
    <section className={`flex items-start gap-3 rounded-card border p-4 ${ai.tint} ${ai.line}`}>
      <span aria-hidden="true" className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-pill bg-card shadow-card">
        <LogoBean size={34} />
      </span>
      <div className="relative flex min-w-0 flex-1 flex-col gap-2 rounded-card rounded-tl-md bg-card p-4 shadow-card">
        <span aria-hidden="true" className="absolute top-4 -left-1.5 h-3 w-3 rotate-45 bg-card" />
        <h2 className={`flex flex-wrap items-center gap-2 text-body font-bold ${ai.ink}`}>
          <Icon name={ai.icon} size={20} />
          {ai.label}
          {bubble.state === "done" && bubble.example && <ExampleTag text={ASSIST.aiExample} accent="ai" />}
        </h2>
        {bubble.state === "loading" && (
          <p role="status" aria-busy="true" className="min-h-12 text-body text-ink-muted">
            {ASSIST.aiLoading}
          </p>
        )}
        {bubble.state === "failed" && (
          <>
            <p role="status" className="text-body text-ink">
              {ASSIST.aiFailed}
            </p>
            <Button variant="secondary" onClick={reload}>
              {COMMON.retry}
            </Button>
          </>
        )}
        {bubble.state === "done" && (
          <>
            <p className="text-body text-ink">{bubble.first}</p>
            {open && (
              <div id={restId} className="flex flex-col gap-1">
                {bubble.rest.map((line) => (
                  <p key={line} className="text-body text-ink">
                    {line}
                  </p>
                ))}
              </div>
            )}
            {bubble.rest.length > 0 && (
              <button
                type="button"
                aria-expanded={open}
                aria-controls={restId}
                onClick={() => setOpen((o) => !o)}
                className={`min-h-11 cursor-pointer self-start text-body font-semibold ${ai.ink}`}
              >
                {open ? ASSIST.aiLess : ASSIST.aiMore}
              </button>
            )}
          </>
        )}
      </div>
    </section>
  );
}
