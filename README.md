# Cross-Asset Derivatives Intelligence Platform

This project is a Streamlit dashboard for cross-asset derivatives research.

## Current milestone

The first real module is **Macro Regime**, powered by official FRED data.

## Setup

1. Create a local `.env` file from the example file:

```bash
copy .env.example .env
```

2. Add your FRED API key to `.env`:

```bash
FRED_API_KEY=your_real_key_here
```

3. Install dependencies:

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Run tests

```bash
.venv\Scripts\python -m pytest
```

## Launch the app

```bash
.venv\Scripts\streamlit run app.py
```

## Notes

- The app reads `FRED_API_KEY` from `.env`.
- Market data is cached in Streamlit for six hours.
- Tests use synthetic data only and do not call the live FRED API.

