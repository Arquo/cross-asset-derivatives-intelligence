import streamlit as st


st.set_page_config(
    page_title="Cross-Asset Derivatives Intelligence Platform",
    page_icon="📈",
    layout="wide",
)

st.markdown(
    """
    <style>
    .hero {
        padding: 2rem 0 1rem 0;
    }
    .hero h1 {
        font-size: 3rem;
        margin-bottom: 0.5rem;
    }
    .hero p {
        font-size: 1.1rem;
        color: #4b5563;
        max-width: 900px;
    }
    .module-card {
        border: 1px solid #e5e7eb;
        border-radius: 16px;
        padding: 1.1rem;
        background: white;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.05);
        min-height: 120px;
    }
    .module-card h3 {
        margin: 0 0 0.35rem 0;
        font-size: 1.1rem;
    }
    .module-card p {
        margin: 0;
        color: #6b7280;
        font-size: 0.95rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <h1>Cross-Asset Derivatives Intelligence Platform</h1>
        <p>
            A lightweight dashboard for exploring macro, positioning, options, market structure,
            liquidity, and cross-asset context in one place.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

modules = [
    ("Macro", "Track the broad economic backdrop and rate-sensitive signals."),
    ("Positioning", "Review where positioning may be stretched or balanced."),
    ("Options", "Monitor volatility and options-driven market cues."),
    ("Market Structure", "Observe structure, trend, and regime context."),
    ("Liquidity", "Watch liquidity conditions and market depth themes."),
    ("Cross-Asset", "Connect relationships across rates, FX, equities, and credit."),
]

for left, right in zip(modules[::2], modules[1::2]):
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(
            f"""
            <div class="module-card">
                <h3>{left[0]}</h3>
                <p>{left[1]}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            f"""
            <div class="module-card">
                <h3>{right[0]}</h3>
                <p>{right[1]}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.write("")
if st.button("Analyze Today’s Market"):
    st.info("Market analysis modules are not connected yet.")

