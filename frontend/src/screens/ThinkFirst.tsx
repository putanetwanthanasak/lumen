/**
 * Screen 3: เช็กก่อนผ่อน, the form (DESIGN.md section 7.3, UI-37).
 * Every field in view, in this order: the item name and the app (both optional), the
 * price (ยอดเงิน for a cash item), the months (with quick picks), the monthly amount
 * and the first due month (no default). The price and the monthly amount are linked
 * both ways: one typed, the other is calculated and says so in one line under it;
 * both typed, neither changes (UI-72). The kind is ผ่อนสินค้า unless the user opens "เป็นรายการเงินสด?",
 * just above the price whose label it changes. The check sits in the bar above the
 * nav, always in view, disabled until the four required fields are valid. The preview
 * opens the result screen (screens/Result.tsx); the form survives the trip.
 */
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { getAssistantPlan, getSettings, needsSettings, previewInstallment, rejectedFields, suggestMonthly } from "../api.ts";
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
  calculatedNote,
  canPreview,
  changedBy,
  edit,
  emptyForm,
  exampleForm,
  firstDueChoices,
  getDraft,
  MONTH_CHIPS,
  PLATFORM_MAX,
  rejectedErrors,
  setDraft,
  shownErrors,
  startPreview,
  suggestionRequest,
  toEntry,
  typeLinked,
  withoutRejected,
  type FieldKey,
  type Form,
  type LinkedKey,
  type RejectedKey,
  type Stage,
} from "../thinkFirstForm.ts";
import { useLoad, type Load } from "../useLoad.ts";

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
  return <ThinkFirst load={load} reload={reload} />;
}

/** Demo deep link: "?persona&scene=YELLOW#/think" opens with that example checked. */
function sceneFromUrl(): Scenario | null {
  const scene = new URLSearchParams(window.location.search).get("scene");
  return scene === "GREEN" || scene === "YELLOW" || scene === "RED" ? scene : null;
}

/** A demo example fills every field, its first due month included (next month). */
function formFor(scenario: Scenario, base: Form): Form {
  return exampleForm(base, SCENARIOS[scenario], firstDueChoices(new Date()).nextMonth);
}

/**
 * The form with its screen around it in every state: one Screen from loading to ready,
 * so the header (its bell) and the nav are never mounted twice; the check's bar joins
 * it once the settings are in.
 */
export function ThinkFirst({ load, reload }: { load: Load<Awaited<ReturnType<typeof loadForm>>>; reload: () => void }) {
  const loaded = load.state === "ready" && load.data !== null;
  const [form, setForm] = useState<Form>(() => {
    const kept = getDraft();
    if (kept !== null) return kept.form; // back from the result screen ("แก้ไข")
    const scene = sceneFromUrl();
    return scene === null ? emptyForm() : formFor(scene, emptyForm());
  });
  const [touched, setTouched] = useState<ReadonlySet<FieldKey> | "all">(() => new Set());
  const [stage, setStage] = useState<Stage>({ name: "form" });
  const [problem, setProblem] = useState<"failed" | null>(null);
  // Fields the API refused (422), until the user edits them.
  const [rejected, setRejected] = useState<Partial<Record<RejectedKey, string>>>({});
  // A cash item is the exception: its kinds open on request, and stay open while one is chosen.
  const [kindsOpen, setKindsOpen] = useState(() => form.kind !== "purchase");
  const pending = useRef<string | null>(null); // the preview request still waited for
  const focusKind = useRef(false);
  const deepLinked = useRef(false);
  const formId = useId();
  const kindsId = useId();
  const needsId = useId();

  // Fields that changed: the API's refusal of them goes, and a pending verdict no longer applies.
  const changed = (keys: readonly string[]) => {
    setRejected((r) => withoutRejected(r, keys));
    pending.current = null;
    setStage((s) => (s.name === "checking" || s.name === "verdict" ? edit(s) : s));
  };
  const set = <K extends keyof Form>(key: K, value: Form[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    changed([key]);
  };
  // The price, the months or the monthly amount: a field the user did not type is recalculated (UI-72).
  const type = (key: LinkedKey, value: string) => {
    setForm((f) => typeLinked(f, key, value));
    changed(changedBy(form, key, value));
  };
  // Leaving a field: from then on it shows its error, if it has one.
  const leave = (key: FieldKey) => setTouched((t) => (t === "all" ? t : new Set(t).add(key)));

  // The 0% suggestion, from the API, while the monthly amount is not typed (UI-72).
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

  // The link that opened the kinds is gone: the keyboard moves to the chosen kind.
  useEffect(() => {
    if (!focusKind.current) return;
    focusKind.current = false;
    document.getElementById(kindsId)?.querySelector<HTMLInputElement>("input:checked")?.focus();
  }, [kindsOpen]);

  function fill(scenario: Scenario) {
    setForm((f) => formFor(scenario, f));
    setTouched(new Set());
    pending.current = null;
    setStage({ name: "form" });
  }

  useEffect(() => {
    // Once, when the settings are in: the deep link's example.
    if (!loaded || deepLinked.current) return;
    deepLinked.current = true;
    if (getDraft() === null && sceneFromUrl() !== null) void preview();
  }, [loaded]);

  async function check(event: FormEvent) {
    event.preventDefault();
    await preview();
  }

  async function preview() {
    const built = toEntry(form, crypto.randomUUID());
    if (!built.ok) {
      setTouched("all"); // cannot happen from the bar (disabled), but never sends a bad entry
      return;
    }
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
      if (pending.current !== id) return;
      setStage({ name: "form" });
      if (needsSettings(error)) {
        setDraft({ form, stage: { name: "form" } }); // kept for the way back from settings
        navigate("settings");
        return;
      }
      const fields = rejectedErrors(rejectedFields(error));
      if (fields === null) setProblem("failed");
      else setRejected(fields);
    }
  }

  if (load.state !== "ready" || load.data === null) {
    return (
      <Screen route="think" title={THINK.title} back="home">
        {load.state === "loading" && <Loading lines={3} />}
        {load.state === "error" && <ErrorState onRetry={reload} />}
        {load.state === "ready" && <SettingsMissing onSetUp={() => navigate("settings")} />}
      </Screen>
    );
  }

  const hint = load.data.hint;
  const checking = stage.name === "checking";
  const cash = form.kind !== "purchase";
  const errors = { ...shownErrors(form, touched), ...rejected };
  const ready = canPreview(form);
  // One line under the calculated field; none when both are typed. The monthly amount's
  // usual help while it is neither typed nor calculated yet (UI-72).
  const note = calculatedNote(form);
  const monthlyHelp = note?.field === "monthly" ? note.text : !form.monthlyTyped && form.monthly === "" ? THINK.monthlyHelp : undefined;
  // Always in view, above the nav; disabled until the four required fields are valid.
  const actions = (
    <div className="flex flex-col gap-2">
      {problem === "failed" && <Alert tone="info" title={THINK.failed} />}
      {!ready && (
        <p id={needsId} className="text-center text-body text-ink-muted">
          {THINK.checkNeeds}
        </p>
      )}
      <Button
        size="lg"
        type="submit"
        form={formId}
        busy={checking}
        disabled={!ready}
        describedBy={ready ? undefined : needsId}
        icon="think"
      >
        {checking ? THINK.checking : THINK.check}
      </Button>
    </div>
  );
  return (
    <Screen route="think" title={THINK.title} back="home" actions={actions}>
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

      <form id={formId} noValidate onSubmit={check}>
        <Card className="flex flex-col gap-5">
          <Field
            label={THINK.itemName}
            value={form.name}
            onChange={(v) => set("name", v)}
            placeholder={THINK.itemNamePlaceholder}
            maxLength={100}
            error={errors.name ?? null}
          />
          <Field
            label={THINK.platform}
            value={form.platform}
            onChange={(v) => set("platform", v)}
            onBlur={() => leave("platform")}
            placeholder={THINK.platformPlaceholder}
            maxLength={PLATFORM_MAX}
            error={errors.platform ?? null}
          />
          {kindsOpen || cash ? (
            <>
              <Choice
                id={kindsId}
                legend={THINK.kindTitle}
                name="kind"
                value={form.kind}
                options={KINDS.map((kind) => ({ value: kind, label: THINK.kinds[kind] }))}
                onChange={(kind) => set("kind", kind)}
              />
              {cash && <p className="-mt-3 text-body text-ink-muted">{THINK.cashNoSaving}</p>}
            </>
          ) : (
            <button
              type="button"
              onClick={() => {
                focusKind.current = true;
                setKindsOpen(true);
              }}
              className="-my-2 inline-flex min-h-11 cursor-pointer items-center self-start rounded-pill text-body font-semibold text-leaf-800 underline underline-offset-4 hover:bg-leaf-50"
            >
              {THINK.cashLink}
            </button>
          )}
          <Field
            label={cash ? THINK.cashAmount : THINK.price}
            value={form.price}
            onChange={(v) => type("price", v)}
            onBlur={() => leave("price")}
            inputMode="decimal"
            suffix="บาท"
            placeholder="เช่น 12,000"
            help={note?.field === "price" ? note.text : undefined}
            error={errors.price ?? null}
          />
          <div className="flex flex-col gap-2">
            <Field
              label={THINK.months}
              value={form.months}
              onChange={(v) => type("months", v)}
              onBlur={() => leave("months")}
              inputMode="numeric"
              suffix="เดือน"
              placeholder="เช่น 10"
              maxLength={3}
              error={errors.months ?? null}
            />
            <MonthChips value={form.months} onPick={(months) => type("months", months)} />
          </div>
          <Field
            label={THINK.monthly}
            value={form.monthly}
            onChange={(v) => type("monthly", v)}
            onBlur={() => leave("monthly")}
            inputMode="decimal"
            suffix="บาท"
            placeholder="เช่น 1,200"
            help={monthlyHelp}
            error={errors.monthly ?? null}
          />
          <FirstDue value={form.firstDue} onChange={(v) => set("firstDue", v)} error={errors.firstDue ?? null} />
        </Card>
      </form>
    </Screen>
  );
}

/** Quick picks under the months field: a tap fills it; the field still takes typing. */
function MonthChips({ value, onPick }: { value: string; onPick: (months: string) => void }) {
  return (
    <div className="grid grid-cols-4 gap-2">
      {MONTH_CHIPS.map((months) => {
        const picked = value.trim() === String(months);
        return (
          <button
            key={months}
            type="button"
            aria-pressed={picked}
            onClick={() => onPick(String(months))}
            className={`min-h-11 cursor-pointer rounded-pill border-2 px-1 text-body font-semibold whitespace-nowrap ${
              picked ? "border-leaf-700 bg-leaf-50 text-leaf-800" : "border-line bg-card text-ink hover:bg-leaf-50"
            }`}
          >
            {THINK.monthChip(months)}
          </button>
        );
      })}
    </div>
  );
}

type ChoiceProps<T extends string> = {
  id?: string;
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
function Choice<T extends string>({ id, legend, name, value, options, onChange, help, error }: ChoiceProps<T>) {
  return (
    <fieldset id={id} className="flex flex-col gap-2">
      <legend className="mb-2 text-body font-semibold text-ink">{legend}</legend>
      {/* Two to a row. Three: the first (ผ่อนสินค้า) takes its own row, so the two cash
          kinds never squeeze their labels, even in the 370px desktop frame (UI-37). */}
      <div className="grid grid-cols-2 gap-2">
        {options.map((option, i) => (
          <label
            key={option.value}
            className={`relative flex min-h-12 cursor-pointer flex-col items-center justify-center rounded-field border-2 px-1 py-1 text-center text-body leading-tight font-semibold has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-leaf-600 ${
              options.length % 2 === 1 && i === 0 ? "col-span-2" : ""
            } ${
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
