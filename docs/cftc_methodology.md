# CFTC Positioning Methodology

## Source and Mapping

Data come from official CFTC Public Reporting machine-readable datasets. Mappings use explicit `cftc_contract_market_code` values in `configs/cftc_contracts.yaml`. The provider does not silently fuzzy-match names and rejects a response containing more than one contract identity.

Current mappings cover S&P 500, Nasdaq-100, Russell 2000, 2-year/5-year/10-year Treasury notes, U.S. Treasury bond, USD Index, Gold, and WTI Physical futures.

## Timing

`report_date` is the Tuesday position date. `publication_date` is the later public-release date proxy. `ingested_ts` records local retrieval. The data are weekly and delayed.

## Calculations

For each contract and participant category, net position is gross long minus gross short. The module calculates one-week and four-week changes, net/open-interest, 52-week and three-year percentiles, rolling z-score, open-interest change, sign reversal, crowding, price-positioning divergence, long-liquidation risk, and short-squeeze risk.

Crowding and risk flags describe exposure conditions. They are not predictions of liquidation, squeeze, or future returns.
