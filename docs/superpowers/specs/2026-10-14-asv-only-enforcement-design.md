# VenoTrack ASV-Only Enforcement Design

## Goal and constraints

VenoTrack manages anti-snake venom (ASV) vials for rural health supply planning. The existing MVP already seeds a polyvalent ASV product, but its catalogue API and UI still permit arbitrary products. This change makes ASV-only scope a server-side invariant across active inventory, workflows, forecasts, reports, seed data, and UI. It preserves existing authentication, facilities, ledger, stock checks, transfers, replenishment, alerts, and evaluation behavior. The application remains online-only and uses synthetic demonstration data.

The first release has one supported catalogue entry: `ASV-POLY-001`, “Polyvalent Anti-Snake Venom”, unit `vial`. Product identity is fixed for this MVP. Batch, transaction, request, transfer, and report quantities continue to use vials.

## Approaches considered

1. **Validation-only generic catalogue.** Keep product creation but validate ASV category and vial units. This is flexible but cannot reliably distinguish an unrelated product mislabeled as ASV.
2. **Fixed ASV catalogue entry (recommended).** Make the existing seeded ASV product the only active product; remove product creation from the worker/officer UI and reject unsupported catalogue writes at the API. This is the smallest enforceable change for the current single-product MVP.
3. **Configurable approved ASV catalogue.** Add an approval subsystem for defining more ASV product types. This expands the product administration model without a current requirement or approved reference catalogue.

## Data and migration behavior

- Add an additive Alembic revision that identifies the one supported product using its exact identifier and canonical name, and ensures its category and unit are `Anti-snake venom` and `vial`.
- Do not infer ASV identity from a legacy category alone. Existing products that do not match the canonical identity, and their batches, remain in the database for preservation but become inactive and quarantined. Their transaction history and linked workflow records are retained.
- Exclude inactive/non-canonical products and their batches from active inventory APIs, stock calculations, forecasts, transfer suggestions, and CSV/evaluation summaries. Keep a migration audit/report for affected product and batch identifiers so an administrator can review what was excluded.
- Never silently delete or relabel legacy records. Document a database backup step and the review/report behavior before migration.

## Application behavior

- Centralize the canonical ASV identity and server-side eligibility checks. Product creation rejects any non-canonical identity. Batch creation, inventory transactions, replenishment requests and receipts, reorder drafts, transfers, and reports must resolve to an active canonical ASV product/batch.
- Keep existing ASV batch expiry, quality, verification, reconciliation, stockout-risk, transfer, replenishment, and role permissions unchanged. Ensure only usable verified in-date ASV vials enter forecasts and transfer availability.
- Update labels and forms to consistently say “ASV” and “vials”; remove generic product selection/creation affordances while retaining ASV batch selection where required.
- Keep synthetic seed data ASV-only and make seed/reset idempotent with the fixed canonical product.
- Update README with the fixed catalogue scope, migration preservation/exclusion behavior, backup guidance, and synthetic-data limitation.

## Validation

Add/update automated tests for rejection of unrelated product writes and references, exclusion of legacy rows from active totals/reports, vial quantity consistency, and continued ASV replenishment/transfer/forecast behavior. Run backend tests and the frontend production build. Review the migration against a database containing a non-ASV legacy product and verify its records remain preserved but are excluded from active inventory.

## Risks and boundaries

This release intentionally supports only the single seeded polyvalent ASV catalogue entry. Adding a second approved ASV product later requires a separately reviewed catalogue design. Legacy records that cannot be proven to match the canonical ASV identity remain preserved but quarantined and excluded; administrators must inspect the migration report and decide how to handle them. No patient-specific treatment advice, external procurement, government integration, or offline synchronization is introduced.
