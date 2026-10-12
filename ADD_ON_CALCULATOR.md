# Existing-position add-on calculation

The live-analysis form now separates total portfolio value (positions + cash)
from the cash available for this stock's add-on. The former sets the existing
20% allocation and 1.5% mark-to-stop risk limits. The latter adds a separate
cash constraint. Do not enter remaining cash as the total portfolio value.

When the manual price is inside the valid entry zone, it is the proposed sizing
price. When outside, the upper zone boundary is used for a conditional scenario.
Existing shares are conservatively reserved at the greater of the manual price
and sizing price, so a hypothetical move back into the zone cannot understate
the future position value or risk. The actual current position value and this
valuation reference are both disclosed.

For N existing shares, total portfolio V, sizing price P, valuation price Q,
stop S and cash C:

- Allocation space = max(0.20 × V − Q × N, 0).
- Risk space = max(0.015 × V − max(Q − S, 0) × N, 0).
- New shares = min(floor(allocation space / P), floor(risk space / (P − S)),
  floor(C / P)). Decimal arithmetic is used before whole-share flooring.
- Cost = new shares × P; remaining cash = C − cost.
- Shares after = N + new shares.
- Weighted average after = (previous average × N + cost) / shares after.

The report exposes all three share limits, binding constraints, portfolio limit
amounts, price basis, cost, weighted average and the resulting total shares.
An exhausted limit or less than one affordable share produces a real zero with
specific numerical reasons. The implementation does not loosen limits to create
a positive quantity. Existing risk is measured from valuation to stop, not from
historical acquisition cost; the purchase average is used for cost averaging.

Missing/zero/fractional holdings are not assumed to be a zero position. Missing
cash keeps a theoretical portfolio-capacity calculation for older API clients,
but cannot produce an executable share quantity. Missing purchase average has
no invented average. The new frontend requires both holdings and purchase average
plus explicit cash (including explicit zero).

The executable quantity is zero for stale or unknown session freshness, invalid
or completed plans, a broken stop, an unspecified cash budget, or a price outside
the zone. Conditional sizing is labeled separately from an entry decision.
Changing any form input invalidates the prior result and any pending response;
the next calculation uses the new submitted snapshot.

Costs and averages exclude commissions and slippage. Risk is the modeled move
to the stop rather than a promise about execution price or maximum realized loss.
The add-on remains separate from the existing holding's hold/exit/profit-taking
decision and never writes live manual prices into historical candles.

Validation: 128 selected regression tests passed with one skipped. The production
frontend build and TypeScript checks passed. Desktop/mobile browser QA verified
a positive cash budget, an explicit zero cash budget, the weighted average,
clearing an edited result, discarding a late response and no mobile overflow or
JavaScript errors. Broken stops and expired plans have no sizing projection;
a fresh valid plan is required first.
