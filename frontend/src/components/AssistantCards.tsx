/**
 * Home's two assistant cards (DESIGN.md section 7.2): consolidation from the plan
 * (L70), and the assistant's chat bubble. Numbers come from GET /assistant/plan; the
 * summary from GET /assistant/summary (the model's words behind the backend's grounding
 * check, or the backend's own template). Shapes and words come
 * from homeLayout.ts (UI-33). "สนใจรวมหนี้" only shows a message: no form, no request
 * call (L71: the bank decides).
 */
import { useId, useState } from "react";
import { getAssistantSummary } from "../api.ts";
import type { AssistantPlanOut } from "../api-types.ts";
import { ACCENT, EDGE, SOLID, type Accent } from "../accent.ts";
import { ratePercent } from "../assistantText.ts";
import { ASSIST, COMMON } from "../copy.ts";
import { aiBubble, type ConsolidationView } from "../homeLayout.ts";
import { formatBaht, type Money } from "../money.ts";
import { useLoad } from "../useLoad.ts";
import { Icon } from "./Icon.tsx";
import { LogoBean } from "./Logo.tsx";
import { Button } from "./ui.tsx";

/**
 * Thai breaks a line between any two words, so "ทุกเดือนกลับมาอยู่ในงบ" could end a
 * line on "กลับ". The sentence's last phrase (after its last space) moves down whole.
 */
function KeepLastPhrase({ text }: { text: string }) {
  const cut = text.lastIndexOf(" ");
  if (cut < 0) return text;
  return (
    <>
      {text.slice(0, cut + 1)}
      <span className="whitespace-nowrap">{text.slice(cut + 1)}</span>
    </>
  );
}

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
      <section className={`rounded-field ${look.tint} ${EDGE.quiet}`}>
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
    // A white card framed in blue, with a solid blue header band: it stands out from
    // the page, its edge at least 3:1 against it (UI-35). The card itself is the blue
    // (the band shows it), so its rounded corners never show a pale hairline.
    <section className={`overflow-hidden rounded-card ${SOLID.bank} ${EDGE.bank}`}>
      <div className="flex flex-wrap items-center justify-between gap-2 px-5 py-3">
        <h2 className="flex items-center gap-2 text-lead font-bold">
          <Icon name={view.title.icon} size={24} />
          {view.title.text}
        </h2>
        <ExampleTag text={ASSIST.exampleTag} accent="bank" />
      </div>
      <div className="flex flex-col gap-4 bg-card p-4 text-ink">
        {/* Both rows on both sides, equally large: a lower payment can cost more in total.
            The arrow sits on the gap, not in a column of its own, so each amount keeps
            its "บาท" on one line in the 370px desktop frame (UI-38). */}
        <div className="relative grid grid-cols-2 gap-3">
          <Plan title={ASSIST.nowColumn} monthly={view.currentMonthly} total={e.current_remaining_total} />
          <Plan title={ASSIST.ifConsolidated} monthly={e.monthly_payment} total={e.total_cost} />
          <span
            aria-hidden="true"
            className={`absolute top-1/2 left-1/2 inline-flex h-7 w-7 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-pill border-2 bg-card ${bank.line} ${bank.ink}`}
          >
            <Icon name="arrow" size={16} />
          </span>
        </div>
        {view.benefit !== null && (
          <p className="text-body text-pretty text-ink">
            <KeepLastPhrase text={view.benefit} />
          </p>
        )}
        <p className="text-body text-ink-muted">
          <KeepLastPhrase text={ASSIST.terms(e.term_months, ratePercent(e.annual_rate))} />
        </p>
        {interested ? (
          <div role="status" className={`flex gap-3 rounded-field border-2 p-4 ${bank.tint} ${bank.line} ${bank.ink}`}>
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
      </div>
    </section>
  );
}

/** The monthly amount and the total are the same size and weight: the total is never the small print (UI-38). */
const PLAN_AMOUNT = "text-lead font-bold text-ink";

/** `monthly` is null when the answer did not carry it (UI-39): the column shows its total only. */
function Plan({ title, monthly, total }: { title: string; monthly: Money | null; total: Money }) {
  return (
    <div className={`flex h-full flex-col rounded-field p-3 ${ACCENT.bank.tint}`}>
      {/* Two lines for every title, so both columns' numbers line up. */}
      <span className="min-h-10 text-caption font-semibold text-ink-muted">{title}</span>
      {monthly !== null && (
        <>
          <span className={PLAN_AMOUNT}>{formatBaht(monthly)}</span>
          <span className="text-caption text-ink-muted">{COMMON.perMonth}</span>
        </>
      )}
      <span className="mt-2 text-caption text-ink-muted">{ASSIST.totalAll}</span>
      <span className={PLAN_AMOUNT}>{formatBaht(total)}</span>
    </div>
  );
}

/**
 * The assistant speaks: the mascot on the left, the summary's first line in a bubble.
 * The same look for the model's words and the app's own, and no error state: a failed
 * request shows the plan's own words (homeLayout.aiBubble).
 */
export function AiBubbleCard({ plan }: { plan: AssistantPlanOut }) {
  const [load] = useLoad(getAssistantSummary);
  const [open, setOpen] = useState(false);
  const restId = useId();
  const bubble = aiBubble(load, plan);
  const ai = ACCENT.ai;
  return (
    <section className={`flex items-start gap-3 rounded-card p-4 ${ai.tint} ${EDGE.ai}`}>
      <span aria-hidden="true" className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-pill bg-card shadow-card">
        <LogoBean size={34} />
      </span>
      <div className="relative flex min-w-0 flex-1 flex-col gap-2 rounded-card rounded-tl-md bg-card p-4 shadow-card">
        <span aria-hidden="true" className="absolute top-4 -left-1.5 h-3 w-3 rotate-45 bg-card" />
        <h2 className={`flex flex-wrap items-center gap-2 text-body font-bold ${ai.ink}`}>
          <Icon name={ai.icon} size={20} />
          {ASSIST.aiTitle}
        </h2>
        {bubble.state === "loading" && (
          <p role="status" aria-busy="true" className="min-h-12 text-body text-ink-muted">
            {ASSIST.aiLoading}
          </p>
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
