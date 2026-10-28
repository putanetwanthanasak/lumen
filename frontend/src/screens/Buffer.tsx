/**
 * Screen 4: the buffer (DESIGN.md section 7.4, L66).
 * Moving money back is the user's own action and is never blocked; an amount above
 * the balance comes back as 422 AMOUNT_ABOVE_BALANCE and is shown next to the field.
 */
import { useState, type FormEvent } from "react";
import { ApiError, getBuffer, moveToMain } from "../api.ts";
import type { BufferOut, MovedOut } from "../api-types.ts";
import { BUFFER, MONEY_ERRORS } from "../copy.ts";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Alert, Button, Card, ErrorState, Field, Loading } from "../components/ui.tsx";
import { afterMoveError, moveRequest, type MoveRequest } from "../bufferMove.ts";
import { formatBaht, parseMoneyInput } from "../money.ts";
import { useLoad } from "../useLoad.ts";

export function BufferScreen() {
  const [load, reload] = useLoad(getBuffer);
  return (
    <Screen route="buffer" title={BUFFER.title}>
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
        getBuffer().then((b) => setBalance(b.balance), () => undefined);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <p className="text-body text-ink-muted">{BUFFER.intro}</p>
      <Card className="flex flex-col gap-2">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-12 w-12 items-center justify-center rounded-pill bg-leaf-50 text-leaf-700">
            <Icon name="shield" size={28} />
          </span>
          <h2 className="text-body text-ink-muted">{BUFFER.balance}</h2>
        </div>
        <p className="text-display font-bold text-ink">{formatBaht(balance)}</p>
        <p className="text-body text-ink-muted">
          {buffer.months_covered === null
            ? BUFFER.nothingOwed
            : buffer.months_covered === 0
              ? BUFFER.coversNone
              : BUFFER.covers(buffer.months_covered)}
        </p>
        <p className="text-body text-ink-muted">{BUFFER.monthlyTotal(formatBaht(buffer.monthly_total))}</p>
      </Card>

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
