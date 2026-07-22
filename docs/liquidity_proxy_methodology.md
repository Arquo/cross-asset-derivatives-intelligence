# Liquidity Proxy Methodology

The module uses delayed daily bars. It does not measure full order-book depth, effective spreads, realized spreads, hidden liquidity, or venue fragmentation.

## Asset Metrics

Each asset receives dollar volume, 20-day average dollar volume, relative volume, 20-day realized volatility, intraday range/close, 14-day average true range, 20-day Amihud illiquidity, Amihud percentile, volume-shock z-score, price-impact proxy, and drawdown.

## Stress Score

The 0-100 score uses:

- Amihud illiquidity percentile: 25%
- Realized-volatility percentile: 20%
- Intraday-range percentile: 15%
- Inverse relative dollar volume: 15%
- HYG stress: 15%
- VIX stress: 10%

Unavailable components are omitted and available weights are normalized. Coverage below 50% is insufficient. Regimes are Abundant (0-20), Normal (above 20-45), Tightening (above 45-70), and Stressed (above 70-100).
