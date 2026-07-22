# SPY and QQQ Options Methodology

## Snapshots

The replaceable yfinance provider retrieves current SPY and QQQ chains. Each retrieval has a unique snapshot ID and immutable Parquet location. Stored fields include underlying price, quote/retrieval timestamp, expiration, strike, type, bid, ask, last price, implied volatility, volume, open interest, and in-the-money status.

The free provider is research-grade. Quotes may be delayed, stale, crossed, missing, or inconsistent. Historical analysis starts when local snapshots are collected.

## Calculations

- Put/call volume and open-interest ratios use aggregate valid values.
- ATM contracts minimize absolute strike-to-spot distance.
- Realized volatility is the 20-day annualized standard deviation of underlying returns.
- Expected move uses valid ATM call plus put midpoints and falls back to `spot x ATM IV x sqrt(time)`.
- Approximate 25-delta contracts minimize absolute difference from Black-Scholes delta targets of +0.25 and -0.25.
- Risk reversal is call 25-delta IV minus put 25-delta IV; downside skew is its negative.
- Open-interest concentration is the share in the five largest strikes.

Every deterministic condition stores supporting metrics, contradicting metrics, timestamp, assumptions, confidence, and limitations. Open interest alone is never used as a directional prediction.
