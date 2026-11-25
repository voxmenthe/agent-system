# GammaGirlLab's pages

How the weekly SPX PDF of 10-25 (week of Oct 26-30; root 2114440610124054725 and five self-replies) maps into the
template. The layout may change; the template does not. The replay transcript is
`scripts/grok-X-adhoc/tests/fixtures/options-levels/2114440610124054725.md`.

| Page | What it holds | Where it goes |
|---|---|---|
| 1 | Header (week, regime, marks, OI refresh), six tiles (spot, gamma flip, net Γ per 1%, vol trigger, VIX, put wall), "The week in one line", "The Fed, Wednesday" | Clocks; Text boxes (every tile and both boxes) |
| 2 | 01 The map (levels, flip band, long-Γ cluster, 50/70/80% cones), 02 Scenario tree, 03 Gamma by day, 04 Not even both ways | Levels, Bands, Cones, Scenarios, Gamma by day, Hedging asymmetry, Text boxes |
| 3 | Page 2/2 header ("The asymmetry that matters"), 05 Skew, 06 Premium, 07 Vanna & charm | Text boxes; Premium, skew, vanna and charm |
| 4 | 08 Gamma by expiry, 09 Implied moves | Gamma by expiry, Implied moves, Bands (today's 70% range, audit_only) |
| 5 | 10 What leans which way (down and up lists), delta exposure, the Fed note, 11 The verdict | Text boxes, Regime, Customer flow |
| 6 | 12 The bottom line (the bigger tail, the relief fuel, the stance), footer | Text boxes; the footer's snapshot clock is the OI snapshot |

Reading notes:
- **The map's axis numbers are levels.** 7805 sits on the long-Γ cluster (7790-7820) and 7717 on the vol trigger
  (7715-20): type both as printed, the cluster also as a band. "8000 / 8100 call walls above" is two call_wall rows.
- **Kinds.** Week and upper call walls: call_wall. PUT WALL: put_wall. GAMMA FLIP: flip, and its band (7695-7722) as
  a shaded band. Vol trigger: vol_trigger. Put-heavy strikes and clusters: node. First and second stop: shelf. The
  scenario tree's break and reclaim lines: pivot, labeled "break line" and "reclaim".
- **Scenario tree.** "Fri 10/30 close · not a forecast": the weights are dated to the Friday OI snapshot. Copy the
  note under the tree (a Monday-open condition) as the Condition line.
- **Gamma by day.** "Fri close" is the snapshot day; "Mon 09:30" through "Fri 15:00" are ET clocks of the coming
  week. Date each row; two Friday rows are normal.
- **Not even both ways.** Flow on the way there: sell is negative, buy positive, "~flat · buy, then sell" is 0 with a
  Note. The headline "A 1% drop forces about 2.4× the hedging of a 1% rally" is the Line.
- **Implied moves.** Each expiry's ATM IV, straddle, ±1σ and 70% range. Only the run's own day's range is a band, and
  audit_only.
- **The QQQ card** prints QQQ strikes: unit QQQ, which the map places on NQ through the matched NDX/QQQ ratio. **A
  daily card** uses the daily form; its OI snapshot is that morning's, so its rows replace the weekly PDF's rows for
  the same expiries.
