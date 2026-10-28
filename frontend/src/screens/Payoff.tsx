/**
 * Screen 6: payoff assistant, MOCK (DESIGN.md section 7.6).
 * Every month and amount comes from the plan (TODO(backend): GET /payoff/plan).
 * The explanation and the answers are labelled as prototype examples, not AI output.
 */
import { useState, type FormEvent, type ReactNode } from "react";
import { askPayoff, getPayoffPlan, getSettings } from "../api.ts";
import type { PayoffPlanOut } from "../api-types.ts";
import { PAYOFF } from "../copy.ts";
import { Icon, type IconName } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Alert, Button, Card, ErrorState, Field, Loading, SettingsMissing } from "../components/ui.tsx";
import { formatBaht } from "../money.ts";
import { navigate } from "../router.ts";
import { thaiMonth } from "../thaiMonth.ts";
import { useLoad } from "../useLoad.ts";

async function loadPlan(): Promise<PayoffPlanOut | null> {
  return (await getSettings()) === null ? null : getPayoffPlan();
}

export function PayoffScreen() {
  const [load, reload] = useLoad(loadPlan);
  return (
    <Screen route="payoff" title={PAYOFF.title} back="home">
      {load.state === "loading" && <Loading lines={4} />}
      {load.state === "error" && <ErrorState onRetry={reload} />}
      {load.state === "ready" &&
        (load.data === null ? <SettingsMissing onSetUp={() => navigate("settings")} /> : <Plan plan={load.data} />)}
    </Screen>
  );
}

function Row({ icon, title, children }: { icon: IconName; title: string; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <span className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-pill bg-leaf-50 text-leaf-700">
        <Icon name={icon} />
      </span>
      <div className="flex flex-col gap-0.5">
        <h2 className="text-body font-bold text-ink">{title}</h2>
        <div className="text-body text-ink">{children}</div>
      </div>
    </div>
  );
}

function Plan({ plan }: { plan: PayoffPlanOut }) {
  const b = plan.buffer_plan;
  return (
    <>
      <Card className="flex flex-col gap-5">
        <Row icon="check" title={PAYOFF.backInBudgetTitle}>
          {plan.back_in_budget_month === null
            ? PAYOFF.notInHorizon
            : plan.pause_until === null
              ? PAYOFF.allInBudget
              : PAYOFF.backInBudget(thaiMonth(plan.back_in_budget_month))}
        </Row>
        <Row icon="info" title={PAYOFF.pauseTitle}>
          {plan.pause_beyond_horizon
            ? PAYOFF.pauseBeyond
            : plan.pause_until === null
              ? PAYOFF.noPause
              : PAYOFF.pause(thaiMonth(plan.pause_until))}
        </Row>
        <Row icon="think" title={PAYOFF.headroomTitle}>
          {plan.headroom === null
            ? PAYOFF.noHeadroom
            : PAYOFF.headroom(formatBaht(plan.headroom.amount), thaiMonth(plan.headroom.from_month))}
        </Row>
        <Row icon="shield" title={PAYOFF.bufferTitle}>
          {b.shortfalls.length === 0 ? (
            PAYOFF.bufferNone
          ) : (
            <div className="flex flex-col gap-1">
              <ul>
                {b.shortfalls.map((s) => (
                  <li key={s.month}>{PAYOFF.bufferShort(thaiMonth(s.month), formatBaht(s.amount))}</li>
                ))}
              </ul>
              <p>{PAYOFF.bufferTotal(formatBaht(b.total_shortfall))}</p>
              <p className={`flex items-center gap-1.5 font-semibold ${b.covered ? "text-ok-ink" : "text-warn-ink"}`}>
                <Icon name={b.covered ? "check" : "alert"} size={20} />
                {b.covered ? PAYOFF.bufferCovered(formatBaht(b.buffer_balance)) : PAYOFF.bufferNotCovered(formatBaht(b.buffer_balance))}
              </p>
            </div>
          )}
        </Row>
      </Card>

      <Card className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-lead font-bold text-ink">
            <Icon name="spark" size={22} />
            {PAYOFF.aiTitle}
          </h2>
          <ExampleTag />
        </div>
        <p className="text-body text-ink">{plan.explanation}</p>
        <p className="text-caption text-ink-muted">{PAYOFF.aiNote}</p>
        <AskBox />
      </Card>

      {plan.consolidation_eligible && (
        <Card className="flex flex-col gap-3">
          <p className="text-body text-ink-muted">{PAYOFF.consolidateHelp}</p>
          <Button variant="secondary" onClick={() => navigate("consolidate")}>
            {PAYOFF.consolidate}
          </Button>
        </Card>
      )}
    </>
  );
}

function ExampleTag() {
  return (
    <span className="rounded-pill border-2 border-dashed border-info-line bg-info-bg px-3 py-0.5 text-caption font-semibold text-info-ink">
      {PAYOFF.exampleTag}
    </span>
  );
}

function AskBox() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (question.trim() === "") {
      setError(PAYOFF.askEmpty);
      return;
    }
    setError(null);
    setBusy(true);
    try {
      setAnswer((await askPayoff(question.trim())).answer);
    } catch {
      setError(PAYOFF.askFailed);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-3 border-t border-line pt-4">
      <Field
        label={PAYOFF.askLabel}
        value={question}
        onChange={setQuestion}
        placeholder={PAYOFF.askPlaceholder}
        maxLength={200}
        error={error}
      />
      <Button type="submit" variant="secondary" busy={busy}>
        {busy ? PAYOFF.asking : PAYOFF.ask}
      </Button>
      {answer !== null && (
        <Alert tone="info" title={PAYOFF.answerNote}>
          {answer}
        </Alert>
      )}
    </form>
  );
}
