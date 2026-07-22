"""Reusable card and badge helpers."""

from __future__ import annotations

from collections.abc import Iterable

import streamlit as st


STATUS_CLASS = {
    "Current": "status-current",
    "Delayed as expected": "status-delayed",
    "Stale": "status-stale",
    "Missing": "status-missing",
    "Failed": "status-failed",
}


def render_status_badge(label: str) -> None:
    css_class = STATUS_CLASS.get(label, "status-missing")
    st.markdown(f"<span class='status-badge {css_class}'>{label}</span>", unsafe_allow_html=True)


def render_metric_cards(metrics: Iterable[dict[str, str]]) -> None:
    metrics = list(metrics)
    if not metrics:
        return
    columns = st.columns(len(metrics))
    for column, metric in zip(columns, metrics, strict=False):
        with column:
            st.metric(metric["label"], metric["value"], metric.get("delta"))


def render_coming_soon_cards(cards: Iterable[dict[str, str]]) -> None:
    rows = list(cards)
    if not rows:
        return
    for start in range(0, len(rows), 3):
        columns = st.columns(3)
        for column, card in zip(columns, rows[start : start + 3], strict=False):
            with column:
                st.markdown(
                    f"""
                    <div class="coming-soon-card">
                        <strong>{card['title']}</strong>
                        <div style="margin-top:0.35rem;color:#94a3b8">{card['description']}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
