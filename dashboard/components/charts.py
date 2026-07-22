"""Chart helpers."""

from __future__ import annotations

import streamlit as st


def render_chart(fig, *, title: str, subtitle: str | None = None) -> None:
    st.markdown(f"**{title}**")
    if subtitle:
        st.caption(subtitle)
    st.plotly_chart(fig, use_container_width=True)
