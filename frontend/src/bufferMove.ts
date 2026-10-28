/**
 * Which client_request_id a buffer move sends (screen 4, L66), kept apart from
 * React so it can be tested (UI-13). One id per amount: a retry of the same amount
 * after a failure repeats the same move, so the money moves once. A new amount, or a
 * 422 (nothing moved), starts a new request.
 */
import { toSatang, type Money } from "./money.ts";

export type MoveRequest = { amount: Money; id: string };

export function moveRequest(previous: MoveRequest | null, amount: Money, newId: string): MoveRequest {
  // Compared by value: "1500" and "1500.00" are the same move (review B2 F3).
  return previous !== null && toSatang(previous.amount) === toSatang(amount) ? previous : { amount, id: newId };
}

/** After an error: forget the request only when the API says nothing moved. */
export function afterMoveError(request: MoveRequest, code: string | null): MoveRequest | null {
  return code === "AMOUNT_ABOVE_BALANCE" ? null : request;
}
