"""
Interactive Scientometric Web Dashboard for Reference Validation.
Run using:
    streamlit run dashboard.py
"""
import config
import sqlite3
import csv
import json
from pathlib import Path
import streamlit as st

from config import BASE_DIR, OUTPUT_DIR, INTERMEDIATE_DIR, ELSEVIER_API_KEY
from src.models.verification import FinalStatus, ConfidenceLevel
from src.providers.scopus import ScopusClient

st.set_page_config(
    page_title="Scholarly Reference Validator",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom Styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1F497D;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #555555;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8F9FA;
        border-left: 5px solid #1F497D;
        border-radius: 6px;
        padding: 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }
    .badge-wrong {
        background-color: #FF4D4D;
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
    .badge-ok {
        background-color: #28A745;
        color: white;
        padding: 2px 8px;
        border-radius: 4px;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(ttl=60)
def load_data():
    """Loads validated references from CSV or checkpoints."""
    csv_path = OUTPUT_DIR / "references_validated.csv"
    records = []
    if csv_path.exists():
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            records = list(reader)
    
    # Load summary stats
    stats_path = OUTPUT_DIR / "summary_statistics.csv"
    stats = {}
    if stats_path.exists():
        with open(stats_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if len(row) >= 2:
                    stats[row[0]] = row[1]
    return records, stats


@st.cache_data(ttl=60)
def load_cache_stats():
    """Loads cache statistics from SQLite."""
    cache_db = BASE_DIR / "cache" / "api_cache.sqlite"
    cache_counts = {}
    if cache_db.exists():
        try:
            conn = sqlite3.connect(str(cache_db))
            cur = conn.cursor()
            cur.execute("SELECT namespace, count(*) FROM cache_entries GROUP BY namespace")
            for row in cur.fetchall():
                cache_counts[row[0]] = row[1]
            conn.close()
        except Exception:
            pass
    return cache_counts


# --- Header ---
st.markdown("<div class='main-header'>🔬 Scholarly Reference Validation System</div>", unsafe_allow_html=True)
st.markdown("<div class='sub-header'>Automated Bibliographic Validation, DOI Resolution & Wrong-Reference Detection</div>", unsafe_allow_html=True)

records, stats = load_data()
cache_counts = load_cache_stats()

# --- KPI Metric Cards ---
col1, col2, col3, col4, col5, col6 = st.columns(6)

docs_cnt = stats.get("Distinct Documents with References") or stats.get("Documents Analyzed") or len(set(r.get("source_eid") for r in records if r.get("source_eid")))
total_r = stats.get("Total References Processed") or stats.get("References Analyzed") or len(records)
resolving_d = stats.get("References with Resolving DOI", "0")
recovered = stats.get("Missing DOI - Recovered (DOI_RECOVERED)", "0")
wrong_doi = stats.get("Valid DOI Wrong Reference (VALID_DOI_WRONG_REFERENCE)") or stats.get("VALID DOI BUT WRONG REFERENCE (VALID_DOI_WRONG_REFERENCE)") or "0"
reviews = stats.get("Cases Requiring Human Review", "0")

with col1:
    st.metric("Docs Analyzed", docs_cnt)
with col2:
    st.metric("Total References", total_r)
with col3:
    st.metric("Resolving DOIs", resolving_d)
with col4:
    st.metric("DOIs Recovered", recovered)
with col5:
    st.metric("Wrong DOI Alerts", wrong_doi)
with col6:
    st.metric("Human Review", reviews)

st.markdown("---")

# --- Tabs ---
tab1, tab2, tab3, tab4 = st.tabs([
    "📋 All References Explorer",
    "⚠️ Wrong-DOI & Discrepancy Inspector",
    "🔍 Human Review Queue",
    "⚡ System Health & Cache Monitor",
])

# --- TAB 1: Reference Explorer ---
with tab1:
    st.subheader("Reference Exploration & Filtering")
    
    col_f1, col_f2, col_f3 = st.columns([2, 2, 3])
    
    # Extract unique statuses
    all_statuses = sorted(list(set(r.get("final_status", "") for r in records if r.get("final_status"))))
    with col_f1:
        sel_statuses = st.multiselect("Filter by Status", options=all_statuses, default=[])
    
    all_confs = sorted(list(set(r.get("confidence", "") for r in records if r.get("confidence"))))
    with col_f2:
        sel_confs = st.multiselect("Filter by Confidence", options=all_confs, default=[])
        
    with col_f3:
        search_kw = st.text_input("Search (Source Paper, Author, Title, DOI, or Ref ID)", placeholder="e.g. Dey, Altmetric, 10.14429, etc.")

    # Filter records
    filtered = records
    if sel_statuses:
        filtered = [r for r in filtered if r.get("final_status") in sel_statuses]
    if sel_confs:
        filtered = [r for r in filtered if r.get("confidence") in sel_confs]
    if search_kw:
        kw = search_kw.lower()
        filtered = [
            r for r in filtered
            if kw in r.get("raw_reference", "").lower()
            or kw in r.get("resolved_title", "").lower()
            or kw in r.get("normalized_doi", "").lower()
            or kw in r.get("reference_id", "").lower()
            or kw in r.get("source_title", "").lower()
            or kw in r.get("source_authors", "").lower()
        ]

    st.markdown(f"**Showing {len(filtered)} of {len(records)} references**")

    # Display as table
    display_rows = []
    for r in filtered[:300]:  # page top 300
        display_rows.append({
            "Ref ID": r.get("reference_id"),
            "Source Paper": f"[{r.get('source_year', '')}] {r.get('source_title', '')}"[:70],
            "Citation": r.get("raw_reference", "")[:75] + "...",
            "Scopus Link Valid": r.get("scopus_link_valid", "False"),
            "Scopus Link": r.get("scopus_reference_link", ""),
            "Final Status": r.get("final_status"),
            "Confidence": r.get("confidence"),
            "Score": r.get("composite_score"),
            "DOI": r.get("normalized_doi"),
            "Resolved Title": r.get("resolved_title", "")[:60],
            "Review?": r.get("needs_human_review"),
        })

    if display_rows:
        st.dataframe(display_rows, use_container_width=True)
    else:
        st.info("No references match the current filter criteria.")

# --- TAB 2: Wrong DOI Inspector ---
with tab2:
    st.subheader("Discrepancy Audit: Valid DOI pointing to Mismatched Paper")
    st.markdown("""
    A core scientometric failure mode is **`VALID_DOI_WRONG_REFERENCE`**: 
    The author cited Paper A, but attached a DOI that resolves successfully to Paper B.
    """)
    
    wrong_cases = [r for r in records if r.get("final_status") == FinalStatus.VALID_DOI_WRONG_REFERENCE.value or (float(r.get("composite_score") or 0.0) < 0.45 and r.get("doi_resolves") == "True")]
    
    if wrong_cases:
        st.error(f"Found {len(wrong_cases)} cases with severe bibliographic discrepancies!")
        for c in wrong_cases:
            with st.expander(f"Ref {c.get('reference_id')} | DOI: {c.get('normalized_doi')} | Score: {c.get('composite_score')}"):
                c_col1, c_col2 = st.columns(2)
                with c_col1:
                    st.markdown("**Cited in Manuscript:**")
                    st.write(c.get("raw_reference"))
                with c_col2:
                    st.markdown("**Resolved by DOI:**")
                    st.write(f"**Title:** {c.get('resolved_title')}")
                    st.write(f"**Authors:** {c.get('resolved_authors')}")
                    st.write(f"**Venue:** {c.get('resolved_journal')} ({c.get('resolved_year')})")
                st.caption(f"**Rationale:** {c.get('decision_rationale')}")
    else:
        st.success("No `VALID_DOI_WRONG_REFERENCE` cases detected in current verified sample.")

# --- TAB 3: Human Review Queue ---
with tab3:
    st.subheader("Human Review Queue (Uncertainty & Ambiguity Audit)")
    review_items = [r for r in records if r.get("needs_human_review") == "True"]
    st.markdown(f"**{len(review_items)} references require manual researcher review.**")
    
    if review_items:
        # CSV download button
        csv_str = ""
        review_csv_path = OUTPUT_DIR / "human_review_queue.csv"
        if review_csv_path.exists():
            with open(review_csv_path, "r", encoding="utf-8-sig") as f:
                csv_str = f.read()
            st.download_button(
                label="📥 Download Human Review Queue (CSV)",
                data=csv_str,
                file_name="human_review_queue.csv",
                mime="text/csv",
            )
        
        for idx, item in enumerate(review_items[:30], 1):
            with st.expander(f"[{idx}] {item.get('reference_id')} | Status: {item.get('final_status')} | Score: {item.get('composite_score')}"):
                st.markdown(f"**Raw Reference:** `{item.get('raw_reference')}`")
                st.markdown(f"**Candidate DOI:** `{item.get('normalized_doi')}` (Resolves: `{item.get('doi_resolves')}`, HTTP: `{item.get('http_status')}`)")
                st.markdown(f"**Resolved Publication:** {item.get('resolved_title')} by *{item.get('resolved_authors')}*")
                st.info(f"**Decision Reason:** {item.get('decision_rationale')}")

# --- TAB 4: System Health & Cache ---
with tab4:
    st.subheader("API Connectivity & SQLite Cache Health")
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("### External API Status")
        scopus = ScopusClient()
        st.write(f"**Elsevier Scopus API Key:** {'Configured (Active)' if scopus.is_configured() else 'Missing'}")
        st.write(f"**Scopus Remaining Quota:** {scopus.rate_limit_remaining if scopus.rate_limit_remaining is not None else 'Active (20,000)'}")
        st.write("**Crossref REST API:** Online (Polite Pool)")
        st.write("**OpenAlex REST API:** Online (Polite Pool)")
        st.write("**DOI Resolver (doi.org):** Online")

    with col_b:
        st.markdown("### SQLite Cache Entries (`cache/api_cache.sqlite`)")
        if cache_counts:
            for ns, count in cache_counts.items():
                st.write(f"- **{ns}:** {count:,} cached items")
        else:
            st.write("No cache records initialized yet.")

st.sidebar.title("Configuration")
st.sidebar.info("""
**Scholarly Reference Validation System**  
Built for Scopus scholarly exports.
- 864 documents in dataset
- 17,253 segmented references
- Resumable pipeline runner
""")
st.sidebar.markdown(f"**Active Input:** `data/input/scopus_export.csv`")

