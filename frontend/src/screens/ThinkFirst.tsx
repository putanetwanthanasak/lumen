/**
 * Screen 3: ตรวจสอบก่อนผ่อน, the form (DESIGN.md section 7.3).
 * Kind, item, app, price, months, monthly amount (prefilled with the API's 0%
 * suggestion until the user edits it) and the first due month (no default). The
 * preview opens the result screen (screens/Result.tsx); the form survives the trip.
 */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, getAssistantPlan, getSettings, previewInstallment, suggestMonthly } from "../api.ts";
import { formHint } from "../assistantText.ts";
import type { InstallmentKind } from "../api-types.ts";
import { THINK } from "../copy.ts";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Alert, Button, Card, ErrorState, Field, Loading, SettingsMissing } from "../components/ui.tsx";
import { SCENARIOS, type Scenario } from "../mock/persona.ts";
import { navigate } from "../router.ts";
import { thaiMonth } from "../thaiMonth.ts";
import {
  answerPreview,
  applySuggestion,
  canPreview,
  edit,
  emptyForm,
  firstDueChoices,
  getDraft,
  PLATFORM_MAX,
  setDraft,
  startPreview,
  suggestionRequest,
  toEntry,
  type Errors,
  type Form,
  type Stage,
} from "../thinkFirstForm.ts";
import { useLoad } from "../useLoad.ts";

const KINDS: InstallmentKind[] = ["purchase", "cash_withdrawal", "cash_loan"];
const SUGGEST_DELAY_MS = 300; // wait for the user to stop typing

/** The form needs the settings; the safe-amount hint is an extra that may fail alone. */
async function loadForm() {
  const settings = await getSettings();
  if (settings === null) return null;
  return { hint: await getAssistantPlan().then(formHint, () => null) };
}

export function ThinkFirstScreen() {
  const [load, reload] = useLoad(loadForm);
  return (
    <Screen route="think" title={THINK.title} back="home">
      {load.state === "loading" && <Loading lines={3} />}
      {load.state === "error" && <ErrorState onRetry={reload} />}
      {load.state === "ready" && (load.data === null ? <SettingsMissing onSetUp={() => navigate("settings")} /> : <ThinkFirst hint={load.data.hint} />)}
    </Screen>
  );
}

/** Demo deep link: "?persona&scene=YELLOW#/think" opens with that example checked. */
function sceneFromUrl(): Scenario | null {
  const scene = new URLSearchParams(window.location.search).get("scene");
  return scene === "GREEN" || scene === "YELLOW" || scene === "RED" ? scene : null;
}

/** A demo example fills every field, its first due month included (next month). */
function formFor(scenario: Scenario, base: Form): Form {
  const s = SCENARIOS[scenario];
  return {
    ...base,
    kind: "purchase",
    name: s.item_name,
    platform: "ShopDemo",
    price: s.item_price,
    months: String(s.months),
    monthly: s.monthly_amount,
    monthlyEdited: true,
    firstDue: firstDueChoices(new Date()).nextMonth,
  };
}

function ThinkFirst({ hint }: { hint: string | null }) {
  const [form, setForm] = useState<Form>(() => {
    const kept = getDraft();
    if (kept !== null) return kept.form; // back from the result screen ("แก้ไข")
    const scene = sceneFromUrl();
    return scene === null ? emptyForm() : formFor(scene, emptyForm());
  });
  const [errors, setErrors] = useState<Errors>({});
  const [stage, setStage] = useState<Stage>({ name: "form" });
  const [problem, setProblem] = useState<"failed" | "settings" | null>(null);
  const pending = useRef<string | null>(null); // the preview request still waited for

  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => ({ ...f, [key]: value, ...(key === "monthly" ? { monthlyEdited: true } : {}) }));
    pending.current = null;
    // A changed entry is a new entry: a pending verdict no longer applies.
    setStage((s) => (s.name === "checking" || s.name === "verdict" ? edit(s) : s));
  };

  // The 0% suggestion, from the API, until the user edits the monthly amount.
  const ask = suggestionRequest(form);
  const askKey = ask === null ? null : `${ask.price}|${ask.months}`;
  useEffect(() => {
    if (ask === null) return;
    const timer = setTimeout(() => {
      suggestMonthly(ask.price, ask.months).then(
        (monthly) => setForm((f) => applySuggestion(f, ask, monthly)),
        () => undefined, // no suggestion: the user types the amount
      );
    }, SUGGEST_DELAY_MS);
    return () => clearTimeout(timer);
    // `ask` is rebuilt every render; its key says when it really changed.
  }, [askKey]);

  function fill(scenario: Scenario) {
    setForm((f) => formFor(scenario, f));
    setErrors({});
    pending.current = null;
    setStage({ name: "form" });
  }

  useEffect(() => {
    if (getDraft() === null && sceneFromUrl() !== null) void preview();
    // Once, on open: the deep link's example.
  }, []);

  async function check(event: FormEvent) {
    event.preventDefault();
    await preview();
  }

  async function preview() {
    const built = toEntry(form, crypto.randomUUID());
    if (!built.ok) {
      setErrors(built.errors);
      return;
    }
    setErrors({});
    setProblem(null);
    const id = built.entry.client_request_id;
    pending.current = id;
    const checking = startPreview(built.entry);
    setStage(checking);
    try {
      const verdict = await previewInstallment(built.entry);
      if (pending.current !== id) return; // the form changed while waiting: drop it
      setDraft({ form, stage: answerPreview(checking, id, verdict) });
      navigate("result");
    } catch (error) {
      // Only an error for the request still waited for is reported.
      if (pending.current === id) {
        setProblem(error instanceof ApiError && error.code === "SETTINGS_REQUIRED" ? "settings" : "failed");
        setStage({ name: "form" });
      }
    }
  }

  if (problem === "settings") return <SettingsMissing onSetUp={() => navigate("settings")} />;

  const checking = stage.name === "checking";
  const cash = form.kind !== "purchase";
  return (
    <>
      <p className="text-body text-ink-muted">{THINK.intro}</p>
      {hint !== null && (
        <p className="flex items-start gap-2 rounded-field bg-leaf-50 px-3 py-2 text-body text-leaf-800">
          <Icon name="info" size={20} className="mt-0.5" />
          {hint}
        </p>
      )}
      <div className="flex flex-col gap-2 rounded-field border-2 border-dashed border-info-line bg-info-bg p-3">
        <span className="text-caption font-semibold text-info-ink">{THINK.demoTitle}</span>
        <div className="grid grid-cols-3 gap-2">
          {(["GREEN", "YELLOW", "RED"] as const).map((scenario) => (
            <button
              key={scenario}
              type="button"
              onClick={() => fill(scenario)}
              className="min-h-11 cursor-pointer rounded-pill border-2 border-info-line bg-card px-2 text-body font-semibold text-info-ink hover:bg-info-bg"
            >
              {THINK.demoScenario[scenario]}
            </button>
          ))}
        </div>
      </div>

      <form noValidate onSubmit={check} className="flex flex-col gap-4">
        <Card className="flex flex-col gap-5">
          <Choice
            legend={THINK.kindTitle}
            name="kind"
            value={form.kind}
            options={KINDS.map((kind) => ({ value: kind, label: THINK.kinds[kind] }))}
            onChange={(kind) => set("kind", kind)}
          />
          {cash && <p className="-mt-3 text-body text-ink-muted">{THINK.cashNoSaving}</p>}
          <Field
            label={THINK.itemName}
            value={form.name}
            onChange={(v) => set("name", v)}
            placeholder={THINK.itemNamePlaceholder}
            maxLength={100}
          />
          <Field
            label={THINK.platform}
            value={form.platform}
            onChange={(v) => set("platform", v)}
            placeholder={THINK.platformPlaceholder}
            maxLength={PLATFORM_MAX}
            error={errors.platform ?? null}
          />
          <Field
            label={cash ? THINK.cashAmount : THINK.price}
            value={form.price}
            onChange={(v) => set("price", v)}
            inputMode="decimal"
            suffix="บาท"
            placeholder="เช่น 12,000"
            error={errors.price ?? null}
          />
          <Field
            label={THINK.months}
            value={form.months}
            onChange={(v) => set("months", v)}
            inputMode="numeric"
            suffix="เดือน"
            placeholder="เช่น 10"
            maxLength={3}
            error={errors.months ?? null}
          />
          <Field
            label={THINK.monthly}
            value={form.monthly}
            onChange={(v) => set("monthly", v)}
            inputMode="decimal"
            suffix="บาท"
            placeholder="เช่น 1,200"
            help={THINK.monthlyHelp}
            error={errors.monthly ?? null}
          />
          <FirstDue value={form.firstDue} onChange={(v) => set("firstDue", v)} error={errors.firstDue ?? null} />
        </Card>
        <Button size="lg" type="submit" busy={checking} disabled={!canPreview(form)} icon="think">
          {checking ? THINK.checking : THINK.check}
        </Button>
      </form>

      {problem === "failed" && <Alert tone="info" title={THINK.failed} />}
    </>
  );
}

type ChoiceProps<T extends string> = {
  legend: string;
  name: string;
  value: T | "";
  /** `sub` is a second, smaller line (the first due month's "ต.ค. 2569"). */
  options: { value: T; label: string; sub?: string }[];
  onChange: (value: T) => void;
  help?: string;
  error?: string | null;
};

/** A row of large radio buttons (each at least 48px high). */
function Choice<T extends string>({ legend, name, value, options, onChange, help, error }: ChoiceProps<T>) {
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="mb-2 text-body font-semibold text-ink">{legend}</legend>
      <div className={`grid gap-2 ${options.length === 2 ? "grid-cols-2" : "grid-cols-3"}`}>
        {options.map((option) => (
          <label
            key={option.value}
            className={`relative flex min-h-12 cursor-pointer flex-col items-center justify-center rounded-field border-2 px-1 py-1 text-center text-body leading-tight font-semibold has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-leaf-600 ${
              value === option.value
                ? "border-leaf-700 bg-leaf-50 text-leaf-800"
                : `${error ? "border-risk-line" : "border-line"} bg-card text-ink-muted`
            }`}
          >
            <input
              type="radio"
              name={name}
              checked={value === option.value}
              onChange={() => onChange(option.value)}
              className="sr-only"
            />
            <span className="whitespace-nowrap">{option.label}</span>
            {option.sub !== undefined && (
              <span className="text-caption font-normal whitespace-nowrap">{option.sub}</span>
            )}
          </label>
        ))}
      </div>
      {help !== undefined && <p className="text-body text-ink-muted">{help}</p>}
      {error ? (
        <p role="alert" className="text-body font-semibold text-risk-ink">
          {error}
        </p>
      ) : null}
    </fieldset>
  );
}

function FirstDue({ value, onChange, error }: { value: string; onChange: (v: string) => void; error: string | null }) {
  const { thisMonth, nextMonth } = firstDueChoices(new Date());
  return (
    <Choice
      legend={THINK.firstDue}
      name="firstDue"
      value={value}
      options={[
        { value: thisMonth, label: THINK.firstDueThis, sub: thaiMonth(thisMonth) },
        { value: nextMonth, label: THINK.firstDueNext, sub: thaiMonth(nextMonth) },
      ]}
      onChange={onChange}
      help={THINK.firstDueHelp}
      error={error}
    />
  );
}
