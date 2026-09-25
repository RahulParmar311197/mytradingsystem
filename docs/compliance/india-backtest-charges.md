# India backtest charge schedules

The backtester models Indian order charges through an effective-dated `IndiaChargeSchedule`. Rates are decimal
fractions of turnover and are deliberately configuration data rather than timeless source constants. Each
schedule identifies its product (equity delivery, equity intraday, futures, or options), effective date, and name.

For each order the model calculates capped or percentage brokerage, exchange transaction charges, SEBI turnover
fees, IPFT, GST on brokerage plus exchange/SEBI/IPFT charges, side-specific STT, and buy-side stamp duty. It
returns every component as well as the total. This supports segment-specific asymmetric taxation, including
sell-side-only schedules, without burying rates in execution code.

No purportedly “current” statutory default is shipped in this repository. The official-source search available
during this implementation returned an authorization error, so committing unverified rates would create silent
financial-model risk. Before a schedule is used for research acceptance, an owner must verify it against dated
NSE/exchange circulars, SEBI circulars, applicable tax notifications, broker pricing, and the intended product;
record those references alongside the schedule and rerun cost sensitivity. Synthetic test rates verify formulas
only and are explicitly not production assumptions.

Changing a schedule must create a new name/effective date; historical runs must retain the schedule identity.
Charge modelling improves realism but does not establish strategy profitability or regulatory compliance.
