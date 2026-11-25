"""Quote-derived ranges and explicitly assumed SPX inventory scenarios."""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from statistics import median

import numpy as np
from scipy.special import ndtr

from options_app.options_market_calendar import regular_session_bounds
from spx_sources import Contract

MODELS = {
    "calls_long_puts_short": (1.0, -1.0),
    "half_calls_long_puts_short": (0.5, -1.0),
    "calls_long_half_puts_short": (1.0, -0.5),
    "all_short_bound": (-1.0, -1.0),
    "all_long_bound": (1.0, 1.0),
}
YEAR_SECONDS = 365 * 24 * 3600


@dataclass(frozen=True)
class SurfaceRow:
    contract: Contract
    forward: float
    discount: float
    years: float
    a: float
    delta: float
    side: str


def black_price(
    forward: float, strike: float, a: float, side: str, discount: float = 1.0
) -> float:
    if min(forward, strike, a, discount) <= 0 or side not in ("call", "put"):
        raise ValueError("Black inputs must be positive with a call/put side")
    d1 = math.log(forward / strike) / a + a / 2
    d2 = d1 - a

    def phi(x: float) -> float:
        return (1 + math.erf(x / math.sqrt(2))) / 2

    return discount * (
        forward * phi(d1) - strike * phi(d2)
        if side == "call"
        else strike * phi(-d2) - forward * phi(-d1)
    )


def implied_total_vol(
    forward: float, strike: float, price: float, side: str, discount: float = 1.0
) -> float:
    intrinsic = discount * max(
        0, forward - strike if side == "call" else strike - forward
    )
    upper_price = discount * (forward if side == "call" else strike)
    if (
        not all(math.isfinite(v) for v in (forward, strike, price, discount))
        or not intrinsic < price < upper_price
    ):
        raise ValueError("price is outside Black no-arbitrage bounds")
    lo, hi = 1e-7, 5.0
    if black_price(forward, strike, hi, side, discount) < price:
        raise ValueError("total volatility exceeds solver range")
    for _ in range(55):
        a = (lo + hi) / 2
        if black_price(forward, strike, a, side, discount) < price:
            lo = a
        else:
            hi = a
    return (lo + hi) / 2


def settlement_time(root: str, expiry: str) -> datetime:
    bounds = regular_session_bounds(date.fromisoformat(expiry))
    if bounds is None:
        raise ValueError(f"expiry is not a regular session: {root} {expiry}")
    return bounds[0] if root == "SPX" else bounds[1]


def _mid(c: Contract, side: str) -> float:
    return (
        (c.call_bid + c.call_ask) / 2 if side == "call" else (c.put_bid + c.put_ask) / 2
    )


def build_surface(
    snapshot: dict, *, rate: float = 0.0, max_days: int = 90
) -> tuple[list[SurfaceRow], dict]:
    if not math.isfinite(rate) or not -0.1 <= rate <= 0.5:
        raise ValueError("rate must be a finite decimal in [-0.1, 0.5]")
    quote_at = datetime.fromisoformat(snapshot["quote_at"])
    quote_date = date.fromisoformat(snapshot["quote_date"])
    groups = defaultdict(list)
    for item in snapshot["contracts"]:
        c = Contract(**item)
        if (
            quote_date
            <= date.fromisoformat(c.expiry)
            <= quote_date + timedelta(days=max_days)
        ):
            groups[(c.root, c.expiry)].append(c)
    result, skipped, forwards = [], Counter(), []
    for (root, expiry), contracts in sorted(groups.items()):
        years = (
            settlement_time(root, expiry) - quote_at
        ).total_seconds() / YEAR_SECONDS
        if years <= 0:
            skipped["already_settled"] += len(contracts)
            continue
        discount = math.exp(-rate * years)
        valid = [
            c
            for c in contracts
            if c.call_ask >= c.call_bid > 0 and c.put_ask >= c.put_bid > 0
        ]
        near = sorted(valid, key=lambda c: abs(c.strike - snapshot["spot"]))[:11]
        if len(near) < 3:
            skipped["insufficient_parity_quotes"] += len(contracts)
            continue
        parity = [
            c.strike + (_mid(c, "call") - _mid(c, "put")) / discount for c in near
        ]
        forward = median(parity)
        dispersion = median(abs(f - forward) for f in parity)
        if not forward > 0 or dispersion > max(5, snapshot["spot"] * 0.005):
            skipped["inconsistent_parity"] += len(contracts)
            continue
        forwards.append(
            {
                "root": root,
                "expiry": expiry,
                "forward": forward,
                "parity_mad": dispersion,
            }
        )
        for c in contracts:
            side = "put" if c.strike < forward else "call"
            bid, ask = (
                (c.put_bid, c.put_ask) if side == "put" else (c.call_bid, c.call_ask)
            )
            if bid <= 0 or ask < bid:
                skipped["zero_bid_or_crossed"] += 1
                continue
            if ask - bid > max(1, (ask + bid) / 4):
                skipped["wide_otm_market"] += 1
                continue
            try:
                a = implied_total_vol(
                    forward, c.strike, (bid + ask) / 2, side, discount
                )
            except ValueError:
                skipped["price_bounds"] += 1
                continue
            d1 = math.log(forward / c.strike) / a + a / 2
            delta = float(ndtr(-d1) if side == "put" else ndtr(d1))
            result.append(SurfaceRow(c, forward, discount, years, a, delta, side))
    if not result:
        raise ValueError("no usable unexpired option surface")
    return result, {
        "excluded": dict(skipped),
        "usable_rows": len(result),
        "forwards": forwards,
    }


def delta_strike(rows: list[SurfaceRow], side: str, delta: float) -> float | None:
    points = sorted((r.contract.strike, r.delta) for r in rows if r.side == side)
    roots = []
    for (k0, d0), (k1, d1) in zip(points, points[1:]):
        if d0 == delta:
            roots.append(k0)
        elif (d0 - delta) * (d1 - delta) < 0:
            roots.append(k0 + (delta - d0) * (k1 - k0) / (d1 - d0))
    if points and points[-1][1] == delta:
        roots.append(points[-1][0])
    return roots[0] if len(roots) == 1 else None


def gamma_matrix(
    rows: list[SurfaceRow],
    spots: np.ndarray,
    reference_spot: float,
    vol_scale: float = 1.0,
) -> np.ndarray:
    strikes = np.array([r.contract.strike for r in rows])[None, :]
    a = np.array([r.a for r in rows])[None, :] * vol_scale
    carry = np.array([r.forward / reference_spot for r in rows])[None, :]
    discount = np.array([r.discount for r in rows])[None, :]
    s = spots[:, None]
    d1 = np.log(s * carry / strikes) / a + a / 2
    return discount * carry * np.exp(-d1 * d1 / 2) / (math.sqrt(2 * math.pi) * s * a)


def find_roots(grid: np.ndarray, values: np.ndarray) -> list[float]:
    if np.all(np.abs(values) < 1e-12):
        return []
    result = []
    # A gamma flip requires opposite signs, not a zero caused by tail underflow.
    nonzero = np.flatnonzero(values)
    for i, j in zip(nonzero[:-1], nonzero[1:]):
        y0, y1 = values[i], values[j]
        if (y0 < 0) != (y1 < 0):
            result.append(float(grid[i] - y0 * (grid[j] - grid[i]) / (y1 - y0)))
    return result


def _concentrations(
    rows: list[SurfaceRow], gamma: np.ndarray, spot: float
) -> list[dict]:
    nodes = defaultdict(lambda: [0.0, 0.0, 0, 0])
    for r, g in zip(rows, gamma):
        c = r.contract
        n = nodes[c.strike]
        n[0] += g * c.call_oi * spot * spot / 1e9
        n[1] += g * c.put_oi * spot * spot / 1e9
        n[2] += c.call_oi
        n[3] += c.put_oi
    return sorted(
        [
            {
                "strike": k,
                "call_gex_bn": v[0],
                "put_gex_bn": v[1],
                "call_oi": v[2],
                "put_oi": v[3],
                "gross_gex_bn": v[0] + v[1],
            }
            for k, v in nodes.items()
        ],
        key=lambda x: -x["gross_gex_bn"],
    )


def outcome_scenarios(
    forward: float, a: float, reference_spot: float, newer_spot: float | None = None
) -> dict:
    """Illustrative lognormal expiry distributions retaining closing total variance."""
    shifts = [-0.02, -0.01, -0.005, 0.0, 0.005, 0.01, 0.02]
    scenarios = []
    for shift in shifts:
        center = forward * (1 + shift)
        scenarios.append(
            {
                "label": f"{shift:+.1%} gap stress" if shift else "Closing forward",
                "forward": center,
                "shift_pct": shift * 100,
                "low_1sigma": center * math.exp(-a * a / 2 - a),
                "high_1sigma": center * math.exp(-a * a / 2 + a),
                "low_3sigma": center * math.exp(-a * a / 2 - 3 * a),
                "high_3sigma": center * math.exp(-a * a / 2 + 3 * a),
            }
        )
    if newer_spot is not None:
        center = forward * newer_spot / reference_spot
        scenarios.append(
            {
                "label": "Newer cash-price location scenario",
                "forward": center,
                "shift_pct": (newer_spot / reference_spot - 1) * 100,
                "low_1sigma": center * math.exp(-a * a / 2 - a),
                "high_1sigma": center * math.exp(-a * a / 2 + a),
                "low_3sigma": center * math.exp(-a * a / 2 - 3 * a),
                "high_3sigma": center * math.exp(-a * a / 2 + 3 * a),
            }
        )
    lo = min(s["low_3sigma"] for s in scenarios) * 0.998
    hi = max(s["high_3sigma"] for s in scenarios) * 1.002
    grid = np.linspace(lo, hi, 401)
    densities = []
    for s in scenarios:
        z = (np.log(grid / s["forward"]) + a * a / 2) / a
        densities.append(
            {
                "label": s["label"],
                "density": (
                    np.exp(-z * z / 2) / (grid * a * math.sqrt(2 * math.pi))
                ).tolist(),
            }
        )
    bands = [
        {
            "sigma": z,
            "low": forward * math.exp(-a * a / 2 - z * a),
            "high": forward * math.exp(-a * a / 2 + z * a),
        }
        for z in (1, 2, 3)
    ]
    return {
        "scenarios": scenarios,
        "bands": bands,
        "grid": grid.tolist(),
        "densities": densities,
        "note": "Illustrative ATM-lognormal distributions, not skew-calibrated physical forecasts. Gap stresses have no assigned probability and retain the entire closing-to-expiry variance; they are not an estimate of variance remaining after the gap.",
    }


def analyze(
    snapshot: dict, *, target_expiry: str | None = None, rate: float = 0.0
) -> dict:
    rows, quality = build_surface(snapshot, rate=rate)
    spot = snapshot["spot"]
    dates = sorted({r.contract.expiry for r in rows if r.contract.root == "SPXW"})
    target_expiry = target_expiry or dates[0]
    target = [
        r
        for r in rows
        if r.contract.root == "SPXW" and r.contract.expiry == target_expiry
    ]
    if not target:
        raise ValueError(f"no usable SPXW prices for {target_expiry}")
    forward = target[0].forward
    atm = min(target, key=lambda r: abs(r.contract.strike - forward))
    straddle = _mid(atm.contract, "call") + _mid(atm.contract, "put")
    deviation = forward * atm.a
    delta_bands = [
        {
            "delta": p,
            "put": delta_strike(target, "put", p),
            "call": delta_strike(target, "call", p),
        }
        for p in (0.01, 0.05, 0.1, 0.15, 0.25)
    ]
    newer = next(
        (
            q
            for q in snapshot["context"]["quotes"]
            if q["symbol"] == "^GSPC"
            and datetime.fromisoformat(q["bar_start"])
            > datetime.fromisoformat(snapshot["quote_at"])
            and datetime.fromisoformat(q["bar_start"])
            <= datetime.fromisoformat(snapshot["captured_at"])
            and datetime.fromisoformat(q["bar_start"])
            < settlement_time("SPXW", target_expiry)
        ),
        None,
    )
    distributions = outcome_scenarios(
        forward, atm.a, spot, newer["close"] if newer else None
    )
    lo = min(spot * 0.95, distributions["grid"][0])
    hi = max(spot * 1.05, distributions["grid"][-1])
    grid = np.linspace(lo, hi, 201)
    profiles, scope_nodes, buckets, finite_shocks, sensitivity = [], {}, [], [], []
    quote_date = date.fromisoformat(snapshot["quote_date"])
    scopes = [
        (
            "target",
            [
                r
                for r in rows
                if r.contract.root == "SPXW" and r.contract.expiry == target_expiry
            ],
        )
    ]
    scopes.extend(
        (
            f"{days}d",
            [
                r
                for r in rows
                if date.fromisoformat(r.contract.expiry)
                <= quote_date + timedelta(days=days)
            ],
        )
        for days in (7, 30, 90)
    )
    for scope, all_rows in scopes:
        selected = [
            r
            for r in all_rows
            if r.contract.call_oi is not None and r.contract.put_oi is not None
        ]
        if not selected:
            continue
        c_oi = np.array([r.contract.call_oi for r in selected])
        p_oi = np.array([r.contract.put_oi for r in selected])
        gammas = gamma_matrix(selected, grid, spot)
        gamma_now = gamma_matrix(selected, np.array([spot]), spot)[0]
        scale = grid * grid / 1e9  # 100 multiplier × 1% shock = 1
        nodes = _concentrations(selected, gamma_now, spot)
        scope_nodes[scope] = nodes[:15]
        for model, (cw, pw) in MODELS.items():
            positions = cw * c_oi + pw * p_oi
            values = gammas @ positions * scale
            profiles.append(
                {
                    "scope": scope,
                    "model": model,
                    "call_fraction": cw,
                    "put_fraction": pw,
                    "gex_bn_per_1pct": float(gamma_now @ positions * spot * spot / 1e9),
                    "roots": find_roots(grid, values),
                    "curve": values.tolist(),
                    "rows": len(selected),
                    "missing_oi_rows": len(all_rows) - len(selected),
                }
            )
        if scope == "30d":
            for vol_scale in (0.9, 1.0, 1.1):
                values = (
                    gamma_matrix(selected, grid, spot, vol_scale)
                    @ (c_oi - p_oi)
                    * scale
                )
                sensitivity.append(
                    {"total_vol_scale": vol_scale, "roots": find_roots(grid, values)}
                )
            for shock in (-0.01, -0.005, 0.005, 0.01):
                new_spot = spot * (1 + shock)
                hedge = 0.0
                for r in selected:
                    c = r.contract
                    carry = r.forward / spot
                    old_d1 = math.log(r.forward / c.strike) / r.a + r.a / 2
                    new_d1 = math.log(carry * new_spot / c.strike) / r.a + r.a / 2
                    delta_change = (
                        r.discount * carry * float(ndtr(new_d1) - ndtr(old_d1))
                    )
                    hedge -= (c.call_oi - c.put_oi) * 100 * delta_change * new_spot
                finite_shocks.append(
                    {"spot_move_pct": shock * 100, "hedge_notional_bn": hedge / 1e9}
                )
    grouped = defaultdict(list)
    for r in rows:
        if r.contract.call_oi is not None:
            grouped[(r.contract.root, r.contract.expiry)].append(r)
    for (root, expiry), group in sorted(grouped.items()):
        g = gamma_matrix(group, np.array([spot]), spot)[0]
        co = sum(r.contract.call_oi for r in group)
        po = sum(r.contract.put_oi for r in group)
        cg = sum(v * r.contract.call_oi for r, v in zip(group, g)) * spot * spot / 1e9
        pg = sum(v * r.contract.put_oi for r, v in zip(group, g)) * spot * spot / 1e9
        buckets.append(
            {
                "root": root,
                "expiry": expiry,
                "rows": len(group),
                "call_oi": co,
                "put_oi": po,
                "put_call_oi_ratio": po / co if co else None,
                "call_gex_bn": cg,
                "put_gex_bn": pg,
                "conventional_net_bn": cg - pg,
            }
        )
    call_curve = sorted(
        (
            r.contract.strike,
            black_price(r.forward, r.contract.strike, r.a, "call", r.discount),
        )
        for r in target
    )
    digital = []
    for (k0, c0), (k1, c1) in zip(call_curve, call_curve[1:]):
        if abs((k0 + k1) / 2 - forward) <= 2 * deviation:
            tail = (c0 - c1) / (k1 - k0) / atm.discount
            digital.append({"strike": (k0 + k1) / 2, "risk_neutral_above": tail})
    digital_valid = all(0 <= d["risk_neutral_above"] <= 1 for d in digital) and all(
        a["risk_neutral_above"] >= b["risk_neutral_above"] - 1e-6
        for a, b in zip(digital, digital[1:])
    )
    levels = {spot, round(spot / 50) * 50, round(spot / 50) * 50 + 50}
    levels.update(
        b[side]
        for b in delta_bands[2:]
        for side in ("put", "call")
        if b[side] is not None
    )
    if newer:
        levels.add(newer["close"])
    level_regimes = [
        {
            "spot": level,
            "scopes": {
                p["scope"]: float(np.interp(level, grid, p["curve"]))
                for p in profiles
                if p["model"] == "calls_long_puts_short"
            },
        }
        for level in sorted(levels)
    ]
    return {
        "analysis_version": 1,
        "quote_date": snapshot["quote_date"],
        "quote_at": snapshot["quote_at"],
        "spot": spot,
        "rate": rate,
        "target_expiry": target_expiry,
        "settlement_at": settlement_time("SPXW", target_expiry).isoformat(),
        "forward": forward,
        "atm_strike": atm.contract.strike,
        "atm_iv": atm.a / math.sqrt(atm.years),
        "atm_total_vol": atm.a,
        "hours_from_quote": atm.years * YEAR_SECONDS / 3600,
        "straddle_points": straddle,
        "sigma_points": deviation,
        "delta_bands": delta_bands,
        "distributions": distributions,
        "newer_cash_reference": newer,
        "level_regimes": level_regimes,
        "skew_10d_iv": {side: _wing_iv(target, side, 0.1) for side in ("put", "call")},
        "quality": quality,
        "profiles": profiles,
        "grid": grid.tolist(),
        "concentrations": scope_nodes,
        "expiry_buckets": buckets,
        "vol_sensitivity_30d": sensitivity,
        "finite_shocks_30d": finite_shocks,
        "digital_tails_valid": digital_valid,
        "digital_tails": digital if digital_valid else [],
        "digital_note": "Call-spread risk-neutral interval averages, not physical forecasts."
        if digital_valid
        else "Suppressed: raw call slopes violate probability bounds or convexity; no smoothing fiction.",
    }


def _wing_iv(rows: list[SurfaceRow], side: str, delta: float) -> float | None:
    strike = delta_strike(rows, side, delta)
    if strike is None:
        return None
    points = sorted(
        (r.contract.strike, r.a / math.sqrt(r.years)) for r in rows if r.side == side
    )
    return float(np.interp(strike, [p[0] for p in points], [p[1] for p in points]))
