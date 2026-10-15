# Demo Data and Information Truthfulness Design

## Goal

Make VenoTrack's synthetic demonstration information clear and trustworthy across the application. Preserve useful demo workflows while ensuring no synthetic record, estimate, missing value, or system status can reasonably be mistaken for verified real-world information.

## Context and constraints

- VenoTrack is an online-only hackathon MVP using synthetic demonstration data. It has no connection to e-Aushadhi, DVDMS, government production data, or live facility systems.
- Keep existing synthetic records so users can demonstrate inventory, risk, transfer, replenishment, and evaluation workflows.
- Existing risk values are deterministic rule-based planning estimates, not predictions from a trained ML model.
- Do not invent operational numbers, contact details, verified dates, system health, or model performance.
- Preserve existing role-based access and ASV-only scope.

## Design

### 1. Audit user-visible information

Review the seed, shared shell, dashboard, risk, inventory, facilities, replenishment, workflows, and Program metrics UI for factual-looking values and claims. Classify each item as:

1. Synthetic example record.
2. Value calculated from persisted records.
3. Rule-based forecast or recommendation.
4. Value or status not recorded by the application.

Use this classification to decide the label and source text shown to users.

### 2. Preserve and label synthetic examples

- Retain the seeded demo facilities, batches, transactions, requests, transfers, alerts, labels, and observations.
- Use consistent, visible wording such as “Synthetic demo data” or “Illustrative demo value” at the relevant page or record. Do not rely only on the login page or README to establish that the displayed record is fictional.
- Treat seeded facility coordinates as illustrative map positions and seeded phone numbers as non-operational demo values. Where a phone number is not necessary for the workflow, show “Not provided” rather than a plausible contact number.
- Keep synthetic examples out of any copy that claims actual stock availability, real-world alert performance, or live integration.

### 3. Show current app state accurately

- Replace unconditional “LIVE”, “updated just now”, and “All systems operational” statements with wording driven by a real successful data fetch or a supported service health signal.
- If the app cannot verify a service state, show neutral wording such as “Demo environment” or “Status unavailable”.
- Derive displayed refresh time from the actual successful query timestamp. Do not create an update time in UI copy.
- Ensure date/year selectors either filter the displayed data or are not presented as interactive controls.

### 4. Explain calculated values and forecasts

- Identify whether counts and rates come from persisted ledger/workflow records, synthetic seeded records, or calculated forecasts.
- Keep null, stale, unverified, and insufficient-sample states explicit. Use “Not recorded”, “Not verified”, or “Not enough data” where appropriate instead of invented values or success claims.
- Describe risk severity as the existing rule-based logistics estimate, including its key inputs and data-confidence caveat. Do not describe it as an ML model output.
- Keep Program metrics tied to independently reviewed labels and show sample size and synthetic status. Do not present synthetic evaluation numbers as real-world accuracy or effectiveness.

### 5. Scope and verification

- Update seed values or labels only where they appear operational or factual without evidence; preserve deterministic examples and their workflow coverage.
- Update shared shell and page-specific copy so the terminology is consistent across worker, officer, admin, and auditor views.
- Verify the affected pages in representative roles and confirm that values still update from API responses, empty/error states remain understandable, and no unsupported live/system-health claim remains.
- Do not add third-party or production data integrations as part of this cleanup.

## Acceptance criteria

- A user can tell at the point of use whether information is synthetic, persisted, calculated, forecast, or unavailable.
- No unconditional live timestamp or system-operational claim remains unless it is backed by an actual status source.
- Demo contact values and map locations are explicitly illustrative or displayed as not provided.
- Dynamic counts, dates, and selectors correspond to actual application data and behavior.
- Program metrics state their synthetic sample limitation and do not claim real-world model performance.
- No facility details outside the user's authorized scope are exposed.

## Risks and limits

- The application cannot replace synthetic values with authentic stock or facility information because no real operational source is connected.
- Historical synthetic rows in a user's existing database remain synthetic even after the UI copy changes; the app must label them, not imply that relabeling makes them real.
- Avoiding over-labeling is important: global demo status can be reinforced at page/record level without repeating lengthy disclaimers beside every number.
