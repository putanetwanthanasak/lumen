/**
 * A month bar's coloured parts (barSegments, UI-52), drawn on the caller's track, under
 * the caller's budget mark. A zero-wide part is not drawn; the first part drawn has the
 * round left end and the last the round right end.
 */
import { segmentStyle, type Segment } from "../barSegments.ts";

export function BarParts({ segments }: { segments: readonly Segment[] }) {
  const shown = segments.filter((s) => s.to > s.from);
  return (
    <>
      {shown.map((segment, i) => (
        <span
          key={segment.kind}
          className={`absolute inset-y-0 ${segment.className}${i === 0 ? " rounded-l-pill" : ""}${i === shown.length - 1 ? " rounded-r-pill" : ""}`}
          style={segmentStyle(segment)}
        />
      ))}
    </>
  );
}
