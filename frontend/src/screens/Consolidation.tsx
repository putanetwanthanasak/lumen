/**
 * Screen 7: consolidation request, MOCK (DESIGN.md section 7.7).
 * The user copies each app's payoff amount, picks a term and consents; the result
 * shows BOTH the new monthly payment AND the total cost, as an example estimate.
 * TODO(backend): POST /consolidation/estimate.
 */
import { useState, type FormEvent } from "react";
import { estimateConsolidation, getDebtSummary, getPayoffPlan, getSettings } from "../api.ts";
import type { ConsolidationOut, InstallmentLine } from "../api-types.ts";
import { CONSOLIDATE, MONEY_ERRORS } from "../copy.ts";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Alert, Button, Card, Checkbox, ErrorState, Field, Loading, SettingsMissing } from "../components/ui.tsx";
import { formatBaht, parseMoneyInput, type Money } from "../money.ts";
import { payoffSteps } from "../payoffSteps.ts";
import { navigate } from "../router.ts";
import { useLoad } from "../useLoad.ts";

const TERMS = [12, 24, 36] as const;

async function loadOwed(): Promise<{ eligible: boolean; lines: InstallmentLine[] } | null> {
  // No settings yet: say so and link to screen 1, never a connection error (review B1 F7).
  if ((await getSettings()) === null) return null;
  const [plan, summary] = await Promise.all([getPayoffPlan(), getDebtSummary()]);
  return { eligible: plan.consolidation_eligible, lines: summary.installments.filter((l) => l.owed) };
}

export function ConsolidationScreen() {
  const [load, reload] = useLoad(loadOwed);
  return (
    <Screen route="consolidate" title={CONSOLIDATE.title} back="payoff">
      <Alert tone="info" title={CONSOLIDATE.exampleBanner} />
      {load.state === "loading" && <Loading lines={3} />}
      {load.state === "error" && <ErrorState onRetry={reload} />}
      {load.state === "ready" && load.data === null && <SettingsMissing onSetUp={() => navigate("settings")} />}
      {load.state === "ready" &&
        load.data !== null &&
        (load.data.eligible ? (
          <Request lines={load.data.lines} />
        ) : (
          <Card>
            <p className="text-body text-ink">{CONSOLIDATE.notEligible}</p>
          </Card>
        ))}
    </Screen>
  );
}

type Entry = { include: boolean; payoff: string };

function Request({ lines }: { lines: InstallmentLine[] }) {
  const [entries, setEntries] = useState<Record<string, Entry>>(() =>
    Object.fromEntries(lines.map((l) => [l.id, { include: true, payoff: "" }])),
  );
  const [months, setMonths] = useState<number>(24);
  const [consent, setConsent] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [result, setResult] = useState<ConsolidationOut | null>(null);

  const update = (id: string, change: Partial<Entry>) => {
    setEntries((e) => ({ ...e, [id]: { include: true, payoff: "", ...e[id], ...change } }));
    setResult(null);
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    const payoffs: { installment_id: string; payoff_amount: Money }[] = [];
    for (const line of lines) {
      const entry = entries[line.id];
      if (entry === undefined || !entry.include) continue;
      const parsed = parseMoneyInput(entry.payoff);
      if (parsed.ok) payoffs.push({ installment_id: line.id, payoff_amount: parsed.value });
      else found[line.id] = MONEY_ERRORS[parsed.reason];
    }
    if (payoffs.length === 0 && Object.keys(found).length === 0) found.form = CONSOLIDATE.pickOne;
    if (!consent) found.consent = CONSOLIDATE.consentError;
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    setFailed(false);
    try {
      setResult(await estimateConsolidation({ payoffs, months, consent }));
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  if (result !== null) return <Result result={result} onAgain={() => setResult(null)} />;

  return (
    <form noValidate onSubmit={submit} className="flex flex-col gap-4">
      <Card className="flex flex-col gap-3">
        <h2 className="text-lead font-bold text-ink">{CONSOLIDATE.stepsTitle}</h2>
        {payoffSteps(lines).map((app) => (
          <div key={app.label} className="flex flex-col gap-2">
            <h3 className="flex items-center gap-2 text-body font-bold text-leaf-800">
              <Icon name="wallet" size={18} />
              {app.label}
            </h3>
            <ol className="flex flex-col gap-2">
              {app.steps.map((step, i) => (
                <li key={step} className="flex gap-3 text-body text-ink">
                  <span className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-pill bg-leaf-700 text-caption font-bold text-white">
                    {i + 1}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
          </div>
        ))}
      </Card>

      <Card className="flex flex-col gap-5">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lead font-bold text-ink">{CONSOLIDATE.payoffTitle}</h2>
          <button
            type="button"
            onClick={() => {
              for (const l of lines) update(l.id, { payoff: l.remaining });
            }}
            className="min-h-11 cursor-pointer rounded-pill border-2 border-dashed border-info-line bg-info-bg px-3 text-caption font-semibold text-info-ink"
          >
            Demo: {CONSOLIDATE.demoFill}
          </button>
        </div>
        {lines.map((line) => {
          const entry = entries[line.id] ?? { include: true, payoff: "" };
          return (
            <div key={line.id} className="flex flex-col gap-2 border-b border-line pb-4 last:border-b-0 last:pb-0">
              <Checkbox
                label={`${CONSOLIDATE.include}: ${line.item_name || line.contract_id}`}
                checked={entry.include}
                onChange={(include) => update(line.id, { include })}
              />
              {entry.include && (
                <Field
                  label={CONSOLIDATE.payoffLabel(line.item_name || line.contract_id)}
                  help={CONSOLIDATE.remainingHint(formatBaht(line.remaining))}
                  value={entry.payoff}
                  onChange={(payoff) => update(line.id, { payoff })}
                  inputMode="decimal"
                  suffix="บาท"
                  placeholder="เช่น 3,900"
                  error={errors[line.id] ?? null}
                />
              )}
            </div>
          );
        })}
        {errors.form !== undefined && <Alert tone="warn">{errors.form}</Alert>}
      </Card>

      <Card className="flex flex-col gap-4">
        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-body font-semibold text-ink">{CONSOLIDATE.monthsTitle}</legend>
          <div className="grid grid-cols-3 gap-2">
            {TERMS.map((term) => (
              <label
                key={term}
                className={`flex min-h-12 cursor-pointer items-center justify-center rounded-field border-2 text-body font-semibold ${
                  months === term ? "border-leaf-700 bg-leaf-50 text-leaf-800" : "border-line bg-card text-ink-muted"
                }`}
              >
                <input
                  type="radio"
                  name="term"
                  checked={months === term}
                  onChange={() => {
                    setMonths(term);
                    setResult(null);
                  }}
                  className="sr-only"
                />
                {CONSOLIDATE.monthsOption(term)}
              </label>
            ))}
          </div>
        </fieldset>
        <Checkbox
          label={CONSOLIDATE.consent}
          checked={consent}
          onChange={setConsent}
          error={errors.consent ?? null}
        />
      </Card>

      {failed && <Alert tone="info" title={CONSOLIDATE.failed} />}
      <Button size="lg" type="submit" busy={busy}>
        {busy ? CONSOLIDATE.estimating : CONSOLIDATE.estimate}
      </Button>
    </form>
  );
}

function Result({ result, onAgain }: { result: ConsolidationOut; onAgain: () => void }) {
  return (
    <>
      <Card className="flex flex-col gap-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-lead font-bold text-ink">{CONSOLIDATE.resultTitle}</h2>
          <span className="rounded-pill border-2 border-dashed border-info-line bg-info-bg px-3 py-0.5 text-caption font-semibold text-info-ink">
            {CONSOLIDATE.exampleTag}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-1 rounded-field bg-leaf-50 p-3">
            <span className="text-body text-ink-muted">{CONSOLIDATE.newMonthly}</span>
            <span className="text-title font-bold text-ink">{formatBaht(result.new_monthly_payment)}</span>
          </div>
          <div className="flex flex-col gap-1 rounded-field bg-leaf-50 p-3">
            <span className="text-body text-ink-muted">{CONSOLIDATE.totalCost}</span>
            <span className="text-title font-bold text-ink">{formatBaht(result.total_cost)}</span>
          </div>
        </div>
        <p className="text-body text-ink">{CONSOLIDATE.interest(formatBaht(result.total_interest))}</p>
        <p className="text-body text-ink-muted">{CONSOLIDATE.rateNote(result.annual_rate_example, result.months)}</p>
      </Card>
      <Card className="flex flex-col gap-2">
        <h2 className="text-lead font-bold text-ink">{CONSOLIDATE.nowTitle}</h2>
        <p className="text-body text-ink">{CONSOLIDATE.nowMonthly(formatBaht(result.monthly_now))}</p>
        <p className="text-body text-ink">{CONSOLIDATE.nowRemaining(formatBaht(result.remaining_now))}</p>
      </Card>
      <Alert tone="warn">{CONSOLIDATE.compareNote}</Alert>
      <Button variant="secondary" onClick={onAgain}>
        {CONSOLIDATE.again}
      </Button>
    </>
  );
}
