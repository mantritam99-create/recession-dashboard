# Recession episode categories (sourcing for `model/regime_study.RECESSION_EPISODES`)

Episode boundaries (start/end year) are transcribed directly from a live pull of FRED
`USREC` (1926-01 to present), re-verified on every `model/regime_study.py` run via
`_demo()`'s assert against a fresh pull -- not hand-typed from memory. Category labels
below are a documented judgment call about the *dominant proximate cause* of each
recession, not something derivable from the price data itself. Two episodes are
boundary cases (flagged `mixed`) with no clean single cause; `sub_regime_sensitivity()`
in `model/regime_study.py` reports what happens to the sub-type playbook if each is
reclassified to its listed alternative.

| Episode | Category | Rationale |
|---|---|---|
| 1926-1927 | `demand_monetary` | Fed tightening into the mid-1920s agricultural/credit slowdown; no external supply shock. |
| 1929-1933 | `financial_credit` | Stock market crash (Oct 1929) followed by cascading bank failures/panics; the modern consensus (Bernanke and others) treats the banking-system collapse, not a demand or supply shock, as the central mechanism. |
| 1937-1938 | `demand_monetary` | Fed doubled reserve requirements (1936-37) while fiscal policy tightened simultaneously ("Roosevelt recession") -- a deliberate policy-driven demand contraction. |
| 1945 | `demand_monetary` | Post-WWII demobilization: war production wound down and government spending collapsed. |
| 1948-1949 | `demand_monetary` | Postwar inventory correction plus Fed tightening against inflation. |
| 1953-1954 | `demand_monetary` | Fed tightening and the end of Korean War spending. |
| 1957-1958 | `demand_monetary` | Fed tightening ("Eisenhower recession"); no oil/commodity shock. |
| 1960-1961 | `demand_monetary` | Fed tightening ("rolling readjustment" recession). |
| 1970 | `demand_monetary` | Fed tightening against Vietnam-era inflation. |
| 1973-1975 | `supply_shock` | OPEC oil embargo (Oct 1973) roughly quadrupled crude prices; textbook supply-shock recession. |
| 1980 | `supply_shock` | Iranian Revolution (1979) oil shock; Volcker's tightening had just begun but the proximate trigger was the oil-price spike. |
| 1981-1982 | `demand_monetary` | Volcker's deliberate disinflation via aggressive monetary tightening -- distinguished from 1980 as the primarily *monetary*-driven double-dip, though the 1979-80 oil shock's aftereffects still linger in the broader period. |
| 1990-1991 | `mixed` | Gulf War oil-price spike (Aug 1990 Iraq invasion of Kuwait) *and* the S&L/commercial-real-estate credit crisis were both live simultaneously -- no single dominant cause. **Alternative in sensitivity check: `supply_shock`** (the oil-spike framing). |
| 2001 | `mixed` | Dot-com bust (demand-side capex/equity collapse) *and* 9/11 (confidence/supply-chain disruption) both fall inside this recession -- no single dominant cause. **Alternative in sensitivity check: `demand_monetary`** (the dot-com framing). |
| 2008-2009 | `financial_credit` | Subprime mortgage collapse and the global financial crisis -- credit-system failure, not a commodity or classic demand shock (despite 2008's separate mid-year oil price spike, which was a symptom of the boom rather than the recession's cause). |
| 2020 | `exogenous` | COVID-19 pandemic and associated lockdowns -- neither a classic demand nor supply shock in the business-cycle sense; kept as its own category rather than forced into either bucket. |

## Sample-size consequence (why most sub-type buckets are gated)

Splitting 16 recession episodes across 5 categories leaves most buckets under
`MIN_N_EPISODES = 5`: `supply_shock` (n=2), `financial_credit` (n=2), `exogenous` (n=1),
`mixed` (n=2). Only `demand_monetary` (n=9) clears the gate for anything beyond a
descriptive mean/std -- see `sub_regime_playbook()`'s docstring. This is expected and
correctly enforced by the gate, not a bug: 100 years contains very few *independent*
supply-shock recessions, so any claim about "how commodities behave in supply-shock
recessions" is necessarily descriptive (n=2: 1973-75 and 1980), not a statistically
tested claim.
