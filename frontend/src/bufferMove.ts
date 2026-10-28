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

export type Mover = {
  /** Null when a move is already on its way: that press is ignored, so the money moves once. */
  press(amount: Money, forMonth?: string): Promise<MovedOut> | null;
};

/**
 * One move at a time, outside React state: two presses in the same task (before a
 * re-render disables the button) still send one request (UI-47, Bugs found in the
 * Session 17 log). The request is kept between presses as `moveRequest` says.
 */
export function mover(send: (body: MoveIn) => Promise<MovedOut>, newId: () => string, codeOf: (error: unknown) => string | null): Mover {
  let request: MoveRequest | null = null;
  let inFlight = false;
  return {
    press(amount, forMonth) {
      if (inFlight) return null;
      inFlight = true;
      const next = moveRequest(request, amount, newId(), forMonth);
      request = next;
      return send(moveBody(next)).then(
        (out) => {
          request = null;
          inFlight = false;
          return out;
        },
        (error: unknown) => {
          request = afterMoveError(next, codeOf(error));
          inFlight = false;
          throw error;
        },
      );
    },
  };
}
