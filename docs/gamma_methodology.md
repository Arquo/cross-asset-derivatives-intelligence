# Estimated Gamma Exposure Methodology

Black-Scholes gamma is calculated per contract with a 4% risk-free-rate approximation and zero dividend yield. Estimated exposure is:

`gamma x open interest x contract multiplier x spot^2`

Public option chains do not reveal who owns each contract or dealer inventory. Therefore the dashboard exposes three sign scenarios:

- Calls positive, puts negative
- All contracts positive
- Calls negative, puts positive

The result is always labelled Estimated Gamma Exposure. Sensitivity across assumptions is shown. A gamma-flip estimate is reported only when total estimated exposure changes sign across the tested spot scenarios; otherwise it remains unavailable. None of these estimates confirms dealer positioning.
