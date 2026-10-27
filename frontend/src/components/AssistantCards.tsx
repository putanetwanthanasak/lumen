/**
 * Home's two assistant cards (DESIGN.md section 7.2): "ควรรวมหนี้ไหม" from the
 * plan's consolidation (L70), and "ผู้ช่วย KidNee สรุปให้ฟัง". Numbers come from
 * GET /assistant/plan; the summary from POST /assistant/summary (mock example now).
 * "สนใจรวมหนี้" only shows a message: no form, no request call (L71: the bank decides).
 */
import { useState } from "react";
import { getAssistantSummary } from "../api.ts";
import type { AssistantSummaryOut, ConsolidationOut } from "../api-types.ts";
import { ratePercent } from "../assistantText.ts";
import { ASSIST } from "../copy.ts";
import { formatBaht } from "../money.ts";
import { Icon } from "./Icon.tsx";
import { Alert, Button, Card } from "./ui.tsx";

function ExampleTag({ text }: { text: string }) {
  return (
    <span className="shrink-0 self-start rounded-pill border-2 border-dashed border-info-line bg-info-bg px-2 py-0.5 text-caption font-semibold text-info-ink">
      {text}
    </span>
  );
}

export function ConsolidationCard({ consolidation }: { consolidation: ConsolidationOut }) {
  const [interested, setInterested] = useState(false);
  const e = consolidation.estimate;
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-lead font-bold text-ink">{ASSIST.consolidateTitle}</h2>
        {e !== null && <ExampleTag text={ASSIST.exampleTag} />}
      </div>
      {e === null ? (
        <div className="flex flex-col gap-1">
          <p className="flex items-center gap-2 text-body font-semibold text-ink">
            <Icon name="info" size={20} className="text-info-ink" />
            {ASSIST.notWorth}
          </p>
          <p className="text-body text-ink-muted">{ASSIST.reason[consolidation.reason]}</p>
        </div>
      ) : (
        <>
          <p className="text-body text-ink">{ASSIST.worth}</p>
          {/* Both numbers, side by side: a lower payment can cost more in total. */}
          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col rounded-field bg-leaf-50 p-3">
              <span className="text-caption text-ink-muted">{ASSIST.newMonthly}</span>
              <span className="text-lead font-bold text-ink">{formatBaht(e.monthly_payment)}</span>
            </div>
            <div className="flex flex-col rounded-field bg-warn-bg p-3">
              <span className="text-caption text-ink-muted">{ASSIST.totalCost}</span>
              <span className="text-lead font-bold text-ink">{formatBaht(e.total_cost)}</span>
            </div>
          </div>
          <p className="text-body text-ink-muted">{ASSIST.terms(e.term_months, ratePercent(e.annual_rate))}</p>
          <p className="text-body font-semibold text-warn-ink">
            {ASSIST.extraCost(formatBaht(e.extra_cost), formatBaht(e.current_remaining_total))}
          </p>
          {interested ? (
            <Alert tone="ok" title={ASSIST.bankWillCall}>
              {ASSIST.bankDecides}
            </Alert>
          ) : (
            <Button variant="secondary" onClick={() => setInterested(true)}>
              {ASSIST.interested}
            </Button>
          )}
        </>
      )}
    </Card>
  );
}

type Summary = { state: "idle" } | { state: "loading" } | { state: "done"; out: AssistantSummaryOut } | { state: "failed" };

export function AiSummaryCard() {
  const [summary, setSummary] = useState<Summary>({ state: "idle" });
  async function ask() {
    setSummary({ state: "loading" });
    try {
      setSummary({ state: "done", out: await getAssistantSummary() });
    } catch {
      setSummary({ state: "failed" });
    }
  }
  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-center gap-3">
        <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-pill bg-leaf-50 text-leaf-700">
          <Icon name="spark" size={28} />
        </span>
        <div className="flex flex-col">
          <h2 className="text-lead font-bold text-ink">{ASSIST.aiTitle}</h2>
          <p className="text-body text-ink-muted">{ASSIST.aiHelp}</p>
        </div>
      </div>
      {summary.state === "done" ? (
        <div className="flex flex-col gap-2 rounded-field border-2 border-dashed border-info-line bg-info-bg p-3">
          {summary.out.is_example && <ExampleTag text={ASSIST.aiExample} />}
          <p className="whitespace-pre-line text-body text-ink">{summary.out.text}</p>
        </div>
      ) : (
        <Button variant="secondary" icon="spark" busy={summary.state === "loading"} onClick={() => void ask()}>
          {summary.state === "loading" ? ASSIST.aiLoading : ASSIST.aiButton}
        </Button>
      )}
      {summary.state === "failed" && <Alert tone="info" title={ASSIST.aiFailed} />}
    </Card>
  );
}
