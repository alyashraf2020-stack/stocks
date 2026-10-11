# Stock technical dashboard

Every directory symbol has `/stocks/<ticker>` and the cache-only API
`GET /api/v1/egx/stocks/<ticker>/technical`. The report and the `/plans` table use
the same `StockPlansService`, so their scores and pullback levels agree.
Refresh uses the existing provider pipeline. No prices, candles or success
probabilities are hardcoded, and a failed symbol cannot remove other stocks.
The directory now also includes the screenshot's RUBX (Rubex), ISIN
EGS3A221C018, with verified Investing instrument 12950. Its price is fetched,
never copied from the screenshot. Listing identity is sourced from the public
[vendor security page](https://www.investing.com/equities/rubex-plastic), with
company information available on [its investor relations site](https://rubexegypt.eg/en/investor-relations/).

## What the dashboard displays

- Last completed EOD close, price change and its actual reference session.
- A line or candlestick chart, with 1W/1M/3M/6M/1Y display ranges.
- Entry, stop and first target overlay, and all three targets in plan cards.
- A signed technical score, five rating categories and every constituent vote.
- Indicator coverage and agreement, volatility and actual relative volume.
- Conditional pullback entry, stop, three targets, risk per share, risk percentage,
  target returns and reward/risk multiples. Breakout remains available in `/plans`.
- A link to the existing analysis using the user's current broker price.

The calculations require at least 50 validated sessions. Prices from future dates,
non-trading dates, other tickers, invalid HLCV and duplicate dates are excluded.
Missing market sessions are counted and disclosed; rows are never fabricated.
Older ratings can be inspected with their date, but are not current signals and
cannot generate a current entry plan. Suspended listings do not issue ratings.
Public Investing chart requests now validate every fetched page against the
directory's ticker/ISIN, the resolved instrument ID, Egypt market and EGP
currency. Unknown identities or mismatches return no chart instead of a guessed
match. Search and chart requests use the anonymous public edition context;
the page token is only held in memory and is not logged or saved.
Exact ticker/ID/page matches can also be resolved from the public Egypt country
screener, restricted to exchange 33, Egypt equities and non-CFD records. Its
prices are discarded. Successful identity metadata is cached for six hours;
failed directory requests are throttled for one minute. Chart identity must
still pass the separate directory ISIN check before historical prices are used.

Display ranges approximate 5/22/65/130/250 trading observations, not calendar
months. The percentage compares the latest close with the close immediately
before the selected observations. When that reference is absent, it uses the
first available close and labels the range partial. Indicators and plans are
computed on full history before the display slice. Changing the display range
does not change the latest rating. MACD's chart scale follows actual values.

## EGX26_V1 methodology

This is a documented deterministic rating. It is neither a trained AI model nor
a replica of any proprietary screenshot's score or decision engine. The general
composite-rating approach is described by
[TradingView's Technical Ratings documentation](https://www.tradingview.com/support/solutions/43000614331-technical-ratings/).
Our exact voting rules are returned in `indicators[].rule_ar` and implemented in
`backend/app/services/technical_rating.py`.

The 14 trend constituents are SMA and EMA at 10, 20, 30, 50, 100 and 200 sessions,
VWMA20 and HMA9. The 12 momentum constituents are RSI14, Stochastic14/3/3, CCI20,
ADX14, Awesome Oscillator5/34, Momentum10, ROC10, MACD12/26/9, Stochastic RSI14,
Williams %R14, Ultimate Oscillator7/14/28 and MFI14. This custom basket and its
rules intentionally have their own version identifier.

Each available constituent votes +1/0/-1. Calculate a mean separately for trend
and momentum, then average the two means and multiply by 100. Trend and momentum
each have 50% weight, even though their constituent counts differ. Categories:
score >50 strong buy; >10 buy; [-10,10] neutral; <-10 sell; <-50 strong sell.
The unrounded score selects the category; the display rounds to two decimals.

Missing/warming-up indicators are excluded from the denominator and appear as
unavailable. Coverage is available/26. Agreement is the fraction of available
votes matching the overall direction (neutral votes for a neutral score). It is
not statistical confidence or a predicted win rate; inputs can be correlated.
Long averages require their full 100/200 observations, so a 159-session symbol
reports 24/26 rather than claiming all 26 were calculated.

Seeded EMA starts with a simple period average and uses alpha=2/(period+1).
RSI and ATR use a simple initial average followed by Wilder's alpha=1/14.
RSI is 50 when both average gain/loss are zero, 100 for positive gains and no
losses, and 0 for losses and no gains. This fixes the previous flat-price RSI
behavior, and aligns the displayed RSI with the rating. MACD retains the
existing first-value-seeded EMA convention used in the chart. HMA uses WMA
lengths 4/9/3. VWMA and MFI require actual nonzero aggregate volume. A relative
comparison tolerance prevents floating-point noise producing trend changes.

Volatility labels are descriptive: ATR/close <2% low, 2–<5% medium, >=5% high.
These are application thresholds, not calibrated loss probabilities. The plan's
risk and return percentages use its planning entry, not the last close. Targets
reuse the existing plan engine's R multiples. Fees/slippage are not included,
and no target arrival time or invented 1–3 day forecast is promised.

## Validation

Deterministic tests cover a numerical RSI example, arithmetic Wilder seeding,
flat/rising/falling prices, warmups, zero volumes, price scaling, group weights,
stale/short/malformed history, session gaps, per-symbol reports and partial chart
ranges. The selected regression suite passed 147 tests, with one skipped and
one external-network indicator test deselected. The frontend production build
and TypeScript check passed. Browser QA passed on desktop and a 390px mobile
viewport: chart mode/range controls, the 26-row breakdown, a 180-stock table,
signal filtering, no page overflow, and no JavaScript errors.
Real source refreshes and technical reports succeeded for BIOC, RUBX and COMI
through the completed 2026-10-11 session. Their available history reports a
partial 24/26 rating rather than manufacturing 200-session averages.
The new-database smoke test found and fixes an existing seeder issue: explicitly
flush newly inserted identities before the BIOC correction when autoflush is
disabled, keeping insertion and correction inside the same transaction.

The repository also contains three pre-existing failing assertions in
`test_trade_plan_and_decision.py` and `test_zero_lag_policy.py`: they assume every
fresh setup is immediately actionable or expect outdated reason wording. They
fail unchanged on the previous release too; this update retains conditional
entry behavior rather than turning a fresh timestamp into permission to buy.
