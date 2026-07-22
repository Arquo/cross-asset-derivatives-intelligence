"""Centralized styling helpers for the dashboard."""

from __future__ import annotations

import streamlit as st


def inject_dashboard_styles() -> None:
    st.markdown(
        """
        <style>
        .dashboard-hero {
            padding: 0.5rem 0 1rem 0;
        }
        .dashboard-hero h1 {
            margin-bottom: 0.2rem;
        }
        .dashboard-subtitle {
            color: #94a3b8;
            font-size: 1rem;
        }
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            padding: 0.25rem 0.7rem;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 700;
            border: 1px solid transparent;
            margin-right: 0.35rem;
        }
        .status-current { background: rgba(34, 197, 94, 0.14); border-color: rgba(34, 197, 94, 0.35); color: #bbf7d0; }
        .status-delayed { background: rgba(59, 130, 246, 0.14); border-color: rgba(59, 130, 246, 0.35); color: #bfdbfe; }
        .status-stale { background: rgba(245, 158, 11, 0.16); border-color: rgba(245, 158, 11, 0.4); color: #fde68a; }
        .status-missing { background: rgba(100, 116, 139, 0.18); border-color: rgba(100, 116, 139, 0.45); color: #cbd5e1; }
        .status-failed { background: rgba(239, 68, 68, 0.16); border-color: rgba(239, 68, 68, 0.4); color: #fecaca; }
        .panel {
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 16px;
            padding: 1rem 1.1rem;
            background: rgba(15, 23, 42, 0.62);
        }
        .empty-panel {
            border: 1px dashed rgba(148, 163, 184, 0.28);
            border-radius: 16px;
            padding: 1.15rem;
            background: rgba(15, 23, 42, 0.4);
        }
        .warning-panel {
            border: 1px solid rgba(245, 158, 11, 0.38);
            background: rgba(245, 158, 11, 0.14);
            border-radius: 14px;
            padding: 0.9rem 1rem;
            color: #fde68a;
        }
        .coming-soon-card {
            border: 1px solid rgba(148, 163, 184, 0.18);
            border-radius: 16px;
            padding: 1rem;
            background: rgba(17, 24, 39, 0.8);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
