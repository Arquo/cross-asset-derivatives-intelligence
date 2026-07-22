"""Shared layout helpers."""

from __future__ import annotations

from collections.abc import Iterable

import streamlit as st


def render_page_header(title: str, subtitle: str, badges: Iterable[str] | None = None) -> None:
    st.markdown(f"<div class='dashboard-hero'><h1>{title}</h1><div class='dashboard-subtitle'>{subtitle}</div></div>", unsafe_allow_html=True)
    if badges:
        badge_markup = "".join([f"<span class='status-badge status-current'>{badge}</span>" for badge in badges])
        st.markdown(badge_markup, unsafe_allow_html=True)


def render_section_heading(title: str, subtitle: str | None = None) -> None:
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)


def render_empty_state(title: str, message: str, command: str | None = None) -> None:
    st.markdown(f"<div class='empty-panel'><strong>{title}</strong><div style='margin-top:0.4rem;color:#94a3b8'>{message}</div></div>", unsafe_allow_html=True)
    if command:
        st.code(command)


def render_warning_panel(message: str) -> None:
    st.markdown(f"<div class='warning-panel'>{message}</div>", unsafe_allow_html=True)
