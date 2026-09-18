# Decision engine

The deterministic decision engine accepts exactly one versioned strategy proposal plus bounded `[0,1]` scores
for technical evidence, SMC/ICT evidence, regime compatibility, volume, options, data quality, and risk context.
An optional ML probability is an input score only. Missing ML is removed and active weights are renormalized;
deterministic decisioning therefore continues safely without a model.

Default weights are 20% technical, 20% SMC/ICT, 15% regime, 10% volume, 5% options, 5% optional ML, 15% data
quality, and 10% risk context. Configured weights must sum exactly to one. Entry proposals require confidence at
least 0.65, data quality at least 0.80, valid directional entry/stop/target geometry, and risk/reward at least
1.5. A failed gate returns `NO_TRADE`, removes proposed executable levels, and sets requested risk to zero.

`EXIT` and `HOLD` are preserved instead of applying new-entry thresholds. Strategy `NO_TRADE` remains
`NO_TRADE` and retains its reasons. The data snapshot ID and every contributing score are included in output.

## Safety boundary

The risk-context score is descriptive context, **not risk approval**. A `LONG` or `SHORT` result always has
`requires_risk_approval=true`. The engine cannot calculate final quantity, create an order intent, access a
broker, or override the independent risk engine. ML can influence only its configured bounded score and can
never directly authorize execution.
