/**
 * Screen 3b: the result of ประเมินภาระผ่อน (DESIGN.md section 7.3b), a screen of its
 * own. A one-line summary with "แก้ไข" (back to the form, every value kept), a large
 * verdict card, the month bars against the budget, what would be saved, then
 * "บันทึก" and "ยังไม่ซื้อ". Recording is always allowed, whatever the verdict.
 */
import { useState } from "react";
import { ApiError, getSettings, recordInstallment } from "../api.ts";
import type { ManualEntryIn, PreviewOut, RecordedOut } from "../api-types.ts";
import { THINK } from "../copy.ts";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Alert, Button, Card, ErrorState, Loading, SettingsMissing } from "../components/ui.tsx";
import { MonthBars, VerdictCard } from "../components/Verdict.tsx";
import { formatBaht, toSatang, type Money } from "../money.ts";
import { navigate } from "../router.ts";
import { thaiMonth } from "../thaiMonth.ts";
import { entryToRecord, getDraft, setDraft } from "../thinkFirstForm.ts";
import { useLoad } from "../useLoad.ts";

type View = { name: "result" } | { name: "recorded"; result: RecordedOut } | { name: "notBuying" };

export function ResultScreen() {
  const [load, reload] = useLoad(getSettings);
  const draft = getDraft();
  const stage = draft?.stage;
  const [view, setView] = useState<View>({ name: "result" });
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<"failed" | "settings" | null>(null);

  function finish(next: View) {
    setDraft(null); // the next ตรวจสอบก่อนผ่อน starts with an empty form
    setView(next);
  }

  async function record(entry: ManualEntryIn) {
    setProblem(null);
    setBusy(true);
    try {
      // Same entry, same client_request_id: a retry after a lost answer records once.
      finish({ name: "recorded", result: await recordInstallment(entry) });
    } catch (error) {
      setProblem(error instanceof ApiError && error.code === "SETTINGS_REQUIRED" ? "settings" : "failed");
    } finally {
      setBusy(false);
    }
  }

  const entry = stage === undefined ? null : entryToRecord(stage);
  const showActions = view.name === "result" && entry !== null && stage?.name === "verdict" && load.state === "ready";
  const actions = showActions ? (
    <div className="flex flex-col gap-1">
      <div className="grid grid-cols-[2fr_1fr] gap-3">
        <Button size="lg" onClick={() => void record(entry)} busy={busy} icon="check">
          {busy ? THINK.recording : THINK.record}
        </Button>
        <Button size="lg" variant="secondary" onClick={() => finish({ name: "notBuying" })} disabled={busy}>
          {THINK.notBuying}
        </Button>
      </div>
      {stage.name === "verdict" && stage.verdict.verdict === "RED" && (
        <button
          type="button"
          onClick={() => navigate("months")}
          className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 self-center rounded-pill px-3 text-body font-semibold text-leaf-800 underline underline-offset-4 hover:bg-leaf-50"
        >
          <Icon name="calendar" size={20} />
          {THINK.seeMonths}
        </button>
      )}
    </div>
  ) : undefined;

  return (
    <Screen route="result" title={THINK.resultTitle} back="think" showNav={view.name !== "result"} actions={actions}>
      {load.state === "loading" && <Loading lines={4} />}
      {load.state === "error" && <ErrorState onRetry={reload} />}
      {load.state === "ready" && load.data === null && <SettingsMissing onSetUp={() => navigate("settings")} />}
      {load.state === "ready" && load.data !== null && problem === "settings" && (
        <SettingsMissing onSetUp={() => navigate("settings")} />
      )}
      {load.state === "ready" && load.data !== null && problem !== "settings" && (
        <>
          {view.name === "recorded" && <Recorded result={view.result} />}
          {view.name === "notBuying" && <NotBuying />}
          {view.name === "result" &&
            (stage?.name === "verdict" ? (
              <Result entry={stage.entry} verdict={stage.verdict} budget={load.data.monthly_installment_budget} />
            ) : (
              <NoDraft />
            ))}
          {problem === "failed" && <Alert tone="info" title={THINK.failed} />}
        </>
      )}
    </Screen>
  );
}

function Result({ entry, verdict, budget }: { entry: ManualEntryIn; verdict: PreviewOut; budget: Money }) {
  const what = entry.item_name || (entry.kind === "purchase" ? THINK.summaryItem : THINK.summaryCash);
  const saves = toSatang(verdict.saving_if_recorded) > 0n;
  return (
    <>
      <div className="flex items-start gap-3 rounded-card border border-line bg-card px-4 py-3">
        <p className="flex-1 text-body text-ink">
          {THINK.summary(what, formatBaht(entry.item_price), entry.months, formatBaht(entry.monthly_amount), thaiMonth(entry.first_due_month))}
          {entry.platform_name !== null && <span className="text-ink-muted"> · {entry.platform_name}</span>}
        </p>
        <button
          type="button"
          onClick={() => navigate("think")}
          className="-my-1 inline-flex min-h-11 shrink-0 cursor-pointer items-center gap-1 rounded-pill px-3 text-body font-semibold text-leaf-800 hover:bg-leaf-50"
        >
          <Icon name="edit" size={18} />
          {THINK.edit}
        </button>
      </div>

      <VerdictCard verdict={verdict.verdict} size="hero" />

      <Card>
        <MonthBars months={verdict.months} budget={budget} />
      </Card>

      <Card className="flex items-center gap-4">
        <span
          className={`inline-flex h-14 w-14 shrink-0 items-center justify-center rounded-pill ${
            saves ? "bg-leaf-700 text-white" : "bg-leaf-50 text-leaf-700"
          }`}
        >
          <Icon name="shield" size={30} />
        </span>
        <div className="flex flex-col">
          <p className="text-body text-ink-muted">{saves ? THINK.savingTitle : THINK.savingNone}</p>
          {saves ? (
            <p className="text-title font-bold text-ok-ink">{formatBaht(verdict.saving_if_recorded)}</p>
          ) : (
            <p className="text-body text-ink-muted">{THINK.savingNoneHelp}</p>
          )}
        </div>
      </Card>

      <p className="text-center text-body text-ink-muted">{THINK.nowTotal(formatBaht(verdict.monthly_total))}</p>
    </>
  );
}

function NoDraft() {
  return (
    <Card className="flex flex-col gap-4">
      <p className="text-body text-ink">{THINK.noDraft}</p>
      <Button onClick={() => navigate("think")}>{THINK.toForm}</Button>
    </Card>
  );
}

function NotBuying() {
  return (
    <Card className="flex flex-col gap-4">
      <Alert tone="ok" title={THINK.notBuyingDone} />
      <Button onClick={() => navigate("think")} variant="secondary">
        {THINK.another}
      </Button>
      <Button onClick={() => navigate("home")} variant="ghost" icon="home">
        {THINK.backHome}
      </Button>
    </Card>
  );
}

function Recorded({ result }: { result: RecordedOut }) {
  const savedSomething = toSatang(result.saved_amount) > 0n;
  return (
    <>
      <Card className="flex flex-col items-center gap-3 py-8 text-center">
        <span className="inline-flex h-16 w-16 items-center justify-center rounded-pill bg-leaf-700 text-white">
          <Icon name="check" size={36} />
        </span>
        <h2 className="text-title font-bold text-ink">{THINK.savedTitle}</h2>
        <p className="text-body text-ink-muted">{THINK.newTotalLabel}</p>
        <p className="text-display font-bold text-ink">{formatBaht(result.monthly_total)}</p>
      </Card>
      <Card className="flex items-center gap-4">
        <span className="inline-flex h-12 w-12 items-center justify-center rounded-pill bg-leaf-50 text-leaf-700">
          <Icon name="shield" size={28} />
        </span>
        <div className="flex flex-col">
          <p className="text-body text-ink-muted">{savedSomething ? THINK.savedLabel : THINK.savedNothing}</p>
          {savedSomething && <p className="text-title font-bold text-ok-ink">{formatBaht(result.saved_amount)}</p>}
        </div>
      </Card>
      {result.warnings.verdict !== "GREEN" && <VerdictCard verdict={result.warnings.verdict} />}
      <Button onClick={() => navigate("home")} icon="home">
        {THINK.backHome}
      </Button>
      <Button onClick={() => navigate("think")} variant="secondary">
        {THINK.another}
      </Button>
    </>
  );
}
