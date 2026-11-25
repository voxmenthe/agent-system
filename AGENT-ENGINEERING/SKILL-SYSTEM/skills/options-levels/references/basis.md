# Moving levels onto front-month futures

`futures_basis.py` and `futures_levels_map.py` do this; these are the rules they hold (10-26's helper task), so a
reader can tell what a number on the map means.

- **The front month** is the quarterly contract until eight days before its expiry (ESZ26 and NQZ26 expire Fri Dec
  18, settling at the 06:30 PT special opening quotation). A level whose option expiry falls after the contract's is
  refused, never placed.
- **Matched bars.** The basis is the median of matched 5-minute bars, future minus cash index, matched on bar start:
  yfinance stamps a bar at its start, and ES=F quotes run about 10 minutes delayed, so two "last" quotes with
  different clocks are never differenced. During the cash session the forming bar is dropped; otherwise the last
  completed session's final hour is used. The map prints median, IQR and n, and the prior Friday's figure beside it.
- **Multiplicative carry.** F/S(now) = 1 + basis / index. Daily carry c = (F/S(now) − 1) / days to the SOQ;
  ratio(T) = 1 + c × days from option expiry T (13:00 PT) to the SOQ, exactly 1 at the contract's own expiry. An SPX
  level becomes SPX × ratio(T) in ES; SPY first takes the matched SPX/SPY ratio, QQQ the matched NDX/QQQ ratio. The
  markdown keeps the old additive figure for comparison.
- **Carry check.** The dividend yield implied by dated ^IRX minus the measured carry should sit in 0–3% for ES and
  0–2% for NQ; outside it the map flags the carry and never substitutes a constant.
- **Unavailable stays unavailable.** A conversion with no matched basis, or a basis session that crosses a roll,
  stays in the table as "basis unavailable" and never appears on the futures axis.
- **Clocks.** The chart's mark is the front month's delayed metadata price; `mkt levels today` uses the newest
  complete 5-minute bar. Either is a delayed quote, not an executable price.
