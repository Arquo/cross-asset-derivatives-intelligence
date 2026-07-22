# Cross-Asset Screener Methodology

## Inputs

The screener uses validated daily OHLCV observations for the configured 13-asset universe. Prices use adjusted close when available and close as a documented fallback.

## Metrics

- Returns: price percentage change over 1, 5, 20, and 60 observations.
- Moving-average distance: `price / rolling mean - 1` over 20 and 60 observations.
- Realized volatility: 20-day standard deviation of daily returns multiplied by the square root of 252.
- Relative volume: current volume divided by its 20-day average.
- Dollar volume: close multiplied by volume.
- Amihud illiquidity: 20-day mean of absolute return divided by dollar volume.

## Market Pressure Score

Component weights are 30% trend/momentum, 20% volume confirmation, 20% volatility, 15% liquidity, and 15% positioning. Each component is normalized to [-100, 100]. Available weights are divided by their sum when inputs are missing. The final weighted score is bounded to [-100, 100].

Labels are:

- 60 to 100: Strong bullish pressure
- 20 to below 60: Moderate bullish pressure
- Above -20 to below 20: Neutral
- Above -60 to -20: Moderate bearish pressure
- -100 to -60: Strong bearish pressure

Coverage below 40% produces Insufficient data. All base weights, effective weights, normalized scores, contributions, and missing components are stored. The score is descriptive and is not a trade recommendation.
