"""
Climate Factor Analyzer — Core Analysis Engine v3.0
====================================================
IFRS S2 (ISSB)-aligned climate risk assessment with peer-relative z-score benchmarking.

Data architecture:
  - Scope 1+2: Reported emissions from company sustainability reports (2023)
    Used for: IFRS S2 (ISSB) disclosure comparison, peer z-scores (apples-to-apples)
  - Scope 1+2+3: S1+2 * sector multiplier (CDP 2023 Supply Chain Report)
    Used for: Climate VaR, full financial risk exposure, stranded asset signal
  - Scope 2 note: Tech companies report market-based Scope 2 = 0 (RECs/PPAs).
    Location-based estimates included separately for grid impact assessment.

Frameworks referenced:
  # TCFD was disbanded October 2023; recommendations fully absorbed into IFRS S2 (ISSB),
  # effective January 2024. Institutional standard adopted by has been adopted by major institutional investors.
  # Reference: https://www.ifrs.org/sustainability/tcfd/
  - IFRS S2 (ISSB) — Climate-related Disclosures (effective January 2024)
  - IEA Net Zero by 2050 (NZE2050) carbon price pathways
  - Science Based Targets initiative (SBTi) Sectoral Decarbonization Approach
  - CDP 2023 Supply Chain Report (Scope 3 multipliers)
  - Damodaran NYU Stern 2024 (sector EBIT margins)

Author: Duru Sacinti | UC Berkeley Environmental Economics + Data Science Alumna
"""

import os
import logging
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

# yfinance prints 404 errors to terminal for invalid tickers,
# which are harmless but look bad during a demo. CRITICAL keeps only hard crashes.
logging.getLogger('yfinance').setLevel(logging.CRITICAL)


# =============================================================================
# SECTION 1: EMISSIONS DATABASE
# Sources: Company sustainability reports, CDP disclosures (2023 data year)
# All values in tonnes CO2e. Scope 2 = market-based unless noted.
# =============================================================================

def _load_emissions_db() -> dict:
    """
    Load verified Scope 1+2 emissions from CSV if available, else use hardcoded
    fallback sourced directly from 2023 company sustainability reports.

    CSV format: ticker, company, sector, scope1_tonnes, scope2_tonnes, source, year, notes
    """
    csv_path = os.path.join(os.path.dirname(__file__), 'emissions_data.csv')
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        db = {}
        for _, row in df.iterrows():
            db[row['ticker']] = {
                'scope1': float(row['scope1_tonnes']),
                'scope2': float(row['scope2_tonnes']),
                'source': row['source'],
                'year':   str(row['year']),
                'notes':  row.get('notes', ''),
            }
        return db

    # Hardcoded fallback — exact values from sustainability reports
    # scope2 = market-based (0 for tech companies with 100% renewable matching)
    return {
        # --- Automotive ---
        'TSLA': {'scope1':   211_000, 'scope2':   466_000,
                 'source': 'Tesla 2023 Impact Report (third-party assured)', 'year': '2023',
                 'notes': 'Scope 2 location-based'},
        'F':    {'scope1': 1_800_000, 'scope2':   900_000,
                 'source': 'Ford CDP Climate Disclosure 2023 / Integrated Sustainability Report', 'year': '2023',
                 'notes': 'Scope 1+2 reduced 35% since 2017'},
        'GM':   {'scope1': 4_100_000, 'scope2': 2_100_000,
                 'source': 'GM 2023 Sustainability Report', 'year': '2023',
                 'notes': 'Includes all global manufacturing'},
        'TM':   {'scope1': 5_800_000, 'scope2': 2_900_000,
                 'source': 'Toyota Environmental Report 2023', 'year': '2023',
                 'notes': 'Global operations incl. manufacturing; Scope 3 Cat11 ~520Mt'},
        'STLA': {'scope1': 1_900_000, 'scope2': 1_100_000,
                 'source': 'Stellantis 2023 Sustainability Report', 'year': '2023',
                 'notes': 'Post-merger combined footprint'},

        # --- Oil & Gas ---
        'XOM':  {'scope1': 92_000_000, 'scope2':  7_000_000,
                 'source': 'ExxonMobil 2023 Advancing Climate Solutions Report (ISO 14064-3 assured)', 'year': '2023',
                 'notes': 'Operated assets basis; equity basis ~111Mt total'},
        'CVX':  {'scope1': 37_000_000, 'scope2':  3_000_000,
                 'source': 'Chevron 2023 Sustainability Performance Data (operated basis)', 'year': '2023',
                 'notes': 'Upstream 17Mt + downstream 20Mt Scope 1'},
        'COP':  {'scope1': 17_000_000, 'scope2':  1_500_000,
                 'source': 'ConocoPhillips 2023 Sustainability Report', 'year': '2023',
                 'notes': 'Operated assets'},
        'BP':   {'scope1': 42_000_000, 'scope2':  4_500_000,
                 'source': 'BP 2023 Sustainability Report', 'year': '2023',
                 'notes': 'Operated basis'},
        'SHEL': {'scope1': 68_000_000, 'scope2':  5_500_000,
                 'source': 'Shell 2023 Sustainability Report', 'year': '2023',
                 'notes': 'Operated basis'},

        # --- Utilities ---
        'NEE':  {'scope1': 22_000_000, 'scope2':  1_200_000,
                 'source': 'NextEra Energy 2023 ESG Report', 'year': '2023',
                 'notes': 'Includes FPL and NEER segments; high S1 due to gas peakers'},
        'DUK':  {'scope1': 48_000_000, 'scope2':  2_100_000,
                 'source': 'Duke Energy 2023 ESG Report', 'year': '2023',
                 'notes': 'Primarily coal/gas generation'},
        'SO':   {'scope1': 38_000_000, 'scope2':  1_800_000,
                 'source': 'Southern Company 2023 ESG Report', 'year': '2023'},
        'D':    {'scope1': 19_000_000, 'scope2':    900_000,
                 'source': 'Dominion Energy 2023 ESG Report', 'year': '2023',
                 'notes': 'Post-asset-sale portfolio'},
        'AEP':  {'scope1': 56_000_000, 'scope2':  2_400_000,
                 'source': 'AEP 2023 Corporate Responsibility Report', 'year': '2023',
                 'notes': 'Heavy coal generation exposure'},

        # --- Technology ---
        # Scope 2 = 0 reflects market-based (100% renewable matched via RECs/PPAs)
        # Location-based Scope 2 stored separately in SCOPE2_LOCATION_BASED
        'MSFT': {'scope1':   280_000, 'scope2':         0,
                 'source': 'Microsoft 2023 Environmental Sustainability Report', 'year': '2023',
                 'notes': 'Scope 2 market-based = 0 (100% renewable matched); location-based ~3.5Mt'},
        'GOOGL':{'scope1':   320_000, 'scope2':         0,
                 'source': 'Alphabet 2023 ESG Report', 'year': '2023',
                 'notes': 'Scope 2 market-based = 0 (carbon-free energy matching); location-based ~3.4Mt'},
        'AAPL': {'scope1':   180_000, 'scope2':         0,
                 'source': 'Apple 2023 Environmental Progress Report', 'year': '2023',
                 'notes': 'Operations 100% renewable since 2018; location-based ~1.2Mt'},
        'META': {'scope1':   190_000, 'scope2':         0,
                 'source': 'Meta 2023 Sustainability Report', 'year': '2023',
                 'notes': 'Net zero operations via RECs; location-based ~2.8Mt'},
        'AMZN': {'scope1': 9_800_000, 'scope2':  3_200_000,
                 'source': 'Amazon 2023 Sustainability Report', 'year': '2023',
                 'notes': 'Logistics fleet dominates; largest tech emitter by far'},
    }


EMISSIONS_DB = _load_emissions_db()

# Location-based Scope 2 for tech companies (source: respective 2023 ESG reports)
# Used for transparency only — z-scores use market-based for peer consistency
SCOPE2_LOCATION_BASED = {
    'MSFT':  3_500_000,
    'GOOGL': 3_400_000,
    'AAPL':  1_200_000,
    'META':  2_800_000,
}


# =============================================================================
# SECTION 2: PEER GROUPS & SECTOR MAPPING
# =============================================================================

SECTOR_PEERS = {
    'Auto':      ['TSLA', 'F', 'GM', 'TM', 'STLA'],
    'Oil & Gas': ['XOM', 'CVX', 'COP', 'BP', 'SHEL'],
    'Utilities': ['NEE', 'DUK', 'SO', 'D', 'AEP'],
    'Technology':['MSFT', 'GOOGL', 'AAPL', 'META', 'AMZN'],
}

SECTOR_MAP = {
    # Consumer Cyclical intentionally omitted: _resolve_sector_group handles auto/vehicle
    # detection explicitly. Non-auto Consumer Cyclical (e.g. Luxury Goods) gets no peer group.
    'Energy':                 'Oil & Gas',
    'Utilities':              'Utilities',
    'Technology':             'Technology',
    'Communication Services': 'Technology',
}


def _resolve_sector_group(sector: str, industry: str):
    industry_lower = industry.lower()
    if 'auto' in industry_lower or 'vehicle' in industry_lower:
        return 'Auto'
    return SECTOR_MAP.get(sector)


# =============================================================================
# SECTION 3: FALLBACK INDUSTRY PROXIES (Scope 1+2 only)
# Used when a ticker lacks reported data.
# Values calibrated to Scope 1+2 only — NOT blended with Scope 3.
# Sources: EPA GHGP sector guidance, CDP industry averages
# =============================================================================

INDUSTRY_CARBON_MAP = {
    'Oil & Gas E&P': 250,
    'Oil & Gas Integrated': 230,
    'Oil & Gas Refining & Marketing': 180,
    'Oil & Gas Midstream': 120,
    'Utilities - Regulated Electric': 1_500,
    'Utilities - Renewable': 40,
    'Auto Manufacturers': 25,
    'Auto Parts': 15,
    'Steel': 300, 'Aluminum': 280, 'Chemicals': 200,
    'Airlines': 200, 'Railroads': 80, 'Trucking': 150,
    'Software - Application': 1, 'Software - Infrastructure': 2,
    'Semiconductors': 10, 'Internet Content & Information': 2,
    'Financial Services': 5, 'Healthcare': 20, 'Retail': 30,
}

SECTOR_FALLBACK_MAP = {
    'Energy': 600, 'Basic Materials': 350, 'Technology': 15,
    'Financial Services': 20, 'Consumer Cyclical': 100,
    'Healthcare': 40, 'Industrials': 150, 'Utilities': 200,
}


# =============================================================================
# SECTION 4: CLIMATE FINANCE PARAMETERS
# =============================================================================

# Scope 3 multipliers: (Scope1+2+3 total) / (Scope1+2)
# Source: CDP 2023 Supply Chain Report, SBTi Value Chain Guidance
SCOPE3_MULTIPLIERS = {
    'TSLA': 2.0,
    'F': 4.0, 'GM': 4.0, 'STLA': 4.0,
    'TM': 60.0,    # Toyota Scope3 Cat11 ~520Mt vs 8.7Mt S1+2 (Toyota Env Report 2023)
    'XOM': 7.5, 'CVX': 7.0, 'COP': 8.0, 'BP': 6.5, 'SHEL': 6.5,
    'NEE': 1.2, 'DUK': 1.2, 'SO': 1.2, 'D': 1.2, 'AEP': 1.2,
    'MSFT': 3.5, 'GOOGL': 3.0,
    'AAPL': 28.0,  # Apple Scope3 ~23Mt (devices in use) vs 0.18Mt S1+2
    'META': 3.0, 'AMZN': 5.0,
}

# IEA NZE2050 carbon price pathways ($/tonne CO2e)
# Source: IEA World Energy Outlook 2023
CARBON_PRICE_SCENARIOS = {
    'current_policy': {'price': 15,  'label': 'Current Policy (~2024)',      'year': 2024},
    'ndc_pledges':    {'price': 45,  'label': 'NDC Pledges Scenario (2030)', 'year': 2030},
    'paris_2c':       {'price': 75,  'label': 'Paris 2°C Pathway (2030)',    'year': 2030},
    'net_zero_1_5c':  {'price': 130, 'label': 'IEA Net Zero 1.5°C (2030)',   'year': 2030},
    'aggressive':     {'price': 250, 'label': 'Tail Risk Scenario (2035)',   'year': 2035},
}

# SBTi Sectoral Decarbonization Approach — 1.5°C / 2°C Scope 1+2 intensity budgets (2030)
# Source: SBTi Corporate Net-Zero Standard v1.1
SBTI_BUDGETS = {
    'Auto':      {'1.5c': 5,    '2c': 8},
    'Oil & Gas': {'1.5c': 80,   '2c': 130},
    'Utilities': {'1.5c': 400,  '2c': 650},
    'Technology':{'1.5c': 1,    '2c': 1.5},
    'default':   {'1.5c': 50,   '2c': 80},
}

# Sub-sector SBTi overrides — applied before sector-level fallback.
# Prevents applying auto-calibrated budgets to unrelated Consumer Cyclical sub-industries.
# Source: SBTi sector guidance notes + CDP sector pathway analysis.
INDUSTRY_SBTI_BUDGETS = {
    'Luxury Goods':    {'1.5c': 30, '2c': 50},
    'Apparel Retail':  {'1.5c': 25, '2c': 40},
    'Grocery Stores':  {'1.5c': 20, '2c': 35},
    'Packaged Foods':  {'1.5c': 35, '2c': 55},
    'Real Estate':     {'1.5c': 15, '2c': 25},
}

# Sector EBIT margins — Source: Damodaran NYU Stern, January 2024
SECTOR_EBIT_MARGINS = {
    'Oil & Gas': 0.12, 'Utilities': 0.16, 'Auto': 0.05,
    'Technology': 0.25, 'Industrials': 0.10,
}


# --- IEA Net Zero 2030 benchmark intensities (tCO2 / $M) — used for Paris alignment
IEA_2030_BENCHMARKS = {
    'Energy': 180,
    'Materials': 200,
    'Industrials': 150,
    'Consumer Cyclical': 60,
    'Technology': 8,
    'Utilities': 120,
    'Financials': 15,
}


# Net-zero target lookup (explicit known companies). Unknown tickers -> 'Unknown'
# None = company has no declared net-zero target (not the same as unknown/unlisted).
NET_ZERO_TARGETS = {
    'LVMH': 2050, 'MC.PA': 2050, 'TSLA': 2040, 'MSFT': 2030,
    'XOM': None, 'NEE': 2045, 'F': 2050, 'BP': 2050, 'SHEL': 2050,
    'AAPL': 2030, 'GOOGL': 2030, 'META': 2030, 'AMZN': 2040,
    'NVDA': None, 'JPM': None, 'BAC': 2050,
}


# Industry-derived green revenue defaults (percent, 0-1). Broader coverage added.
INDUSTRY_GREEN_REVENUE_PCT = {
    'Luxury Goods': 0.05,
    'Apparel & Luxury': 0.05,
    'Automobile Manufacturers': 0.15,
    'Auto Manufacturers': 0.15,
    'Consumer Staples': 0.10,
    'Retail': 0.08,
    'Real Estate': 0.02,
    'Mining': 0.03,
    'Steel': 0.02,
    'Oil & Gas': 0.01,
    'Utilities': 0.30,
    'Renewable Electricity': 0.80,
    'Software': 0.40,
    'Semiconductors': 0.20,
    'Financial Services': 0.02,
}


# Industry intensity multipliers relative to sector benchmark (defaults to 1.0)
INDUSTRY_INTENSITY_FACTOR = {
    'Luxury Goods': 0.8,
    'Apparel & Luxury': 0.8,
    'Automobile Manufacturers': 1.1,
    'Auto Manufacturers': 1.1,
    'Consumer Staples': 0.9,
    'Retail': 0.9,
    'Real Estate': 0.6,
    'Mining': 1.3,
    'Steel': 1.6,
    'Oil & Gas': 2.0,
    'Utilities': 1.0,
    'Renewable Electricity': 0.3,
    'Software': 0.1,
    'Semiconductors': 0.3,
    'Financial Services': 0.05,
}


def _estimate_green_rev_pct(sector: str, industry: str) -> float:
    """Estimate green revenue fraction from industry/sector mapping.

    Returns a fraction between 0 and 1.
    """
    if not industry:
        return 0.05
    # direct lookup
    pct = INDUSTRY_GREEN_REVENUE_PCT.get(industry)
    if pct is not None:
        return pct
    # try fuzzy matches
    for key in INDUSTRY_GREEN_REVENUE_PCT:
        if key.lower() in industry.lower():
            return INDUSTRY_GREEN_REVENUE_PCT[key]
    # sector-level fallbacks
    if sector == 'Technology':
        return 0.25
    if sector in ('Energy', 'Basic Materials'):
        return 0.02
    if sector in ('Utilities',):
        return 0.35
    return 0.05


def _estimate_company_intensity(sector: str, industry: str, green_rev_frac: float) -> float:
    """Estimate company carbon intensity (tCO2 / $M) from sector benchmark,
    industry factor, and green revenue fraction.
    """
    base = IEA_2030_BENCHMARKS.get(sector)
    if base is None:
        # fallback to SECTOR_FALLBACK_MAP (earlier defined) or a default
        base = SECTOR_FALLBACK_MAP.get(sector, 100)
    factor = 1.0
    if industry:
        # try direct, then fuzzy
        factor = INDUSTRY_INTENSITY_FACTOR.get(industry, factor)
        for key in INDUSTRY_INTENSITY_FACTOR:
            if key.lower() in industry.lower():
                factor = INDUSTRY_INTENSITY_FACTOR[key]
                break
    # reduce intensity by share of green revenue as a first-order proxy
    intensity = base * factor * (1.0 - float(green_rev_frac))
    return float(round(intensity, 2))


def _get_net_zero_target_for_ticker(ticker: str) -> str:
    if ticker not in NET_ZERO_TARGETS:
        return 'Unknown'
    val = NET_ZERO_TARGETS[ticker]
    if val is None:
        return 'None declared'
    return val


def _sync_net_zero(ticker: str, profile_year) -> str:
    """Return the net-zero target for a ticker, keeping NET_ZERO_TARGETS and
    COMPANY_PROFILE in sync.

    Priority:
      1. NET_ZERO_TARGETS[ticker] — explicit entry (including None → 'None declared')
      2. COMPANY_PROFILE[ticker]['nz_year'] — fallback when ticker is missing from
         NET_ZERO_TARGETS, preventing the two tables drifting out of sync.
      3. 'Unknown' — ticker appears in neither table.

    Args:
        ticker:       Uppercase ticker string.
        profile_year: nz_year value from COMPANY_PROFILE (int or None), or None if
                      the ticker has no COMPANY_PROFILE entry.
    """
    if ticker in NET_ZERO_TARGETS:
        return _get_net_zero_target_for_ticker(ticker)
    # Fallback: use COMPANY_PROFILE value to avoid silent 'Unknown' for known companies
    if profile_year is not None:
        return profile_year  # integer year — callers handle int vs str display
    return 'Unknown'


def _compute_transition_velocity(ticker: str) -> str:
    """Proxy for transition velocity from 3-year capex-to-revenue trend.

    Uses yfinance `financials` and `cashflow`. Returns: 'Accelerating', 'Stable', 'Slowing', or 'Unknown'.
    """
    tk = yf.Ticker(ticker)
    try:
        fin = tk.financials
        cf = tk.cashflow
    except Exception:
        return 'Unknown'

    if fin is None or cf is None or fin.empty or cf.empty:
        return 'Unknown'

    # find revenue row
    revenue_row = None
    for candidate in ['Total Revenue', 'Total revenues', 'TotalRevenue', 'Revenue', 'totalRevenue']:
        if candidate in fin.index:
            revenue_row = candidate
            break
    if revenue_row is None:
        # fallback to first numeric-like row that contains 'Revenue'
        for idx in fin.index:
            if 'revenue' in str(idx).lower():
                revenue_row = idx
                break
    if revenue_row is None:
        return 'Unknown'

    capex_row = None
    for candidate in ['Capital Expenditure', 'Capital Expenditures', 'CapitalExpenditures', 'capitalExpenditures', 'Capex']:
        if candidate in cf.index:
            capex_row = candidate
            break
    if capex_row is None:
        for idx in cf.index:
            if 'capital expenditure' in str(idx).lower():
                capex_row = idx
                break
    if capex_row is None:
        return 'Unknown'

    # columns are years (timestamps) — align years present in both
    rev_series = fin.loc[revenue_row]
    capex_series = cf.loc[capex_row]
    # convert to pandas Series and drop NaNs
    rev_series = rev_series.dropna()
    capex_series = capex_series.dropna()
    # find intersection of columns
    years = [c for c in rev_series.index if c in capex_series.index]
    if len(years) < 2:
        return 'Unknown'

    # pick up to 3 most recent years
    years = sorted(years, reverse=True)[:3]
    ratios = []
    for y in reversed(years):  # oldest -> newest
        rev = rev_series.get(y)
        capex = capex_series.get(y)
        try:
            rev = float(rev)
            capex = float(capex)
            if rev == 0:
                ratios.append(None)
            else:
                ratios.append(abs(capex) / rev)
        except Exception:
            ratios.append(None)
    ratios = [r for r in ratios if r is not None]
    if len(ratios) < 2:
        return 'Unknown'

    oldest = ratios[0]
    latest = ratios[-1]
    if oldest == 0:
        if latest > 0:
            return 'Accelerating'
        return 'Stable'

    change = (latest - oldest) / abs(oldest)
    if change > 0.10:
        return 'Accelerating'
    if change < -0.10:
        return 'Slowing'
    return 'Stable'


def get_climate_profile(ticker: str) -> dict:
    """Return a climate profile dict for `ticker` using industry/sector-derived heuristics.

    Fields returned:
      - ticker, name, sector, industry
      - green_revenue_pct (0-100)
      - estimated_carbon_intensity (tCO2 / $M)
      - sector_benchmark_2030
      - paris_aligned (bool) and alignment_details
      - net_zero_target (year or 'Unknown')
      - transition_velocity ('Accelerating'|'Stable'|'Slowing'|'Unknown')
      - peer_benchmark (sector average intensity used for comparison)
      - peer_comparison ('Below'/'Above'/'Equal')
    """
    tk = yf.Ticker(ticker)
    info = {}
    try:
        info = tk.info or {}
    except Exception:
        info = {}

    name = info.get('shortName') or info.get('longName') or ticker
    sector = info.get('sector') or 'Unknown'
    industry = info.get('industry') or ''

    green_frac = _estimate_green_rev_pct(sector, industry)
    est_intensity = _estimate_company_intensity(sector, industry, green_frac)

    sector_bench = IEA_2030_BENCHMARKS.get(sector)
    # Paris alignment: compare estimated intensity against IEA 2030 benchmark
    paris_aligned = False
    alignment = {}
    if sector_bench is not None:
        paris_aligned = est_intensity <= sector_bench
        alignment = {
            'sector_benchmark_2030': sector_bench,
            'company_intensity': est_intensity,
            'paris_aligned': paris_aligned,
            'note': f"Company intensity {est_intensity} tCO2/$M vs sector 2030 benchmark {sector_bench} tCO2/$M",
        }
    else:
        alignment = {'note': 'No sector benchmark available', 'paris_aligned': False}

    profile_nz_year = COMPANY_PROFILE.get(ticker, {}).get('nz_year')
    net_zero = _sync_net_zero(ticker, profile_nz_year)
    transition_velocity = _compute_transition_velocity(ticker)

    # peer benchmarking — use sector benchmark as sector average proxy (no emissions required)
    peer_benchmark = sector_bench if sector_bench is not None else SECTOR_FALLBACK_MAP.get(sector, None)
    peer_comparison = 'Unknown'
    if peer_benchmark is not None:
        if est_intensity < peer_benchmark:
            peer_comparison = 'Below'
        elif est_intensity > peer_benchmark:
            peer_comparison = 'Above'
        else:
            peer_comparison = 'Equal'

    return {
        'ticker': ticker,
        'name': name,
        'sector': sector,
        'industry': industry,
        'green_revenue_pct': round(float(green_frac) * 100, 1),
        'estimated_carbon_intensity_tCO2_per_$M': est_intensity,
        'sector_benchmark_2030_tCO2_per_$M': sector_bench,
        'paris_alignment': alignment,
        'net_zero_target': net_zero if net_zero is not None else 'Unknown',
        'transition_velocity': transition_velocity,
        'peer_benchmark_tCO2_per_$M': peer_benchmark,
        'peer_comparison': peer_comparison,
    }


# Green revenue & SBTi commitments
# Source: Company sustainability reports + SBTi target dashboard (sciencebasedtargets.org)
COMPANY_PROFILE = {
    'MC.PA': {'green_rev': 5,  'has_sbti': True,  'nz_year': 2050},  # LVMH 2050 net-zero (CDP 2023)
    'TSLA': {'green_rev': 97, 'has_sbti': True,  'nz_year': 2040},
    'F':    {'green_rev': 12, 'has_sbti': True,  'nz_year': 2050},
    'GM':   {'green_rev': 8,  'has_sbti': True,  'nz_year': 2050},
    'TM':   {'green_rev': 18, 'has_sbti': True,  'nz_year': 2050},
    'STLA': {'green_rev': 10, 'has_sbti': True,  'nz_year': 2038},
    'XOM':  {'green_rev': 2,  'has_sbti': False, 'nz_year': None},
    'CVX':  {'green_rev': 3,  'has_sbti': False, 'nz_year': None},
    'COP':  {'green_rev': 1,  'has_sbti': False, 'nz_year': None},
    'BP':   {'green_rev': 8,  'has_sbti': True,  'nz_year': 2050},
    'SHEL': {'green_rev': 10, 'has_sbti': True,  'nz_year': 2050},
    'NEE':  {'green_rev': 88, 'has_sbti': True,  'nz_year': 2045},
    'DUK':  {'green_rev': 18, 'has_sbti': True,  'nz_year': 2050},
    'SO':   {'green_rev': 12, 'has_sbti': True,  'nz_year': 2050},
    'D':    {'green_rev': 20, 'has_sbti': True,  'nz_year': 2050},
    'AEP':  {'green_rev': 15, 'has_sbti': True,  'nz_year': 2050},
    'MSFT': {'green_rev': 25, 'has_sbti': True,  'nz_year': 2030},
    'GOOGL':{'green_rev': 20, 'has_sbti': True,  'nz_year': 2030},
    'AAPL': {'green_rev': 10, 'has_sbti': True,  'nz_year': 2030},
    'META': {'green_rev': 12, 'has_sbti': True,  'nz_year': 2030},
    'AMZN': {'green_rev': 15, 'has_sbti': True,  'nz_year': 2040},
}


# =============================================================================
# SECTION 5: REVENUE HELPER
# =============================================================================

def _get_revenue_millions(ticker: str):
    """
    Fetch annual revenue in $M from yfinance.
    yfinance totalRevenue is in raw dollars — divide by 1,000,000 for $M.

    Note: yfinance has a known bug where Japanese tickers (e.g. TM) return revenue
    in JPY but mislabel the currency as USD. Values above 5 trillion are treated as
    JPY and converted using a live USD/JPY rate fetch with 150 as fallback.
    """
    try:
        info = yf.Ticker(ticker).info
        rev = info.get('totalRevenue')
        if rev and rev > 0:
            if rev > 5_000_000_000_000:
                try:
                    fx = yf.Ticker('USDJPY=X').info.get('regularMarketPrice', 150)
                    usd_jpy = fx if fx and fx > 100 else 150
                except Exception:
                    usd_jpy = 150
                rev = rev / usd_jpy
            return rev / 1_000_000  # raw dollars → $M
    except Exception:
        pass
    return None


# =============================================================================
# SECTION 6: PEER Z-SCORE (Scope 1+2 consistent across all peers)
# =============================================================================

def calculate_peer_z_score(ticker: str, sector_group: str) -> tuple:
    """
    Scope 1+2 carbon intensity z-score within sector peer group.

    All peers use market-based Scope 2 for apples-to-apples comparison.
    Tech Scope 2 = 0 is valid — verified renewable procurement sets this to zero.

    intensity = (Scope1 + Scope2_market_based) / revenue_$M

    Returns: (z_score, intensity, confidence, peer_intensities_dict)
    """
    peers = SECTOR_PEERS.get(sector_group, [])
    peer_intensities = {}

    for peer in peers:
        if peer not in EMISSIONS_DB:
            continue
        rev = _get_revenue_millions(peer)
        if not rev:
            continue
        em = EMISSIONS_DB[peer]
        peer_intensities[peer] = (em['scope1'] + em['scope2']) / rev

    if len(peer_intensities) < 3:
        return None, None, 'insufficient_peers', {}

    if ticker not in EMISSIONS_DB:
        return None, None, 'no_emissions_data', peer_intensities

    rev = _get_revenue_millions(ticker)
    if not rev:
        return None, None, 'no_revenue_data', peer_intensities

    em = EMISSIONS_DB[ticker]
    target_intensity = (em['scope1'] + em['scope2']) / rev

    values = list(peer_intensities.values())
    mean = np.mean(values)
    std  = np.std(values)
    z = round((target_intensity - mean) / std, 2) if std > 0 else 0.0

    return z, round(target_intensity, 2), 'high', peer_intensities


def z_to_risk_label(z) -> str:
    if z is None: return 'Unknown'
    if z >  1.0:  return 'Very High'
    if z >  0.4:  return 'High'
    if z > -0.4:  return 'Medium'
    if z > -1.0:  return 'Low'
    return 'Very Low'


# =============================================================================
# SECTION 7: PARIS ALIGNMENT (SBTi Sectoral Decarbonization Approach)
# =============================================================================

def check_paris_alignment(intensity_s12: float, sector_group: str,
                           has_sbti: bool, nz_year, industry: str = '') -> dict:
    # Industry-level override first; fall back to sector-level budget.
    budgets = (INDUSTRY_SBTI_BUDGETS.get(industry)
               or SBTI_BUDGETS.get(sector_group or 'default', SBTI_BUDGETS['default']))
    b15, b2c = budgets['1.5c'], budgets['2c']
    has_commitment = has_sbti and nz_year and nz_year <= 2050

    if intensity_s12 <= b15:
        status = '1.5C Aligned' if has_commitment else '1.5C Consistent (unverified)'
        label  = ('✅ 1.5°C Aligned' if has_commitment
                  else '🟡 1.5°C Consistent (no formal commitment)')
        note   = f'Intensity ({intensity_s12:.1f}) within SBTi 1.5°C budget ({b15}).'
        if has_commitment:
            note += f' Verified net-zero by {nz_year}.'
    elif intensity_s12 <= b2c:
        status = '2C Aligned' if has_commitment else 'Potentially 2C Aligned'
        label  = ('🟡 Paris 2°C Aligned' if has_commitment
                  else '🟠 Potentially 2°C (unverified)')
        note   = f'Within 2°C budget ({b2c} tCO2/$M). Reduce further to meet 1.5°C target ({b15} tCO2/$M).'
    else:
        reduction_pct = ((intensity_s12 - b2c) / intensity_s12) * 100
        status = 'Committed, Off Track' if has_commitment else 'Paris Misaligned'
        label  = ('🔴 Committed but Off Track' if has_commitment
                  else '🔴 Paris Misaligned')
        note   = (
            f'Net-zero target ({nz_year}), but intensity ({intensity_s12:.1f}) exceeds 2°C budget ({b2c}). '
            f'Requires {reduction_pct:.0f}% reduction.'
            if has_commitment else
            f'Intensity ({intensity_s12:.1f}) exceeds 2°C budget ({b2c}) by {reduction_pct:.0f}%. No credible pathway.'
        )

    return {
        'status': status, 'label': label, 'note': note,
        'budget_1_5c': b15, 'budget_2c': b2c,
        'required_reduction_pct': round(max(0, (intensity_s12 - b2c) / intensity_s12 * 100), 1),
    }


# =============================================================================
# SECTION 8: CLIMATE VALUE AT RISK
# =============================================================================

def calculate_climate_var(intensity_s12: float, revenue_bn: float,
                           sector_group: str, scope3_multiplier: float) -> dict:
    """
    Climate VaR: % of EBIT at risk from carbon pricing across IEA scenarios.
    Scope 1+2 VaR = direct operational exposure.
    Full-scope VaR = full value chain liability (incl. Scope 3).
    """
    margin    = SECTOR_EBIT_MARGINS.get(sector_group, 0.10)
    revenue_m = revenue_bn * 1000
    s12_em    = intensity_s12 * revenue_m
    full_em   = s12_em * scope3_multiplier
    ebit_bn   = revenue_bn * margin

    results = {}
    for key, sc in CARBON_PRICE_SCENARIOS.items():
        price = sc['price']
        s12_cost  = (s12_em  * price) / 1e9
        full_cost = (full_em * price) / 1e9
        results[key] = {
            'carbon_price':       price,
            'label':              sc['label'],
            'scope12_var_pct':    round(s12_cost  / ebit_bn * 100 if ebit_bn > 0 else 0, 1),
            'full_scope_var_pct': round(full_cost / ebit_bn * 100 if ebit_bn > 0 else 0, 1),
            'scope12_cost_bn':    round(s12_cost, 2),
            'annual_emissions_mt': round(s12_em / 1e6, 1),
        }
    return results


# =============================================================================
# SECTION 9: TRANSITION RISK SCORE (0-100)
# =============================================================================

def _transition_risk_score(z_score, intensity_s12: float, green_rev: float,
                            has_sbti: bool, paris_status: str) -> tuple:
    # Intensity component (0-40): z-score preferred, absolute fallback
    if z_score is not None:
        intensity_component = min(40, max(0, (z_score + 2) / 4 * 40))
    else:
        if   intensity_s12 > 1500: intensity_component = 40
        elif intensity_s12 > 500:  intensity_component = 32
        elif intensity_s12 > 100:  intensity_component = 22
        elif intensity_s12 > 20:   intensity_component = 12
        else:                      intensity_component = 4

    green_derisk  = min(25, green_rev * 0.25)
    paris_penalty = {
        'Paris Misaligned': 20, 'Committed, Off Track': 14,
        'Potentially 2C Aligned': 10, '2C Aligned': 6,
        '1.5C Consistent (unverified)': 3, '1.5C Aligned': 0,
    }.get(paris_status, 10)
    sbti_penalty  = 0 if has_sbti else 15

    score = round(max(0, min(100, intensity_component - green_derisk + paris_penalty + sbti_penalty)), 1)
    label = ('Very High' if score >= 70 else 'High' if score >= 50 else
             'Medium' if score >= 30 else 'Low' if score >= 15 else 'Very Low')
    return score, label


# =============================================================================
# SECTION 10: MAIN ANALYSIS FUNCTION
# =============================================================================

def calculate_climate_factors(ticker: str) -> dict:
    """
    Full IFRS S2 (ISSB)-aligned climate risk profile.

    Calls get_climate_profile() internally for sector-derived estimates.
    Field mapping:
      carbon_intensity  ← estimated_carbon_intensity_tCO2_per_$M  (fallback when no real data)
      transition_risk   ← derived from paris_alignment + peer_comparison (from profile)
      status_note       ← generated from profile fields
    """
    ticker = ticker.upper().strip()

    # --- get sector-level profile (IEA benchmarks + green-revenue heuristics) ---
    climate_profile = get_climate_profile(ticker)

    info     = yf.Ticker(ticker).info
    sector   = info.get('sector', 'Unknown')
    industry = info.get('industry', 'Unknown').replace('—', '-').strip()
    sector_group = _resolve_sector_group(sector, industry)

    # Revenue
    rev_m = _get_revenue_millions(ticker)
    if rev_m and rev_m > 0:
        revenue_bn = rev_m / 1000
    else:
        rev_raw = info.get('totalRevenue', 0)
        revenue_bn = rev_raw / 1e9 if rev_raw else max(info.get('marketCap', 1e9) / 1e9 * 0.5, 0.5)

    # carbon_intensity ← estimated_carbon_intensity_tCO2_per_$M when no real data
    using_real_data = ticker in EMISSIONS_DB
    if using_real_data:
        em = EMISSIONS_DB[ticker]
        scope1, scope2   = em['scope1'], em['scope2']
        intensity_s12    = (scope1 + scope2) / (revenue_bn * 1000)
        emissions_source = em['source']
        emissions_year   = em['year']
        emissions_notes  = em.get('notes', '')
    else:
        # carbon_intensity mapped from profile's estimated_carbon_intensity_tCO2_per_$M
        intensity_s12    = climate_profile['estimated_carbon_intensity_tCO2_per_$M']
        scope1 = scope2  = None
        emissions_source = 'IEA sector benchmark (adjusted for industry factor and green revenue)'
        emissions_year   = 'N/A'
        emissions_notes  = 'Estimated via sector benchmark × industry factor × (1 − green revenue fraction). No company-specific data.'

    scope2_location = SCOPE2_LOCATION_BASED.get(ticker)

    # Peer z-score (Scope 1+2 consistent)
    z_score, _, z_conf, peer_data = None, None, 'unavailable', {}
    if sector_group:
        z_score, _, z_conf, peer_data = calculate_peer_z_score(ticker, sector_group)

    # Company profile (hardcoded COMPANY_PROFILE; fall back to climate_profile estimates)
    comp_profile = COMPANY_PROFILE.get(ticker, {})
    green_rev    = comp_profile.get('green_rev', climate_profile['green_revenue_pct'])
    has_sbti     = comp_profile.get('has_sbti', False)
    nz_year      = comp_profile.get('nz_year', None)
    # Resolve authoritative net-zero status: NET_ZERO_TARGETS > COMPANY_PROFILE > 'Unknown'
    _nz_raw      = _sync_net_zero(ticker, nz_year)
    net_zero_status = str(_nz_raw) if isinstance(_nz_raw, int) else _nz_raw

    scope3_mult = SCOPE3_MULTIPLIERS.get(ticker, 2.0)

    paris = check_paris_alignment(intensity_s12, sector_group, has_sbti, nz_year, industry)

    # Use actual SBTi paris status (computed from real intensity_s12, not heuristic estimate)
    paris_aligned_profile = paris['status'] in (
        '1.5C Aligned', '2C Aligned', '1.5C Consistent (unverified)', 'Potentially 2C Aligned'
    )
    # Use z_score for peer_comparison when real emissions data available; else profile heuristic
    if z_score is not None:
        peer_comparison = 'Below' if z_score < -0.4 else ('Above' if z_score > 0.4 else 'Equal')
    else:
        peer_comparison = climate_profile['peer_comparison']

    # _transition_risk_score uses z_score, intensity, green_rev, SBTi, and paris together.
    # Previously a dead 8-cell matrix was used here — this activates the proper scorer.
    risk_score, risk_label = _transition_risk_score(
        z_score, intensity_s12, green_rev, has_sbti, paris['status']
    )

    # Absolute intensity floor: being best-in-class among dirty peers doesn't eliminate
    # physical carbon-price exposure. Floor prevents contradictions like Low risk + HIGH VaR.
    if intensity_s12 > 800:
        floor_score, floor_label = 50, 'High'
    elif intensity_s12 > 500:
        floor_score, floor_label = 40, 'Medium'
    else:
        floor_score, floor_label = 0, None
    if floor_score and risk_score < floor_score:
        risk_score, risk_label = floor_score, floor_label

    climate_var = calculate_climate_var(intensity_s12, revenue_bn, sector_group or 'default', scope3_mult)

    # Fossil exposure
    # Utilities override: high grid-combustion intensity → Medium regardless of green revenue.
    # Green revenue reflects future direction but doesn't eliminate current fossil combustion.
    if sector == 'Utilities' and intensity_s12 > 500:  fossil_exp = 'Medium'
    elif green_rev > 75 or intensity_s12 < 5:          fossil_exp = 'Minimal'
    elif intensity_s12 < 20 or green_rev > 50:         fossil_exp = 'Low'
    elif sector == 'Energy':                            fossil_exp = 'High'
    elif intensity_s12 >= 150:                         fossil_exp = 'Medium'
    else:                                              fossil_exp = 'Low'

    # Stranded asset signal
    nz_var = climate_var['net_zero_1_5c']['scope12_var_pct']
    if   intensity_s12 > 150 and nz_var > 50:  stranded = 'HIGH — Material stranded asset risk under 1.5°C scenario'
    elif intensity_s12 > 50  and nz_var > 25:  stranded = 'MEDIUM — Significant repricing risk under Paris-aligned carbon prices'
    elif nz_var > 10:                           stranded = 'LOW-MEDIUM — Some asset repricing risk under aggressive scenarios'
    else:                                       stranded = 'LOW — Limited stranded asset exposure'

    # Analyst classification
    if green_rev > 80 and intensity_s12 < 20:
        cls, cls_note = 'Clean Pure-Play', 'Revenue predominantly from low-carbon products. Net beneficiary of carbon pricing.'
    elif green_rev > 50 and intensity_s12 > 50:
        cls, cls_note = 'Credible Transition Leader', 'Significant green revenue offsetting legacy high-carbon assets.'
    elif green_rev > 20 and intensity_s12 > 50:
        cls, cls_note = 'Early-Stage Transition', 'Green revenues emerging but legacy carbon exposure still dominant. Execution risk elevated.'
    elif intensity_s12 > 150 and green_rev < 10:
        cls, cls_note = 'Climate Laggard', 'High fossil dependency with minimal green transition. Material stranded asset risk under Paris-aligned carbon pricing.'
    elif has_sbti and paris['status'] in ['2C Aligned', '1.5C Aligned', '1.5C Consistent (unverified)']:
        cls, cls_note = 'Managed Transition', 'Moderate carbon exposure with credible decarbonization commitment and trajectory.'
    else:
        cls, cls_note = 'Standard — Monitor', 'Risk profile typical for sector. No exceptional leadership or laggard identified.'

    # status_note ← generated from profile fields
    status_note = (
        f"Paris aligned: {'Yes' if paris_aligned_profile else 'No'} | "
        f"Peer: {peer_comparison} benchmark | "
        f"Net-zero: {climate_profile['net_zero_target']} | "
        f"Velocity: {climate_profile['transition_velocity']}"
    )

    return {
        'ticker': ticker, 'company': info.get('longName', 'Unknown'),
        'sector': sector, 'industry': industry, 'sector_group': sector_group,
        'market_cap_bn': round(info.get('marketCap', 0) / 1e9, 1),
        'revenue_bn': round(revenue_bn, 1),
        'scope1_tonnes': scope1, 'scope2_tonnes': scope2,
        'scope2_location_based': scope2_location,
        'intensity_s12': round(intensity_s12, 2),
        'scope3_multiplier': scope3_mult,
        'using_real_data': using_real_data,
        'emissions_source': emissions_source,
        'emissions_year': emissions_year,
        'emissions_notes': emissions_notes,
        'z_score': z_score, 'z_confidence': z_conf,
        'peer_data': peer_data, 'z_risk_label': z_to_risk_label(z_score),
        'green_revenue_pct': green_rev,
        'fossil_exposure': fossil_exp,
        'has_sbti_target': has_sbti, 'net_zero_year': nz_year, 'net_zero_status': net_zero_status,
        'paris_alignment': paris,
        'transition_risk_score': risk_score, 'transition_risk_label': risk_label,
        'climate_var': climate_var,
        'stranded_asset_signal': stranded,
        'classification': cls, 'classification_note': cls_note,
        'status_note': status_note,
        'iea_benchmark': IEA_2030_BENCHMARKS.get(sector),
    }


def get_stock_data(ticker: str) -> dict:
    info = yf.Ticker(ticker.upper()).info
    return {
        'ticker': ticker.upper(), 'name': info.get('longName', 'Unknown'),
        'sector': info.get('sector', 'Unknown'), 'market_cap': info.get('marketCap', 0),
    }


# =============================================================================
# SECTION 11: CLI OUTPUT
# =============================================================================

def _print_report(f: dict):
    w = 82
    print("\n" + "=" * w)
    print(f"  CLIMATE RISK REPORT: {f['ticker']} — {f['company']}")
    print("=" * w)
    print(f"  Sector: {f['sector']} | Revenue: ${f['revenue_bn']}B | MCap: ${f['market_cap_bn']}B")
    print(f"\n  ▶ {f['classification']}")
    print(f"    {f['classification_note']}")

    print(f"\n  EMISSIONS  ({'real data' if f['using_real_data'] else 'industry proxy'})")
    if f['scope1_tonnes']:
        print(f"  ├─ Scope 1          : {f['scope1_tonnes']:>15,.0f} tCO2e/yr")
        print(f"  ├─ Scope 2 (market) : {f['scope2_tonnes']:>15,.0f} tCO2e/yr")
        if f['scope2_location_based']:
            print(f"  ├─ Scope 2 (location): {f['scope2_location_based']:>14,.0f} tCO2e/yr  [grid before RECs]")
    print(f"  ├─ Scope 1+2 Intensity: {f['intensity_s12']:>10.2f} tCO2e/$M revenue")
    print(f"  ├─ Scope 3 Mult     : {f['scope3_multiplier']}x")
    print(f"  ├─ Green Revenue    : {f['green_revenue_pct']}%  |  Fossil Exposure: {f['fossil_exposure']}")
    print(f"  └─ Source: {f['emissions_source']} ({f['emissions_year']})")
    if f['emissions_notes']:
        print(f"     Note: {f['emissions_notes']}")

    if f['z_score'] is not None:
        print(f"\n  PEER BENCHMARKING  ({f['sector_group']}, Scope 1+2 market-based)")
        print(f"  ├─ Z-Score: {f['z_score']:+.2f}  →  {f['z_risk_label']} relative to peers")
        for peer, val in sorted(f['peer_data'].items(), key=lambda x: x[1]):
            marker = '  ◀' if peer == f['ticker'] else ''
            print(f"  │    {peer:<6}: {val:>8.2f} tCO2/$M{marker}")

    pa = f['paris_alignment']
    print(f"\n  PARIS ALIGNMENT  (SBTi Sectoral Decarbonization Approach)")
    print(f"  ├─ {pa['label']}")
    print(f"  ├─ 1.5°C budget: {pa['budget_1_5c']} | 2°C budget: {pa['budget_2c']} tCO2/$M")
    print(f"  └─ {pa['note']}")

    print(f"\n  TRANSITION RISK: {f['transition_risk_score']}/100  ({f['transition_risk_label']})")
    print(f"  SBTi: {'Yes' if f['has_sbti_target'] else 'No'}  |  Net-Zero: {f['net_zero_year'] or 'uncommitted'}")

    print(f"\n  CLIMATE VaR  (% EBIT at risk from carbon pricing)")
    print(f"  {'Scenario':<35} {'$/t':>5}  {'S1+2':>7}  {'Full-scope':>10}")
    print(f"  {'-'*35} {'-'*5}  {'-'*7}  {'-'*10}")
    for v in f['climate_var'].values():
        print(f"  {v['label']:<35} {v['carbon_price']:>4}  {v['scope12_var_pct']:>6.1f}%  {v['full_scope_var_pct']:>9.1f}%")

    print(f"\n  STRANDED ASSET: {f['stranded_asset_signal']}")
    print(f"\n  STATUS NOTE: {f['status_note']}")
    print("=" * w)


if __name__ == "__main__":
    print(f"Climate Factor Analyzer v3.0  |  {datetime.now().strftime('%Y-%m-%d')}\n")
    for ticker in ['TSLA', 'XOM', 'MC.PA', 'NEE', 'F', 'MSFT']:
        try:
            _print_report(calculate_climate_factors(ticker))
        except Exception as e:
            print(f"\nERROR {ticker}: {e}")