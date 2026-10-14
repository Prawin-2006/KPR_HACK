# Facility Map and ASV Usage Design

## Goal and constraints

Improve the Facilities & map page so workers and supply officers can understand each facility's ASV vial position and see active transfers in context. Preserve the existing role-scoped facility access, server-derived usable inventory, transfer approvals, and synthetic demonstration data. Do not imply that VenoTrack has vehicle GPS or a government-system integration.

## Approved approach

Use an explicitly labeled simulated movement marker for dispatched transfers, and add a selected-facility detail view backed by existing facility, risk, reorder, and transaction records. This is appropriate to the online-only synthetic hackathon MVP and does not require a GPS provider.

## Facility detail and usage

- Selecting a facility from the map or facility list opens a detail panel with its name, kind, district, usable ASV vial quantity, and need quantity.
- Need quantity uses the existing reorder calculation, including target stock, usable quantity, confirmed incoming quantities due within lead time, estimated lead-time demand, and configured maximum. Show the calculation or a short explanation and its data-quality flags; do not present a forecast as a purchase order.
- Show the earliest recorded ASV batch expiry with batch identifier, remaining quantity, and days until expiry. If there is no eligible expiry date, say so rather than estimating one.
- Show weekly and monthly issue-quantity charts aggregated from the facility's ASV transaction ledger. Weekly view uses seven daily buckets; monthly view uses the most recent six calendar months. Receipts and adjustments are not consumption. Empty periods are zero, and missing ledger history is called out rather than synthesized.
- Server-side facility authorization applies to every detail/summary request. Usable quantity continues to exclude expired, quarantined, damaged, and quality-pending batches.

## Transfer movement on the map

- Continue to show facility markers and add a route plus animated, blinking marker only for transfers whose status is `dispatched` or `partially_received` and whose endpoints have coordinates.
- Interpolate the marker along the straight line between the source and destination coordinates in a repeating forward-and-back demo animation. The animation is a visual demo simulation, not a measurement of vehicle position; label it prominently as simulated and display the transfer code, status, quantity outstanding, and endpoint names. Do not show progress percentages or ETA as if measured.
- Refresh transfer status periodically so receipt/reconciliation removes the active marker. If no transfer is in transit, show a clear empty state. Do not loop completed or proposed transfers as if they were moving.
- Include dispatch timestamp in the transfer API response for status context. Do not add fabricated GPS coordinates or persist simulated locations.

## Page behavior

- Keep the existing map/list toggle, search, risk-coded facility markers, and nearby-transfer suggestions.
- Selecting a map marker or facility card selects the same facility and opens its details. The facility details also remain accessible in list view.
- Retain synthetic-data labeling and distinguish the simulated route from the existing live API refresh/status indicators.

## Validation and boundaries

- Keep the API response within the existing server-side facility authorization rules and use the established reorder calculation for need quantity.
- Build the frontend and review the map and selected-facility states in the running demo.
- No real GPS feed, vehicle hardware, route-network directions, actual ETA, new procurement submission, or change to transfer authorization is in scope. Straight-line route animation must never be described as live GPS tracking.
