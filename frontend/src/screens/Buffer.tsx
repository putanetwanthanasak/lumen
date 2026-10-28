/**
 * Screen 4: the buffer, feature 2 (DESIGN.md section 7.4, L66). The balance, each
 * month over budget with its state (GET /buffer/shortfalls, UI-46) and its move as
 * three steps (UI-47), and the free move back. Moving money is the user's own action
 * and is never blocked; an amount above the balance comes back as 422
 * AMOUNT_ABOVE_BALANCE and is said next to the button or the field.
 */
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, getBuffer, getShortfalls, moveToMain } from "../api.ts";
import { bufferPlanLines } from "../assistantText.ts";
import type { BufferOut, MovedOut, ShortfallsOut } from "../api-types.ts";
import { ACCENT, BUFFER_METER, EDGE, SOLID } from "../accent.ts";
import { ASSIST, BUFFER, BUFFER_STATE, MONEY_ERRORS } from "../copy.ts";
import { Icon } from "../components/Icon.tsx";
import { Screen } from "../components/Screen.tsx";
import { Alert, Button, Card, ErrorState, Field, Loading, MarkedText } from "../components/ui.tsx";
import { latestOnly, mover, moverRegistry } from "../bufferMove.ts";
import { cardMove, shortfallView, takeBufferMonth, type Prepare, type ShortfallView } from "../bufferState.ts";
import { walletFor, WALLET_SEGMENTS } from "../homeLayout.ts";
import { formatAmount, formatBaht, parseMoneyInput, type Money } from "../money.ts";
import { thaiMonth } from "../thaiMonth.ts";
import { useLoad } from "../useLoad.ts";

type BufferData = { buffer: BufferOut; shortfalls: ShortfallsOut | null };

async function loadBuffer(): Promise<BufferData> {
  // The months over budget are an extra: without them the balance and the free move still work.
  const [buffer, shortfalls] = await Promise.all([getBuffer(), getShortfalls().catch(() => null)]);
  return { buffer, shortfalls };
}

/**
 * Every move of the page, on one lock: a press while any move is out is ignored, also
 * after leaving the screen and coming back (UI-47). One mover per month, and "free".
 */
const MOVES = moverRegistry((lock) => mover(moveToMain, () => crypto.randomUUID(), (e) => (e instanceof ApiError ? e.code : null), lock));

/** What every move on the screen shares: whether one is out, and the balance before it. */
type Moves = { moving: boolean; setMoving: (on: boolean) => void; balanceNow: () => Money };

export function BufferScreen() {
  const [load, reload] = useLoad(loadBuffer);
  return (
    <Screen route="buffer" title={BUFFER.title} accent="buffer">
      {load.state === "loading" && <Loading lines={2} />}
      {load.state === "error" && <ErrorState onRetry={reload} />}
      {load.state === "ready" && <BufferBody buffer={load.data.buffer} shortfalls={load.data.shortfalls} onMoved={reload} />}
    </Screen>
  );
}

export function BufferBody({ buffer, shortfalls, onMoved }: { buffer: BufferOut; shortfalls: ShortfallsOut | null; onMoved: () => void }) {
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [moved, setMoved] = useState<MovedOut | null>(null);
  // One lock for every move on the page (review F1, round 2 F2); one id per amount and month.
  const [moving, setMoving] = useState(MOVES.lock.held);
  const free = MOVES.get("free");
  const [balance, setBalance] = useState(buffer.balance);
  // The balance as the API last said, read when a move starts (its "before").
  const latestBalance = useRef(buffer.balance);
  const showBalance = (value: Money) => {
    latestBalance.current = value;
    setBalance(value);
  };
  // The last GET /buffer answer: the months covered and the monthly total are the API's.
  const [current, setCurrent] = useState(buffer);
  const cover = walletFor(current, balance); // null between a move and the next GET /buffer
  // The months over budget as the API last said; read again after every move.
  const [months, setMonths] = useState(shortfalls);
  const [reads] = useState(latestOnly);
  const refresh = () => {
    const isLatest = reads.take(); // an older answer never replaces a newer one
    getBuffer().then((b) => {
      if (!isLatest()) return;
      showBalance(b.balance);
      setCurrent(b);
    }, () => undefined);
    getShortfalls().then((s) => isLatest() && setMonths(s), () => undefined);
  };
  const moves: Moves = { moving, setMoving, balanceNow: () => latestBalance.current };

  // Opened from Home or ภาระผ่อนรายเดือน at a month: show that month's card.
  useEffect(() => {
    const month = takeBufferMonth();
    if (month !== null) document.getElementById(prepareId(month))?.scrollIntoView({ block: "center" });
  }, []);

  // Opened while a move from an earlier visit is still out: wait for it, then read again.
  useEffect(() => {
    const out = MOVES.lock.out;
    if (out === null || out === undefined) return;
    let live = true;
    void out.then(() => {
      if (!live) return;
      setMoving(false);
      refresh();
    });
    return () => {
      live = false;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    const parsed = parseMoneyInput(amount);
    if (!parsed.ok) {
      setError(MONEY_ERRORS[parsed.reason]);
      return;
    }
    const pending = free.press(parsed.value); // the free move: no month
    if (pending === null) return;
    setError(null);
    setFailed(false);
    setBusy(true);
    setMoving(true);
    try {
      const out = await pending;
      setMoved(out);
      showBalance(out.balance);
      // The months covered for the new balance come from the API (review F4).
      refresh();
      setAmount("");
    } catch (e) {
      if (e instanceof ApiError && e.code === "AMOUNT_ABOVE_BALANCE") {
        setError(BUFFER.aboveBalance);
      } else {
        // Unknown outcome: the money may already have moved. Say so, and read the
        // balance again instead of showing the old one (review B1 F4).
        setFailed(true);
        refresh();
      }
    } finally {
      setBusy(false);
      setMoving(false);
    }
  }

  return (
    <>
      <p className="text-body text-ink-muted">{BUFFER.intro}</p>
      {/* The same wallet as on Home, larger, with its edge: teal is the buffer on every screen. */}
      <section className={`flex flex-col gap-2 rounded-card p-5 ${ACCENT.buffer.tint} ${EDGE.buffer}`}>
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

      {months !== null && (
        <ShortfallSection
          shortfalls={months}
          moves={moves}
          onMoved={(out) => {
            showBalance(out.balance);
            refresh();
          }}
          onUnknown={refresh}
        />
      )}

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
              disabled={moving}
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
            {/* The free move: no month (no for_month), so it prepares nothing. */}
            <Button type="submit" busy={busy} disabled={moving} icon="wallet" variant="secondary">
              {busy ? BUFFER.moving : BUFFER.move}
            </Button>
          </form>
        )}
      </Card>
    </>
  );
}

const prepareId = (month: string) => `prepare-${month}`;

/**
 * Each month over budget, in date order: its state, and while it is not prepared, its
 * move. The summary on top is the API's (`covered`, `still_short`, over the gaps left).
 */
function ShortfallSection({
  shortfalls,
  moves,
  onMoved,
  onUnknown,
}: {
  shortfalls: ShortfallsOut;
  moves: Moves;
  onMoved: (out: MovedOut) => void;
  onUnknown: () => void;
}) {
  const { tone, lines } = bufferPlanLines(shortfalls);
  const [head = "", ...rest] = lines;
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-lead font-bold text-ink">{shortfalls.months.length === 0 ? ASSIST.bufferTitle : BUFFER_STATE.sectionTitle}</h2>
      {/* About the buffer: teal when it covers or is not needed, amber when still short. */}
      <Alert tone={tone === "ok" ? "buffer" : "warn"} title={head}>
        {rest.join(" ")}
      </Alert>
      {shortfalls.months.map((row) => (
        <PrepareCard key={row.month} view={shortfallView(row, shortfalls.balance)} moves={moves} onMoved={onMoved} onUnknown={onUnknown} />
      ))}
    </section>
  );
}

type Done = { out: MovedOut; before: Money };

/**
 * One month over budget. Not or partly prepared: the three steps and
 * "ใช้กันชนจ่ายส่วนที่เกิน", which moves the amount the API gave with `for_month`. Once
 * moved, the steps show the API's numbers and the success line; the state line comes
 * from the next GET /buffer/shortfalls. A retry after a lost answer sends the same id,
 * so the money moves once; a press while any move on the screen is out is ignored (UI-47).
 */
function PrepareCard({
  view,
  moves,
  onMoved,
  onUnknown,
}: {
  view: ShortfallView;
  moves: Moves;
  onMoved: (out: MovedOut) => void;
  onUnknown: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const forMonth = MOVES.get(view.month);
  const [done, setDone] = useState<Done | null>(null);
  // A move whose outcome is unknown keeps its button and its id (review round 2 F1).
  const kept = forMonth.kept();
  const prepare: Prepare | null = done === null ? cardMove(view, kept) : null;
  const unsure = problem ?? (kept !== null && !busy ? BUFFER.failed : null);
  const month = thaiMonth(view.month);

  async function move(p: Prepare) {
    const pending = forMonth.press(p.amount, p.month);
    if (pending === null) return; // another move on the screen is out
    // The balance before this move, as the API last said (never the first load's).
    const before = moves.balanceNow();
    setProblem(null);
    setBusy(true);
    moves.setMoving(true);
    try {
      const out = await pending;
      setDone({ out, before });
      onMoved(out);
    } catch (e) {
      const above = e instanceof ApiError && e.code === "AMOUNT_ABOVE_BALANCE";
      setProblem(above ? BUFFER.aboveBalance : BUFFER.failed);
      if (!above) onUnknown(); // the money may have moved: read the balance again
    } finally {
      setBusy(false);
      moves.setMoving(false);
    }
  }

  const amount = done?.out.amount ?? prepare?.amount ?? null;
  return (
    <Card className="flex flex-col gap-3">
      <div id={prepareId(view.month)} className="scroll-mt-4">
        <MarkedText item={view.line} className="font-semibold" />
      </div>
      {amount !== null && (
        <ol aria-label={BUFFER_STATE.stepsLabel} className="flex flex-col gap-2">
          <Step n={1} done={done !== null}>
            {done === null
              ? BUFFER_STATE.step1(formatBaht(amount))
              : BUFFER_STATE.step1Done(formatBaht(amount), formatAmount(done.before), formatBaht(done.out.balance))}
          </Step>
          <Step n={2} done={done !== null}>
            {BUFFER_STATE.step2(formatBaht(amount))}
          </Step>
          <Step n={3} done={false}>
            {BUFFER_STATE.step3(month, formatBaht(view.total))}
          </Step>
        </ol>
      )}
      {done !== null && <Alert tone="ok" title={BUFFER_STATE.success(formatBaht(done.out.amount), formatBaht(done.out.balance))} />}
      {prepare !== null && (
        <>
          <p className="text-body text-ink-muted">{BUFFER_STATE.helper}</p>
          {unsure !== null && <Alert tone="info" title={unsure} />}
          <Button variant="buffer" icon={ACCENT.buffer.icon} busy={busy} disabled={moves.moving} onClick={() => void move(prepare)}>
            {busy ? BUFFER_STATE.moving : BUFFER_STATE.use}
          </Button>
        </>
      )}
      {/* Not prepared and nothing to move: the buffer is empty. */}
      {prepare === null && done === null && view.state !== "prepared" && <p className="text-body text-ink-muted">{BUFFER_STATE.empty}</p>}
    </Card>
  );
}

/** A numbered step; ① and ② get a check once the API answered, ③ is always the user's own. */
function Step({ n, done, children }: { n: number; done: boolean; children: string }) {
  return (
    <li className="flex items-start gap-3 text-body text-ink">
      <span
        aria-hidden="true"
        className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-pill text-caption font-bold ${done ? SOLID.buffer : `${EDGE.buffer} ${ACCENT.buffer.ink}`}`}
      >
        {done ? <Icon name="check" size={16} /> : n}
      </span>
      <span className="pt-0.5">{children}</span>
    </li>
  );
}
