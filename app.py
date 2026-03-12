import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from analysis import calculate_climate_factors

st.set_page_config(page_title="Climate Factor Analyzer", page_icon="🌍", layout="wide")

# ── Styling ──────────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetricValue"] { font-size: 1.1rem; }
.risk-badge { padding:4px 12px; border-radius:12px; font-weight:600; font-size:0.85rem; }
.badge-red   { background:#fee2e2; color:#991b1b; }
.badge-orange{ background:#ffedd5; color:#9a3412; }
.badge-yellow{ background:#fef9c3; color:#854d0e; }
.badge-green { background:#dcfce7; color:#166534; }
.badge-blue  { background:#dbeafe; color:#1e40af; }
.source-note { font-size:0.75rem; color:#6b7280; font-style:italic; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def risk_color(label):
    return {
        'Very High': '#ef4444', 'High': '#f97316',
        'Medium': '#eab308', 'Low': '#22c55e', 'Very Low': '#3b82f6'
    }.get(label, '#9ca3af')

def paris_badge(status):
    if '1.5C Aligned' in status:       return 'badge-blue',  '✅ 1.5°C Aligned'
    if '2C Aligned' in status:         return 'badge-green', '🟡 2°C Aligned'
    if 'Consistent' in status:         return 'badge-yellow','🟡 1.5°C Consistent'
    if 'Off Track' in status:          return 'badge-orange','🔴 Committed, Off Track'
    if 'Misaligned' in status:         return 'badge-red',   '🔴 Paris Misaligned'
    return 'badge-yellow', status

def _fmt_nz_display(f):
    """Return a clean display string for Net-Zero status from the net_zero_status field."""
    nz = f.get('net_zero_status', 'Unknown')
    if nz == 'None declared':
        return 'No target declared'
    if nz == 'Unknown':
        return 'Not disclosed'
    return str(nz)

def cls_icon(classification):
    icons = {
        'Clean Pure-Play': '🌱',
        'Credible Transition Leader': '📈',
        'Early-Stage Transition': '🔄',
        'Climate Laggard': '⚠️',
        'Managed Transition': '🧭',
        'Standard — Monitor': 'ℹ️',
    }
    return icons.get(classification, 'ℹ️')

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🌍 Climate Factor Analyzer")
st.caption("IFRS S2 (ISSB)-aligned climate risk assessment · IEA carbon price scenarios · SBTi Paris alignment")
st.markdown("---")

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2 = st.tabs(["🔍 Single Stock", "⚖️ Compare Two Stocks"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: SINGLE STOCK
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    ticker_input = st.text_input("Enter stock ticker (e.g., TSLA, XOM, F):", "TSLA", key="single")

    if ticker_input:
        try:
            with st.spinner("Analyzing climate risk..."):
                f = calculate_climate_factors(ticker_input.upper())

            # ── Company header ────────────────────────────────────────────────
            col_h1, col_h2 = st.columns([3, 1])
            with col_h1:
                icon = cls_icon(f['classification'])
                st.markdown(f"## {icon} {f['company']} ({f['ticker']})")
                st.markdown(f"**{f['sector']}** · {f['industry']}")
                st.markdown(f"*{f['classification_note']}*")
            with col_h2:
                badge_cls, badge_lbl = paris_badge(f['paris_alignment']['status'])
                st.markdown(f"<br><span class='risk-badge {badge_cls}'>{badge_lbl}</span>",
                            unsafe_allow_html=True)
                st.markdown(f"<br><b>Risk Score: {f['transition_risk_score']}/100</b> "
                            f"<span style='color:{risk_color(f['transition_risk_label'])}'>■</span> "
                            f"{f['transition_risk_label']}", unsafe_allow_html=True)

            st.markdown("---")

            # ── Row 1: Key metrics ────────────────────────────────────────────
            st.subheader("📊 Key Climate Metrics")
            m1, m2, m3, m4, m5 = st.columns(5)
            m1.metric("Scope 1+2 Intensity",
                      f"{f['intensity_s12']:.1f} tCO2/$M",
                      help="Scope 1+2 carbon intensity per $M revenue. Lower = less carbon per dollar earned.")
            m2.metric("Green Revenue", f"{f['green_revenue_pct']}%",
                      help="% of revenue from clean/low-carbon products or services.")
            m3.metric("Fossil Exposure", f['fossil_exposure'])
            m4.metric("Transition Risk", f['transition_risk_label'],
                      help="Composite 0-100 score based on intensity, green revenue, Paris alignment, and SBTi commitment.")
            _nz_status = f.get('net_zero_status', 'Unknown')
            if _nz_status == 'None declared':
                m5.metric("Net-Zero Target", "No target declared",
                          help="Company has explicitly stated no net-zero target.")
                m5.markdown("<p style='color:#ef4444;font-size:0.75rem;margin-top:-10px;'>⚠️ No commitment</p>",
                            unsafe_allow_html=True)
            elif _nz_status == 'Unknown':
                m5.metric("Net-Zero Target", "Not disclosed",
                          help="No net-zero target information available for this company.")
            else:
                m5.metric("Net-Zero Target", _nz_status,
                          help="Company-stated net-zero target year.")

            st.markdown("---")

            # ── Row 2: Emissions data + Peer z-score ──────────────────────────
            col_em, col_peer = st.columns([1, 1])

            with col_em:
                st.subheader("🏭 Emissions Data")
                data_tag = "✅ Real reported data" if f['using_real_data'] else "⚠️ Industry proxy"
                st.caption(data_tag)

                if f['scope1_tonnes']:
                    em_data = {
                        'Metric': ['Scope 1', 'Scope 2 (market-based)', 'Scope 1+2 Total', 'Scope 1+2 Intensity'],
                        'Value': [
                            f"{f['scope1_tonnes']:,.0f} tCO2e",
                            f"{f['scope2_tonnes']:,.0f} tCO2e",
                            f"{f['scope1_tonnes'] + f['scope2_tonnes']:,.0f} tCO2e",
                            f"{f['intensity_s12']:.2f} tCO2/$M revenue",
                        ]
                    }
                    if f.get('scope2_location_based'):
                        em_data['Metric'].insert(2, 'Scope 2 (location-based)')
                        em_data['Value'].insert(2, f"{f['scope2_location_based']:,.0f} tCO2e ⚠️")
                    st.table(pd.DataFrame(em_data))
                else:
                    st.info(f"Scope 1+2 Intensity (proxy): **{f['intensity_s12']:.1f} tCO2/$M**")

                st.markdown(f"<p class='source-note'>Source: {f['emissions_source']} ({f['emissions_year']})</p>",
                            unsafe_allow_html=True)
                if f['emissions_notes']:
                    st.markdown(f"<p class='source-note'>📝 {f['emissions_notes']}</p>",
                                unsafe_allow_html=True)

            with col_peer:
                st.subheader("📐 Peer Benchmarking")
                if f['z_score'] is not None:
                    st.caption(f"Scope 1+2 intensity vs {f['sector_group']} peer group")
                    z = f['z_score']
                    z_color = risk_color(f['z_risk_label'])
                    st.markdown(f"**Z-Score: {z:+.2f}** — "
                                f"<span style='color:{z_color}'><b>{f['z_risk_label']}</b></span> "
                                f"relative to peers", unsafe_allow_html=True)

                    # Peer bar chart
                    peers = dict(sorted(f['peer_data'].items(), key=lambda x: x[1]))
                    fig, ax = plt.subplots(figsize=(5, 3))
                    colors = ['#3b82f6' if p == f['ticker'] else '#d1d5db' for p in peers]
                    ax.barh(list(peers.keys()), list(peers.values()), color=colors)
                    ax.set_xlabel("tCO2e / $M revenue (Scope 1+2)", fontsize=9)
                    ax.set_title(f"{f['sector_group']} Peer Comparison", fontsize=10, fontweight='bold')
                    ax.tick_params(labelsize=8)
                    ax.grid(axis='x', alpha=0.3)
                    fig.tight_layout()
                    st.pyplot(fig)
                    plt.close()
                    st.caption("Blue bar = selected company · Sorted ascending (lower = cleaner)")
                elif f.get('peer_data'):
                    # No emissions data for this ticker but peer group data exists —
                    # show sector benchmark comparison with company estimate as reference.
                    st.caption("Sector benchmark comparison (no peer emissions data available)")
                    peers = dict(sorted(f['peer_data'].items(), key=lambda x: x[1]))
                    fig, ax = plt.subplots(figsize=(5, 3))
                    ax.barh(list(peers.keys()), list(peers.values()), color='#d1d5db')
                    ax.axvline(x=f['intensity_s12'], color='#3b82f6', linestyle='--',
                               linewidth=2, label=f"{f['ticker']} est. ({f['intensity_s12']:.0f})")
                    ax.set_xlabel("tCO2e / $M revenue (Scope 1+2)", fontsize=9)
                    ax.set_title(f"{f['sector_group']} Sector Benchmarks", fontsize=10, fontweight='bold')
                    ax.tick_params(labelsize=8)
                    ax.legend(fontsize=8)
                    ax.grid(axis='x', alpha=0.3)
                    fig.tight_layout()
                    st.pyplot(fig)
                    plt.close()
                    st.caption("Blue dashed line = company industry estimate · Grey bars = reported peer emissions")
                else:
                    iea = f.get('iea_benchmark')
                    if iea:
                        st.caption("IEA 2030 sector benchmark (no peer group available)")
                        fig, ax = plt.subplots(figsize=(5, 3))
                        ax.axvline(x=iea, color='#22c55e', linestyle='--', linewidth=2,
                                   label=f'IEA 2030 target ({iea} tCO2/\$M)')
                        ax.axvline(x=f['intensity_s12'], color='#3b82f6', linestyle='--', linewidth=2,
                                   label=f"{f['ticker']} est. ({f['intensity_s12']:.0f} tCO2/\$M)")
                        ax.set_xlim(0, max(iea, f['intensity_s12']) * 1.5)
                        ax.set_xlabel("tCO2e / \$M revenue (Scope 1+2)", fontsize=9)
                        ax.set_title(f"{f['sector']} — IEA 2030 Benchmark", fontsize=10, fontweight='bold')
                        ax.set_yticks([])
                        ax.legend(fontsize=8)
                        ax.grid(axis='x', alpha=0.3)
                        fig.tight_layout()
                        st.pyplot(fig)
                        plt.close()
                        st.caption("Blue = company estimate · Green = IEA 2030 sector target")
                    else:
                        st.info("Peer benchmarking not available for this sector.")

            st.markdown("---")

            # ── Row 3: Paris alignment ─────────────────────────────────────────
            st.subheader("🌡️ Paris Alignment (SBTi Sectoral Decarbonization Approach)")
            pa = f['paris_alignment']
            pa_col1, pa_col2 = st.columns([2, 1])
            with pa_col1:
                badge_cls, badge_lbl = paris_badge(pa['status'])
                st.markdown(f"<span class='risk-badge {badge_cls}'>{badge_lbl}</span><br><br>",
                            unsafe_allow_html=True)
                st.markdown(pa['note'].replace('$', r'\$'))
                if pa['required_reduction_pct'] > 0:
                    st.warning(f"**{pa['required_reduction_pct']}% reduction required** to meet 2°C budget")
            with pa_col2:
                st.metric("SBTi 1.5°C Budget", f"{pa['budget_1_5c']} tCO2/$M")
                st.metric("SBTi 2°C Budget", f"{pa['budget_2c']} tCO2/$M")
                st.metric("Current Intensity", f"{f['intensity_s12']:.1f} tCO2/$M")

            st.markdown("---")

            # ── Row 4: Climate VaR ────────────────────────────────────────────
            st.subheader("💰 Climate Value at Risk")
            st.caption("Estimated % of EBIT at risk from carbon pricing · Scope 3 multiplier: "
                       f"{f['scope3_multiplier']}x · Methodology: MSCI Climate VaR (transition component)")

            var_rows = []
            for v in f['climate_var'].values():
                var_rows.append({
                    'Scenario': v['label'],
                    'Carbon Price': f"${v['carbon_price']}/t",
                    'Scope 1+2 VaR': f"{v['scope12_var_pct']:.1f}%",
                    'Full-Scope VaR': f"{v['full_scope_var_pct']:.1f}%",
                    'Annual Emissions': f"{v['annual_emissions_mt']:.1f} Mt",
                })
            var_df = pd.DataFrame(var_rows)
            st.dataframe(var_df, use_container_width=True, hide_index=True)

            # VaR chart
            scenarios = [v['label'].split('(')[0].strip() for v in f['climate_var'].values()]
            s12_vars  = [v['scope12_var_pct'] for v in f['climate_var'].values()]
            full_vars = [v['full_scope_var_pct'] for v in f['climate_var'].values()]

            fig2, ax2 = plt.subplots(figsize=(9, 4))
            x = range(len(scenarios))
            width = 0.35
            ax2.bar([i - width/2 for i in x], s12_vars,  width, label='Scope 1+2 VaR',  color='#3b82f6', alpha=0.85)
            ax2.bar([i + width/2 for i in x], full_vars, width, label='Full-Scope VaR', color='#f97316', alpha=0.85)
            ax2.axhline(y=100, color='red', linestyle='--', alpha=0.4, label='100% EBIT (insolvency threshold)')
            ax2.set_xticks(list(x))
            ax2.set_xticklabels(scenarios, rotation=15, ha='right', fontsize=8)
            ax2.set_ylabel('% of EBIT at risk', fontsize=9)
            ax2.set_title(f'{f["ticker"]} — Climate VaR by Carbon Price Scenario', fontsize=11, fontweight='bold')
            ax2.legend(fontsize=8)
            ax2.grid(axis='y', alpha=0.3)
            fig2.tight_layout()
            st.pyplot(fig2)
            plt.close()

            # Stranded asset signal
            stranded = f['stranded_asset_signal']
            if 'HIGH' in stranded:
                st.error(f"🏚️ Stranded Asset Signal: {stranded}")
            elif 'MEDIUM' in stranded:
                st.warning(f"🏚️ Stranded Asset Signal: {stranded}")
            else:
                st.success(f"🏚️ Stranded Asset Signal: {stranded}")

        except Exception as e:
            st.error(f"❌ Error analyzing {ticker_input}: {str(e)}")
            st.write("Please check the ticker symbol and try again.")

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("📚 About")
        st.write("""
        **Frameworks:**
        - IFRS S2 (ISSB) — effective January 2024
        - IEA Net Zero 2050 carbon price pathways
        - SBTi Sectoral Decarbonization Approach
        - CDP Scope 3 multipliers

        **Metrics:**
        - **Scope 1+2 Intensity**: Scope 1+2 CO2e / $M revenue
        - **Climate VaR**: % EBIT at risk from carbon pricing
        - **Z-Score**: Intensity vs sector peers (same scope basis)
        - **Paris Alignment**: vs SBTi 2030 sector budgets
        - **Stranded Asset Signal**: Under 1.5°C scenario
        """)
        st.header("🧪 Try These")
        st.write("""
        **Clean Leaders:** TSLA · MSFT · AAPL  
        **Transition Stories:** NEE · BP · SHEL  
        **High Risk:** XOM · CVX · AEP · DUK  
        **Interesting comparisons:** TM vs TSLA · XOM vs BP
        """)
        st.markdown("---")
        st.caption("Data: Company 2023 sustainability reports · yfinance  \n"
                   "Built with Python, yfinance, Streamlit  \n"
                   "UC Berkeley Environmental Economics + Data Science")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: COMPARE TWO STOCKS
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    c1, c2 = st.columns(2)
    with c1:
        ticker_a = st.text_input("First stock:", "TSLA", key="cmp_a")
    with c2:
        ticker_b = st.text_input("Second stock:", "XOM",  key="cmp_b")

    if st.button("🔍 Compare Climate Risk"):
        try:
            with st.spinner("Analyzing..."):
                fa = calculate_climate_factors(ticker_a.upper())
                fb = calculate_climate_factors(ticker_b.upper())

            # ── Side-by-side classification ───────────────────────────────────
            ca, cb = st.columns(2)
            with ca:
                st.markdown(f"### {cls_icon(fa['classification'])} {fa['ticker']} — {fa['company']}")
                st.write(f"**{fa['classification']}**")
                st.caption(fa['classification_note'])
                badge_cls, badge_lbl = paris_badge(fa['paris_alignment']['status'])
                st.markdown(f"<span class='risk-badge {badge_cls}'>{badge_lbl}</span>",
                            unsafe_allow_html=True)
            with cb:
                st.markdown(f"### {cls_icon(fb['classification'])} {fb['ticker']} — {fb['company']}")
                st.write(f"**{fb['classification']}**")
                st.caption(fb['classification_note'])
                badge_cls, badge_lbl = paris_badge(fb['paris_alignment']['status'])
                st.markdown(f"<span class='risk-badge {badge_cls}'>{badge_lbl}</span>",
                            unsafe_allow_html=True)

            st.markdown("---")

            # ── Comparison table ──────────────────────────────────────────────
            st.subheader("📊 Side-by-Side Comparison")
            nz_a = _fmt_nz_display(fa)
            nz_b = _fmt_nz_display(fb)
            comp = {
                'Metric': [
                    'Sector', 'Scope 1+2 Intensity (tCO2/$M)',
                    'Green Revenue %', 'Fossil Exposure',
                    'Transition Risk', 'Risk Score (/100)',
                    'Paris Alignment', 'SBTi Target', 'Net-Zero Year',
                    'VaR @ $130/t (Scope 1+2)', 'VaR @ $130/t (Full-scope)',
                    'Stranded Asset Signal',
                    'Data Source'
                ],
                fa['ticker']: [
                    fa['sector'],
                    f"{fa['intensity_s12']:.1f}",
                    f"{fa['green_revenue_pct']}%",
                    fa['fossil_exposure'],
                    fa['transition_risk_label'],
                    f"{fa['transition_risk_score']}",
                    fa['paris_alignment']['status'],
                    'Yes' if fa['has_sbti_target'] else 'No',
                    nz_a,
                    f"{fa['climate_var']['net_zero_1_5c']['scope12_var_pct']:.1f}%",
                    f"{fa['climate_var']['net_zero_1_5c']['full_scope_var_pct']:.1f}%",
                    fa['stranded_asset_signal'].split('—')[0].strip(),
                    '✅ Real' if fa['using_real_data'] else '⚠️ Proxy',
                ],
                fb['ticker']: [
                    fb['sector'],
                    f"{fb['intensity_s12']:.1f}",
                    f"{fb['green_revenue_pct']}%",
                    fb['fossil_exposure'],
                    fb['transition_risk_label'],
                    f"{fb['transition_risk_score']}",
                    fb['paris_alignment']['status'],
                    'Yes' if fb['has_sbti_target'] else 'No',
                    nz_b,
                    f"{fb['climate_var']['net_zero_1_5c']['scope12_var_pct']:.1f}%",
                    f"{fb['climate_var']['net_zero_1_5c']['full_scope_var_pct']:.1f}%",
                    fb['stranded_asset_signal'].split('—')[0].strip(),
                    '✅ Real' if fb['using_real_data'] else '⚠️ Proxy',
                ],
            }
            st.dataframe(pd.DataFrame(comp), use_container_width=True, hide_index=True)

            st.markdown("---")

            # ── Visual comparisons ────────────────────────────────────────────
            st.subheader("📈 Visual Comparison")
            v1, v2 = st.columns(2)

            with v1:
                # Carbon intensity bar
                fig, ax = plt.subplots(figsize=(5, 3.5))
                tickers = [fa['ticker'], fb['ticker']]
                intensities = [fa['intensity_s12'], fb['intensity_s12']]
                colors = ['#3b82f6' if i == min(intensities) else '#ef4444' for i in intensities]
                ax.bar(tickers, intensities, color=colors, alpha=0.85)
                ax.set_ylabel('tCO2e / $M revenue (Scope 1+2)', fontsize=9)
                ax.set_title('Carbon Intensity Comparison', fontsize=10, fontweight='bold')
                ax.grid(axis='y', alpha=0.3)
                fig.tight_layout()
                st.pyplot(fig)
                plt.close()

            with v2:
                # Climate VaR comparison across scenarios
                scenarios_short = ['Current\nPolicy', 'NDC\nPledges', 'Paris\n2°C', 'Net Zero\n1.5°C', 'Tail\nRisk']
                vars_a = [v['scope12_var_pct'] for v in fa['climate_var'].values()]
                vars_b = [v['scope12_var_pct'] for v in fb['climate_var'].values()]

                fig2, ax2 = plt.subplots(figsize=(5, 3.5))
                x = range(len(scenarios_short))
                ax2.plot(list(x), vars_a, 'o-', color='#3b82f6', label=fa['ticker'], linewidth=2)
                ax2.plot(list(x), vars_b, 's-', color='#ef4444', label=fb['ticker'], linewidth=2)
                ax2.axhline(y=100, color='gray', linestyle='--', alpha=0.4)
                ax2.set_xticks(list(x))
                ax2.set_xticklabels(scenarios_short, fontsize=8)
                ax2.set_ylabel('% EBIT at risk (Scope 1+2)', fontsize=9)
                ax2.set_title('Climate VaR by Scenario', fontsize=10, fontweight='bold')
                ax2.legend(fontsize=8)
                ax2.grid(alpha=0.3)
                fig2.tight_layout()
                st.pyplot(fig2)
                plt.close()

            # ── Winner ────────────────────────────────────────────────────────
            st.markdown("---")
            st.subheader("🏆 Climate Risk Winner")
            score_a = fa['transition_risk_score']
            score_b = fb['transition_risk_score']
            winner  = fa if score_a < score_b else fb
            loser   = fb if score_a < score_b else fa
            st.success(
                f"**{winner['ticker']}** has lower net climate risk "
                f"(score: {winner['transition_risk_score']}/100 vs {loser['transition_risk_score']}/100)  \n"
                f"Intensity: {winner['intensity_s12']:.1f} vs {loser['intensity_s12']:.1f} tCO2/$M  |  "
                f"Green revenue: {winner['green_revenue_pct']}% vs {loser['green_revenue_pct']}%  |  "
                f"Paris: {winner['paris_alignment']['status']}"
            )

        except Exception as e:
            st.error(f"❌ Error: {str(e)}")