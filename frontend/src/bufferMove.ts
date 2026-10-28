/**
 * Which client_request_id a buffer move sends (screen 4, L66), kept apart from
 * React so it can be tested (UI-13, UI-47). One id per amount and month: a retry of
 * the same move after a failure repeats it, so the money moves once. A new amount,
 * another month, or a 422 (nothing moved), starts a new request.
 */
import type { MoveIn, MovedOut } from "./api-types.ts";
import { toSatang, type Money } from "./money.ts";

/** `forMonth` ("YYYY-MM"): "ใช้กันชนจ่ายส่วนที่เกิน" for that month; absent for a free move. */
export type MoveRequest = { amount: Money; id: string; forMonth?: string };

export function moveRequest(previous: MoveRequest | null, amount: Money, newId: string, forMonth?: string): MoveRequest {
  // Compared by value: "1500" and "1500.00" are the same move (review B2 F3).
  if (previous !== null && toSatang(previous.amount) === toSatang(amount) && previous.forMonth === forMonth) return previous;
  return forMonth === undefined ? { amount, id: newId } : { amount, id: newId, forMonth };
}

/** The body of POST /buffer/move-to-main: `for_month` only for a month's move. */
export function moveBody(request: MoveRequest): MoveIn {
  const body = { client_request_id: request.id, amount: request.amount };
  return request.forMonth === undefined ? body : { ...body, for_month: request.forMonth };
}

/** After an error: forget the request only when the API says nothing moved. */
export function afterMoveError(request: MoveRequest, code: string | null): MoveRequest | null {
  return code === "AMOUNT_ABOVE_BALANCE" ? null : request;
}

/**
 * Shared by every move: while one is out (`held`), every other press is ignored, and
 * `out` settles when it is answered, so a screen opened meanwhile can wait for it.
 */
export type MoveLock = { held: boolean; out?: Promise<void> | null };

export type Mover = {
  /** Null when a move is already on its way: that press is ignored, so the money moves once. */
  press(amount: Money, forMonth?: string): Promise<MovedOut> | null;
  /**
   * The request kept after an unknown outcome (a lost answer, a 500), until it is
   * answered: pressing again with its amount and month resends its id, so the
   * backend repeats the bank call once and never moves the money twice.
   */
  kept(): MoveRequest | null;
};

/**
 * One move at a time, outside React state: two presses in the same task (before a
 * re-render disables the button) still send one request (UI-47, Bugs found in the
 * Session 17 log). Pass one `lock` to every mover on a screen, so a move for another
 * month, or the free move, waits too (review F1). Each mover keeps its own request
 * between presses, as `moveRequest` says, so a retry still finds its id.
 */
export function mover(
  send: (body: MoveIn) => Promise<MovedOut>,
  newId: () => string,
  codeOf: (error: unknown) => string | null,
  lock: MoveLock = { held: false },
): Mover {
  let request: MoveRequest | null = null;
  return {
    press(amount, forMonth) {
      if (lock.held) return null;
      lock.held = true;
      const next = moveRequest(request, amount, newId(), forMonth);
      request = next;
      const answered = send(moveBody(next)).then(
        (out) => {
          request = null;
          lock.held = false;
          lock.out = null;
          return out;
        },
        (error: unknown) => {
          request = afterMoveError(next, codeOf(error));
          lock.held = false;
          lock.out = null;
          throw error;
        },
      );
      lock.out = answered.then(
        () => undefined,
        () => undefined,
      );
      return answered;
    },
    kept() {
      return lock.held ? null : request;
    },
  };
}

/**
 * The movers of the buffer screen, kept for the page, not for one screen: one lock,
 * and one mover per key (a month, or "free"). Leaving the screen and coming back while
 * a move is out finds the same lock and the same kept request, so it can never send
 * a second id for the same move (review round 2 F2).
 */
export function moverRegistry(make: (lock: MoveLock) => Mover): { lock: MoveLock; get(key: string): Mover } {
  const lock: MoveLock = { held: false, out: null };
  const movers = new Map<string, Mover>();
  return {
    lock,
    get(key) {
      const known = movers.get(key);
      if (known !== undefined) return known;
      const made = make(lock);
      movers.set(key, made);
      return made;
    },
  };
}

/**
 * For answers that may arrive out of order (GET /buffer after each move): `take()`
 * before asking, and show the answer only while `isLatest()` still holds, so an older
 * balance never replaces a newer one (review F1).
 */
export function latestOnly(): { take(): () => boolean } {
  let asked = 0;
  return {
    take() {
      asked += 1;
      const mine = asked;
      return () => mine === asked;
    },
  };
}
