# Budget page

The existing finance importer reads the left-hand Net Income / Expenses / Investment Property sections of Budget. Column G (Yearly) is the canonical cached amount. Right-hand gross income and tax calculations, totals and savings rows are intentionally excluded. A missing cached value or unexpected layout rejects the entire plan and retains the prior successful plan, if any. Save/recalculate the workbook in Excel before syncing.

The fiscal year is the starting year (July–June). One current snapshot per financial year is stored using the existing budget_lines table; reimport replaces that year's lines. No schema migration, new services or dependency changes. Old importer versions trigger reimport on the next successful sync. Workbook contents and account identifiers are not committed.

The page at /finance/budget and API /api/v1/finance/budget/comparison?fiscal_year=2026&month=11 use existing classified transactions. Month=all covers the financial year through the latest observed date (not beyond today). The annual plan is divided by 12 and prorated by calendar days for partial months. Data coverage is inferred from the overall transaction date range, not a guarantee that every account is complete.

Mappings are conservative and single-assignment; unmatched categories are reported separately. Missing matches are unavailable, not zero. Salary and rental credits are distinguished from internal credits; mortgage payer-side payments count once, interest and transfers do not. BNPL payments and unmatched credits are disclosed separately. Review aliases against actual transactions before treating the numbers as definitive. A current rent plan should not be interpreted as the historical budget. The workbook's mortgage annual input needs verification because it can reference estimated interest rather than the contractual repayment. Savings scenarios calculate 10/15/20% of net income and exclude estimated tax refunds.

## Operator validation
- Run the normal test suite and review the budget page in both themes.
- Merge to main only after tests pass; pull main on the VPS, then use the existing stop/start scripts.
- Run the finance source sync (or configured workbook import) once. Confirm the FY, import number, source cell references and missing-match warnings.
- Compare mortgage and rent actuals to bank statements and review unallocated categories, especially setup expenses, before relying on cash-flow estimates.
