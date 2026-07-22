"""Regime card helpers."""

from __future__ import annotations

from collections.abc import Iterable

import streamlit as st


def render_regime_cards(cards: Iterable[dict[str, str]]) -> None:
    rows = list(cards)
    if not rows:
        return
    columns = st.columns(min(3, len(rows)))
    for index, card in enumerate(rows):
        with columns[index % len(columns)]:
            st.markdown(
                f"""
                <div class="panel">
                    <div style="font-size:0.85rem;color:#94a3b8">{card.get('label', '')}</div>
                    <div style="font-size:1.3rem;font-weight:700;margin-top:0.2rem">{card.get('value', '')}</div>
                    <div style="color:#cbd5e1;margin-top:0.2rem">{card.get('supporting', '')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

