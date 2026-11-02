/**
 * A month bar's coloured parts (barSegments, UI-52), drawn on the caller's track, under
 * the caller's budget mark. A zero-wide part is not drawn; the first part drawn has the
 * round left end and the last the round right end. Every part after the first starts
 * with a 2px white gap (`GAP`, its left border in the card's white), as the result
 * chart's parts do: green and teal side by side are only 1.44:1 apart, and each holds
 * at least 3:1 against the white (UI-35). The gap is drawn inside the part (border-box),
 * so the parts' places stay barSegments' exact per mille; a sliver gives way to it.
 */
import { segmentStyle, type Segment } from "../barSegments.ts";

export const GAP = "border-l-2 border-card";

export function BarParts({ segments }: { segments: readonly Segment[] }) {
  const shown = segments.filter((s) => s.to > s.from);
  return (
    <>
      {shown.map((segment, i) => (
        <span
          key={segment.kind}
          className={`absolute inset-y-0 ${segment.className}${i === 0 ? " rounded-l-pill" : ` ${GAP}`}${i === shown.length - 1 ? " rounded-r-pill" : ""}`}
          style={segmentStyle(segment)}
        />
      ))}
    </>
  );
}
