/**
 * Screen 4: the buffer, feature 2 (DESIGN.md section 7.4, L66). The balance, the
 * plan for months over budget (GET /assistant/plan's buffer_plan), and the move back.
 * Moving money back is the user's own action and is never blocked; an amount above
 * the balance comes back as 422 AMOUNT_ABOVE_BALANCE and is shown next to the field.
 */
import { useState, type FormEvent } from "react";
import { ApiError, getAssistantPlan, getBuffer, moveToMain } from "../api.ts";
import { bufferPlanLines } from "../assistantText.ts";
import type { BufferOut, MovedOut } from "../api-types.ts";
import { ACCENT, BUFFER_METER, SOLID } from "../accent.ts";
import { ASSIST, BUFFER, MONEY_ERRORS } from "../copy.ts";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Alert, Button, Card, ErrorState, Field, Loading } from "../components/ui.tsx";
import { afterMoveError, moveRequest, type MoveRequest } from "../bufferMove.ts";
import { walletFor, WALLET_SEGMENTS } from "../homeLayout.ts";
import { formatBaht, parseMoneyInput } from "../money.ts";
import { useLoad } from "../useLoad.ts";

export function BufferScreen() {
  const [load, reload] = useLoad(getBuffer);
  return (
    <Screen route="buffer" title={BUFFER.title} accent="buffer">
      {load.state === "loading" && <Loading lines={2} />}
      {load.state === "error" && <ErrorState onRetry={reload} />}
      {load.state === "ready" && <BufferBody buffer={load.data} onMoved={reload} />}
    </Screen>
  );
}

function BufferBody({ buffer, onMoved }: { buffer: BufferOut; onMoved: () => void }) {
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [moved, setMoved] = useState<MovedOut | null>(null);
  // One id per amount: a retry of the same move (lost answer) moves the money once.
  const [request, setRequest] = useState<MoveRequest | null>(null);
  const [balance, setBalance] = useState(buffer.balance);
  // The last GET /buffer answer: the months covered and the monthly total are the API's.
  const [current, setCurrent] = useState(buffer);
  const cover = walletFor(current, balance); // null between a move and the next GET /buffer

  async function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = parseMoneyInput(amount);
    if (!parsed.ok) {
      setError(MONEY_ERRORS[parsed.reason]);
      return;
    }
    const next = moveRequest(request, parsed.value, crypto.randomUUID());
    setRequest(next);
    setError(null);
    setFailed(false);
    setBusy(true);
    try {
      const out = await moveToMain({ client_request_id: next.id, amount: parsed.value });
      setMoved(out);
      setBalance(out.balance);
      // The months covered for the new balance come from the API (review F4).
      getBuffer().then(setCurrent, () => undefined);
      setRequest(null);
      setAmount("");
    } catch (e) {
      const code = e instanceof ApiError ? e.code : null;
      setRequest(afterMoveError(next, code));
      if (code === "AMOUNT_ABOVE_BALANCE") {
        setError(BUFFER.aboveBalance);
      } else {
        // Unknown outcome: the money may already have moved. Say so, and read the
        // balance again instead of showing the old one (review B1 F4).
        setFailed(true);
        getBuffer().then((b) => {
          setBalance(b.balance);
          setCurrent(b);
        }, () => undefined);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p className="text-body text-ink-muted">{BUFFER.intro}</p>
      {/* The same wallet as on Home, larger: teal is the buffer on every screen. */}
      <section className={`flex flex-col gap-2 rounded-card border-2 p-5 ${ACCENT.buffer.tint} ${ACCENT.buffer.line}`}>
        <div className="flex items-center gap-3">
          <span className={`inline-flex h-12 w-12 items-center justify-center rounded-pill ${SOLID.buffer}`}>
            <Icon name={ACCENT.buffer.icon} size={28} />
          </span>
          <h2 className={`flex-1 text-body font-semibold ${ACCENT.buffer.ink}`}>{BUFFER.balance}</h2>
          {cover !== null && (
            <span aria-hidden="true" className="flex gap-1">
              {Array.from({ length: WALLET_SEGMENTS }, (_, i) => (
                <span key={i} className={`h-5 w-2.5 rounded-sm ${i < cover.filled ? BUFFER_METER.on : BUFFER_METER.off}`} />
              ))}
            </span>
          )}
        </div>
        <p className="text-display font-bold text-ink">{formatBaht(balance)}</p>
        {cover !== null && (
          <p className={`text-body font-semibold ${ACCENT.buffer.ink}`}>
            {current.months_covered === null
              ? BUFFER.nothingOwed
              : current.months_covered === 0
                ? BUFFER.coversNone
                : BUFFER.covers(current.months_covered)}
          </p>
        )}
        <p className="text-body text-ink-muted">{BUFFER.monthlyTotal(formatBaht(current.monthly_total))}</p>
      </section>

      {/* Reloads after a move, so "covered" or "still short" matches the balance above. */}
      <BufferPlanCard key={balance} />

      <Card className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-lead font-bold text-ink">{BUFFER.moveTitle}</h2>
          <p className="text-body text-ink-muted">{BUFFER.moveHelp}</p>
        </div>
        {moved !== null ? (
          <>
            <Alert tone="ok" title={BUFFER.moved(formatBaht(moved.amount))}>
              {BUFFER.balanceAfter(formatBaht(moved.balance))}
            </Alert>
            <Button
              variant="secondary"
              onClick={() => {
                setMoved(null);
                onMoved();
              }}
            >
              {BUFFER.another}
            </Button>
          </>
        ) : (
          <form noValidate onSubmit={submit} className="flex flex-col gap-4">
            <Field
              label={BUFFER.amount}
              value={amount}
              onChange={(v) => {
                setAmount(v);
                setError(null);
              }}
              inputMode="decimal"
              suffix="บาท"
              placeholder="เช่น 1,500"
              error={error}
            />
            {failed && <Alert tone="info" title={BUFFER.failed} />}
            <Button type="submit" busy={busy} icon="wallet">
              {busy ? BUFFER.moving : BUFFER.move}
            </Button>
          </form>
        )}
      </Card>
    </>
  );
}

/** The over-budget plan: the shortfall over every month, then covered or still short. */
function BufferPlanCard() {
  const [load] = useLoad(getAssistantPlan);
  if (load.state !== "ready") return null; // an extra: no plan, no card
  const { tone, lines } = bufferPlanLines(load.data.buffer_plan);
  const [head = "", ...rest] = lines;
  return (
    <Card className="flex flex-col gap-2">
      <h2 className="text-lead font-bold text-ink">{ASSIST.bufferTitle}</h2>
      {/* About the buffer: teal when it covers or is not needed, amber when still short. */}
      <Alert tone={tone === "ok" ? "buffer" : "warn"} title={head}>
        {rest.join(" ")}
      </Alert>
    </Card>
  );
}
