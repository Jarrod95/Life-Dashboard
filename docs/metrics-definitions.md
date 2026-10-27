# Metric semantics

**Reported net worth:** cached value in row 2 of the dated snapshot column of Net Worth Tracking; missing formulas remain unavailable.

**Reconstructed net worth:** deliberately unavailable until the spreadsheet is checked for property equity/mortgage double-counting, subtotal/holding overlap and exchange/crypto overlap.

**Change:** latest reported value minus preceding reported dated snapshot. Missing prior values mean unavailable.

**Spending:** negative signed transactions are expenses; unclassified positive credits reduce net spending. Explicit transfers and card repayments are excluded by a preliminary text rule. **Income** requires an explicit salary/wage/income/interest classification, rather than assuming every positive transaction is income. Classify and verify refunds and repayments before trusting totals.

**Mortgage scenario:** end-of-month payments; monthly nominal interest = annual rate / 12 times max(principal − offset, 0); offset increases after each monthly payment. There are no taxes, fees, daily interest accrual, redraw or rental deductions in the estimate. Offset money stays liquid cash.

**Budget:** not imported until source budget frequency columns are confirmed; do not project one-off figures forward.
