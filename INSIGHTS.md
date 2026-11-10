# Findings

Numbers below are computed by `src/hbp/analytics.py` from `data/snapshot/`. They are not typed in by hand. The dashboard reads the same calculation through `site/data/dashboard.json`.

Access date for every file in the snapshot: **10 November 2026**.

## What the files say

1. **546,789 home batteries** have had certificates approved, from 1 July 2025 through 30 September 2026. Together they are **15.3 GWh** of usable storage, about **28 kWh** each. The Clean Energy Regulator's own state table sums to the same 546,789. Ministers said the program had passed 600,000 batteries and about 16.6 GWh in the first days of November 2026. That gap is later installations and applications still waiting. This project does not inflate the file to match the speech. At 28 kWh each, 600,000 batteries would be about 16.8 GWh, which is in the same neighbourhood as the reported 16.6 GWh. That is a check, not a measured total.

2. **Installations fell from 87,128 in April 2026 to 23,679 in May**, a 73% drop, in the first month the full discount applied only to the first 14 kWh. July, August and September 2026 are still being lodged (the creation window is 12 months), so September's 14,855 is not treated as a collapse in demand.

3. **Uptake is uneven.** Per 1,000 occupied private dwellings in the 2021 Census: South Australia 87.5, New South Wales 64.5, Western Australia 63.4, the ACT 61.2, Queensland 59.1, Victoria 46.0, Tasmania 26.0, the Northern Territory 19.3. New South Wales has the most batteries (187,154) because it has the most homes, not the highest rate. Postcode assignment uses Australia Post ranges. A few dozen systems sit in postcodes that cross a border, so state totals differ from the regulator's own state table by less than 150 systems. The national total matches exactly.

4. **Wholesale price swings pay a battery back only in South Australia, and only just.** Over the 365 days from 1 November 2025 to 31 October 2026, the gap between the cheapest two midday hours and the dearest two evening hours averaged **$207/MWh in South Australia** and **$64/MWh in Tasmania**. South Australia's cheap window averaged **−$8/MWh** (a battery was paid to charge, on the average day). A 10 kWh battery doing one such cycle a day, keeping 90% of the energy, would have earned **$760** in South Australia and **$217** in Tasmania. At the Solar Choice November 2026 after-rebate price of **$7,384**, that is **9.7 years** in South Australia and **34.1 years** in Tasmania. New South Wales is 18.5 years, Queensland 20.0, Victoria 21.2.

5. **The next scheduled cut does not change the ranking.** From 1 January 2027 the certificate factor falls from 6.8 to 5.7. At the $40 clearing-house price a 10 kWh battery loses $440 (68 certificates become 57). Payback becomes 10.3 years in South Australia and 36.1 years in Tasmania. Treasury is drafting further options for the December budget. Those options are not published, so they are not modelled. May 2026 is the evidence of what a tighter discount does to installations.

Western Australia and the Northern Territory are not in the east-coast wholesale market. Their uptake is on the map. Their payback is not, because these prices do not apply there. The ACT is on the New South Wales regional price.

## Assumptions

| Choice | Value | Why |
| --- | --- | --- |
| Battery sizes | 10 kWh and 20 kWh | The two sizes in the Solar Choice Battery Price Index of 6 November 2026. A 13.5 kWh price is not in that table, so it is not invented. |
| Price the household pays today | $7,384 for 10 kWh, $14,172 for 20 kWh | Battery-only national average, installation and GST included, federal discount already taken off. A home that needs a new inverter pays more. |
| Certificate price | $40 | The statutory clearing-house price. Installers sometimes pass through less, so the cut scenario is an upper bound on the extra dollars. |
| Factor today | 6.8, full to 14 kWh, 60% to 28 kWh, 15% to 50 kWh | DCCEEW table for 1 May 2026 to 31 December 2026. Counts are rounded down: 68 certificates for 10 kWh, 119 for 20 kWh. |
| Factor in the cut | 5.7 | The factor already legislated for 1 January 2027 to 30 June 2027. Not a guess at the December budget. |
| Round trip | 90% | A typical home lithium battery. Not measured in these files. |
| Cycles | One a day | Cheapest 2 hours ending between 12:00 and 15:00, dearest 2 hours ending between 18:00 and 21:00, NEM time. A 10 kWh battery needs about 5 kW for those two hours. A 20 kWh battery needs about 10 kW. Value scales with size only if the battery can actually move that energy in the window. |
| Earnings | Wholesale only | Storing the household's own solar, virtual-power-plant payments, and network tariffs are not in the price file. Those usually make a battery look better than this. Treat the years as a slow, wholesale-only view. |
| Homes | Occupied private dwellings, Census 2021 table G34 | The denominator is five years older than the batteries. New estates look more crowded with batteries than they are. State rates are safer than a single postcode. |
| Negative earnings | Floored at zero | A day whose evening price does not cover the losses is skipped, not charged as a loss. |

## Caveats

- Certificate data lags installation. The latest months will rise.
- The solar count is systems registered since 2001, not systems still on the roof.
- NEM time stays on AEST all year. Clocks in Melbourne and Sydney move to AEDT. The labels say so.
- One postcode, 2765 in September 2026, is deliberately written as 113 and then put back to the real 112 inside the lakehouse, so a row update can be shown. The restored snapshot matches the file. The dashboard does not read the drilled snapshot.
