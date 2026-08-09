# Sprint 3B: Coverage Gate and Rescue

Sprint 3B adds the deterministic decision boundary between verified Candidates and later selection/freeze stages.

The public repository contains only generic decision logic. Private source identities, entity lists, search prompts, event content, and operational history remain in the private state store.

## Coverage confidence

The gate emits only `HIGH`, `MEDIUM`, or `LOW`; it does not manufacture a probability.

`LOW` is forced by unresolved critical coverage conditions such as a failed/missing C1 or C2 route, any failed/missing mandatory channel, at least two partial mandatory channels, an unresolved report gap, an incomplete required premium sweep, or abnormal-low signal volume combined with partial mandatory coverage.

If no LOW condition exists, one partial mandatory channel, any collector saturation, abnormal-low signal volume, due P0 pending work, or a rescue that was required results in `MEDIUM`.

`HIGH` requires complete mandatory coverage, completed premium sweep, no unresolved gap, no signal-volume anomaly, no saturation, no due P0 pending work, and no rescue/material rescue anomaly.

## Rescue trigger

Rescue is required when pre-rescue coverage is LOW, a previous report gap exists, signal volume is abnormally low, or the rolling critical-miss count is nonzero.

A rescue plan carries bounded budgets for broad discovery, the required premium-source sweep, Tier-A exact-entity checks, and a normal cap on new rescue Candidates. Critical P0 findings may be handled by the private worker outside the ordinary Candidate cap under the v11 specification.

Sprint 3B remains shadow-only and does not authorize writes to formal `Lite_EventIndex` or production delivery state.
