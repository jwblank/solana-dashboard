from __future__ import annotations

import numpy as np
import pandas as pd


def demo_history(days: int = 820, seed: int = 20260704) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range(
        end=pd.Timestamp.utcnow().normalize() - pd.Timedelta(days=1), periods=days
    )
    regime = np.sin(np.linspace(0, 12, days))
    sol_ret = 0.001 + 0.012 * regime / 10 + rng.normal(0, 0.045, days)
    btc_ret = 0.0006 + rng.normal(0, 0.028, days)
    sol = 28 * np.exp(np.cumsum(sol_ret))
    btc = 18000 * np.exp(np.cumsum(btc_ret))
    data = pd.DataFrame(
        {
            "date": dates.date.astype(str),
            "sol_close": sol,
            "btc_close": btc,
            "sol_volume": 8_000_000 * (1 + rng.lognormal(0, 0.45, days)),
            "dex_volume": 320_000_000 * (1 + regime / 5 + rng.lognormal(0, 0.35, days)),
            "fees": 1_200_000 * (1 + regime / 6 + rng.lognormal(0, 0.30, days)),
            "tvl": 1_800_000_000 * np.exp(np.cumsum(0.0004 + rng.normal(0, 0.01, days))),
            "stablecoins": 2_400_000_000 * np.exp(np.cumsum(0.0003 + rng.normal(0, 0.006, days))),
        }
    )
    return data
