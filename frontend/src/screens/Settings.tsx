/**
 * Screen 1: first-time settings, and editing them later (DESIGN.md section 7.1).
 * POST the first time, PUT afterwards. A budget above one third of income is saved
 * anyway; the API's warning code is shown (L64, advice only).
 */
import { useState, type FormEvent } from "react";
import { getSettings, saveSettings } from "../api.ts";
import { BUDGET_ABOVE_ONE_THIRD_OF_INCOME, type SettingsIn, type SettingsOut } from "../api-types.ts";
import { MONEY_ERRORS, SETTINGS } from "../copy.ts";
import { Alert, Button, Card, Checkbox, ErrorState, Field, Loading, Toggle } from "../components/ui.tsx";
import { Screen } from "../components/Screen.tsx";
import { PERSONA_SETTINGS } from "../mock/persona.ts";
import { parseMoneyInput } from "../money.ts";
import { navigate } from "../router.ts";
import { useLoad } from "../useLoad.ts";

type Form = {
  income: string;
  payday: string;
  budget: string;
  mode: "percent" | "fixed";
  percent: string;
  fixed: string;
  autoSave: boolean;
  leftover: boolean;
  consent: boolean;
};

const EMPTY: Form = {
  income: "",
  payday: "",
  budget: "",
  mode: "percent",
  percent: "10",
  fixed: "",
  autoSave: true,
  leftover: true,
  consent: false,
};

function fromSettings(s: SettingsIn | SettingsOut): Form {
  return {
    income: s.income,
    payday: String(s.payday),
    budget: s.monthly_installment_budget,
    mode: s.saving_rule.mode,
    percent: s.saving_rule.mode === "percent" ? String(s.saving_rule.percent) : "10",
    fixed: s.saving_rule.mode === "fixed" ? s.saving_rule.amount : "",
    autoSave: s.auto_save_enabled,
    leftover: s.leftover_saving_enabled,
    consent: "consent_at" in s ? s.consent_at !== null : s.auto_save_consent,
  };
}

type Errors = Partial<Record<"income" | "payday" | "budget" | "percent" | "fixed" | "consent", string>>;

const INT_1_TO_31 = /^([1-9]|[12][0-9]|3[01])$/;
const INT_1_TO_100 = /^([1-9][0-9]?|100)$/;

/** Build the request, or the errors to show. Money stays the string the user typed. */
function toRequest(form: Form): { ok: true; body: SettingsIn } | { ok: false; errors: Errors } {
  const errors: Errors = {};
  const income = parseMoneyInput(form.income);
  const budget = parseMoneyInput(form.budget);
  const fixed = parseMoneyInput(form.fixed);
  if (!income.ok) errors.income = MONEY_ERRORS[income.reason];
  if (!budget.ok) errors.budget = MONEY_ERRORS[budget.reason];
  if (!INT_1_TO_31.test(form.payday.trim())) errors.payday = SETTINGS.paydayError;
  if (form.mode === "percent" && !INT_1_TO_100.test(form.percent.trim())) errors.percent = SETTINGS.percentError;
  if (form.mode === "fixed" && !fixed.ok) errors.fixed = MONEY_ERRORS[fixed.reason];
  if (form.autoSave && !form.consent) errors.consent = SETTINGS.consentError;
  if (!income.ok || !budget.ok || Object.keys(errors).length > 0) return { ok: false, errors };
  return {
    ok: true,
    body: {
      income: income.value,
      payday: Number(form.payday.trim()), // ui-06-allow: a day of the month
      monthly_installment_budget: budget.value,
      // L63: exactly one mode is sent, never both.
      saving_rule:
        form.mode === "percent"
          ? { mode: "percent", percent: Number(form.percent.trim()) } // ui-06-allow: a whole percent
          : { mode: "fixed", amount: fixed.ok ? fixed.value : "" },
      auto_save_enabled: form.autoSave,
      auto_save_consent: form.autoSave && form.consent,
      leftover_saving_enabled: form.leftover,
    },
  };
}

export function SettingsScreen() {
  const [load, reload] = useLoad(getSettings);
  if (load.state === "loading") {
    return (
      <Screen route="settings" title={SETTINGS.editTitle} showNav={false}>
        <Loading lines={4} />
      </Screen>
    );
  }
  if (load.state === "error") {
    return (
      <Screen route="settings" title={SETTINGS.editTitle} showNav={false}>
        <ErrorState onRetry={reload} />
      </Screen>
    );
  }
  return <SettingsForm existing={load.data} />;
}

function SettingsForm({ existing }: { existing: SettingsOut | null }) {
  const firstTime = existing === null;
  const [form, setForm] = useState<Form>(existing === null ? EMPTY : fromSettings(existing));
  const [errors, setErrors] = useState<Errors>({});
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [saved, setSaved] = useState<SettingsOut | null>(null);
  const [exists, setExists] = useState(!firstTime);

  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setSaved(null);
  };

  async function submit(event: FormEvent) {
    event.preventDefault();
    const request = toRequest(form);
    if (!request.ok) {
      setErrors(request.errors);
      return;
    }
    setErrors({});
    setBusy(true);
    setFailed(false);
    try {
      setSaved(await saveSettings(request.body, exists));
      setExists(true);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen
      route="settings"
      {...(firstTime ? {} : { title: SETTINGS.editTitle })}
      showNav={!firstTime}
    >
      {firstTime && (
        <div className="flex flex-col gap-1 pt-2">
          <h1 className="text-title font-bold text-ink">{SETTINGS.title}</h1>
          <p className="text-body text-ink-muted">{SETTINGS.intro}</p>
        </div>
      )}
      <DemoFill onFill={() => setForm(fromSettings(PERSONA_SETTINGS))} />
      <form noValidate onSubmit={submit} className="flex flex-col gap-4">
        <Card className="flex flex-col gap-5">
          <Field
            label={SETTINGS.income}
            help={SETTINGS.incomeHelp}
            value={form.income}
            onChange={(v) => set("income", v)}
            inputMode="decimal"
            suffix="บาท"
            placeholder="เช่น 20,000"
            error={errors.income ?? null}
          />
          <Field
            label={SETTINGS.payday}
            help={SETTINGS.paydayHelp}
            value={form.payday}
            onChange={(v) => set("payday", v)}
            inputMode="numeric"
            placeholder="เช่น 25"
            maxLength={2}
            error={errors.payday ?? null}
          />
          <Field
            label={SETTINGS.budget}
            help={SETTINGS.budgetHelp}
            value={form.budget}
            onChange={(v) => set("budget", v)}
            inputMode="decimal"
            suffix="บาท"
            placeholder="เช่น 5,000"
            error={errors.budget ?? null}
          />
        </Card>

        <Card className="flex flex-col gap-4">
          <Toggle
            label={SETTINGS.autoSave}
            help={SETTINGS.savingHelp}
            checked={form.autoSave}
            onChange={(v) => set("autoSave", v)}
          />
          {form.autoSave && (
            <>
              <fieldset className="flex flex-col gap-2">
                <legend className="mb-2 text-body font-semibold text-ink">{SETTINGS.savingTitle}</legend>
                <div className="grid grid-cols-2 gap-2">
                  {(["percent", "fixed"] as const).map((mode) => (
                    <label
                      key={mode}
                      className={`flex min-h-12 cursor-pointer items-center justify-center rounded-field border-2 px-3 text-center text-body font-semibold ${
                        form.mode === mode ? "border-leaf-700 bg-leaf-50 text-leaf-800" : "border-line bg-card text-ink-muted"
                      }`}
                    >
                      <input
                        type="radio"
                        name="saving-mode"
                        value={mode}
                        checked={form.mode === mode}
                        onChange={() => set("mode", mode)}
                        className="sr-only"
                      />
                      {mode === "percent" ? SETTINGS.savingPercent : SETTINGS.savingFixed}
                    </label>
                  ))}
                </div>
              </fieldset>
              {form.mode === "percent" ? (
                <Field
                  label={SETTINGS.percentLabel}
                  value={form.percent}
                  onChange={(v) => set("percent", v)}
                  inputMode="numeric"
                  suffix="%"
                  maxLength={3}
                  error={errors.percent ?? null}
                />
              ) : (
                <Field
                  label={SETTINGS.fixedLabel}
                  value={form.fixed}
                  onChange={(v) => set("fixed", v)}
                  inputMode="decimal"
                  suffix="บาท"
                  placeholder="เช่น 200"
                  error={errors.fixed ?? null}
                />
              )}
              <p className="text-body text-ink-muted">{SETTINGS.safetyNet}</p>
            </>
          )}
          <Toggle
            label={SETTINGS.leftover}
            help={SETTINGS.leftoverHelp}
            checked={form.leftover}
            onChange={(v) => set("leftover", v)}
          />
          {form.autoSave && (
            <Checkbox
              label={SETTINGS.consent}
              checked={form.consent}
              onChange={(v) => set("consent", v)}
              error={errors.consent ?? null}
            />
          )}
        </Card>

        {failed && <Alert tone="info" title={SETTINGS.failed} />}
        {saved !== null && (
          <div className="flex flex-col gap-3">
            <Alert tone="ok" title={SETTINGS.saved} />
            {saved.warnings.includes(BUDGET_ABOVE_ONE_THIRD_OF_INCOME) && (
              <Alert tone="warn">{SETTINGS.budgetWarning}</Alert>
            )}
          </div>
        )}
        {saved !== null ? (
          <Button size="lg" onClick={() => navigate("home")} icon="home">
            {SETTINGS.next}
          </Button>
        ) : (
          <Button size="lg" type="submit" busy={busy}>
            {busy ? SETTINGS.saving : SETTINGS.save}
          </Button>
        )}
      </form>
    </Screen>
  );
}

/** Demo only: fill the persona's values (DESIGN.md section 10). */
function DemoFill({ onFill }: { onFill: () => void }) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-field border-2 border-dashed border-info-line bg-info-bg px-4 py-2">
      <span className="text-caption font-semibold text-info-ink">Demo</span>
      <button
        type="button"
        onClick={onFill}
        className="min-h-11 cursor-pointer rounded-pill px-3 text-body font-semibold text-info-ink underline underline-offset-4"
      >
        {SETTINGS.demoFill}
      </button>
    </div>
  );
}
