# Facility Branches and Order Tracking Design

## Goal and constraints

Extend Facilities & map so staff can understand facility branches and follow both worker replenishment requests and facility-to-facility ASV vial transfers in a courier-style status view. Use existing parent-child relationships and persisted workflow records. Preserve server-side role scope and synthetic demo labeling. Do not imply vehicle GPS, a route-network service, or a measured transfer ETA.

## Approved approach

- Display authorized parent and child facilities as a hierarchy and connect authorized parent-child pairs on the map.
- Show courier-style progress for replenishment requests and interfacility transfers, including actual arrival time once recorded.
- Use a replenishment request's existing expected date as a planned delivery date. Transfers have no ETA source, so show no predicted arrival time for them.
- Keep animated movement clearly identified as a demo simulation; do not use it to infer a real position, speed, or arrival time.

## Facility hierarchy

- Build the visible branch tree from the existing `parent_id` relationships in the authorized facilities response.
- Show each authorized facility's parent and authorized child facilities in the map details/list, and draw a distinct connector between map markers when both facilities are in the user's authorized scope and have coordinates.
- Selecting a facility highlights its branch relationships and allows selecting a child or parent from the details.
- Do not display names, stock quantities, or map links for facilities that are outside the user's authorized scope. Hide a hierarchy edge when either endpoint is not in the authorized result.
- Preserve the existing risk-coded markers, nearby-support routes, search, and map/list toggle.

## Replenishment request tracking

- On Facilities & map, show requests associated with authorized destination facilities in a courier-style timeline: submitted, approved, dispatched, delivery received (including partial receipts), and stock verified.
- Use the existing request code, destination, quantity received/outstanding, status, expected date, creation time, approval time, and dispatch time.
- Add a persisted `received_at` timestamp to replenishment records and expose it through the request API. Update it when delivery quantity is recorded; for a fully received order it represents the final receipt time. Existing transaction timestamps remain the audit record for each partial receipt.
- Show the expected date as a planned arrival date, clearly distinguished from the actual received time. Do not create GPS routes for replenishments because the model does not identify a source facility.

## Facility-to-facility transfer tracking

- Show authorized transfers in a timeline: proposed, source verified, approved by both facilities, dispatched/in transit, partially received, and received/reconciled.
- Use existing verified, dispatched, and received timestamps and received/outstanding quantities. Show timestamps only where the record stores them.
- Keep the currently approved simulated movement marker and nearby-support route visually distinct. Do not show a transfer ETA because no transfer travel-time data is recorded.

## Access, data, and interface behavior

- Reuse the role-scoped `/facilities`, `/replenishments`, and `/transfers` APIs; include only records and facility details visible to the signed-in user.
- Replenishment receipt timestamp is written in the existing authorized receive action; it must not be client supplied.
- Refresh order and transfer status so newly dispatched and received records appear without a manual reload.
- When no active or recent records exist, show clear empty states. Label all synthetic records as demo data.
- Do not automatically approve, dispatch, or receive an order. Existing officer and worker actions remain the source of status changes.

## Out of scope

- Real GPS, vehicle/device integration, road routing, live courier APIs, or invented transfer ETAs.
- Changing the approval chain, stock ledger semantics, facility authorization policy, or procurement submission behavior.
- Showing inaccessible facilities merely to complete a hierarchy tree or route.

## Validation

- Confirm hierarchy connectors only render for authorized facilities and existing coordinates.
- Confirm replenishment timelines reflect each status and show the expected date separately from server-recorded receipt time.
- Confirm transfer timelines show stored milestone times and preserve the explicit simulated movement label.
- Build the frontend and check backend schema/API serialization and authorized receive behavior.
