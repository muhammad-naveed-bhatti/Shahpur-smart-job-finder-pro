from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parent
SAMPLE = ROOT / "data" / "sample_jobs.csv"

st.set_page_config(
    page_title="Shahpur Smart Job Finder Pro",
    page_icon="🧭",
    layout="wide",
)

st.markdown(
    """
<style>
.block-container{padding-top:1.5rem;padding-bottom:2.5rem}
[data-testid="stMetric"]{border:1px solid #2a3447;border-radius:14px;padding:12px 14px;background:#151d2e}
.pill{border:1px solid #2a3447;border-radius:999px;padding:4px 9px;display:inline-block;margin:0 6px 6px 0;font-size:.78rem}
</style>
""",
    unsafe_allow_html=True,
)

DEFAULT_KEYWORDS = [
    "logistics", "supply chain", "warehouse", "inventory", "procurement",
    "aviation", "aircraft", "spares", "materials", "stores", "operations",
    "material control", "planning", "mro", "freight", "cargo",
]

SPONSOR_TERMS = [
    "visa sponsorship", "sponsorship available", "work visa", "relocation support",
    "relocation assistance", "employer sponsored", "sponsor visa",
]

PRIORITY_LOCATIONS = [
    "lahore", "sheikhupura", "gujranwala", "sialkot",
    "dubai", "abu dhabi", "sharjah", "doha", "riyadh", "jeddah",
]

def clean_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "").replace("&nbsp;", " ")

def normalize_space(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()

@st.cache_data
def load_sample() -> pd.DataFrame:
    return pd.read_csv(SAMPLE)

@st.cache_data(ttl=1800)
def fetch_arbeitnow(page: int = 1) -> pd.DataFrame:
    r = requests.get("https://www.arbeitnow.com/api/job-board-api", params={"page":page}, timeout=20)
    r.raise_for_status()
    payload = r.json()
    rows = []
    for item in payload.get("data", []):
        rows.append({
            "source":"Arbeitnow",
            "source_id":item.get("slug",""),
            "company":normalize_space(item.get("company_name","")),
            "title":normalize_space(item.get("title","")),
            "location":normalize_space(item.get("location","")),
            "remote":bool(item.get("remote",False)),
            "description":normalize_space(clean_html(item.get("description",""))),
            "apply_url":item.get("url",""),
            "tags":", ".join(item.get("tags") or []),
            "published_date":item.get("created_at",""),
        })
    return pd.DataFrame(rows)

def make_uid(row: pd.Series) -> str:
    raw = "|".join([
        normalize_space(row.get("company")).lower(),
        normalize_space(row.get("title")).lower(),
        normalize_space(row.get("location")).lower(),
        normalize_space(row.get("apply_url")).lower(),
    ])
    return hashlib.sha1(raw.encode("utf-8","ignore")).hexdigest()[:14]

def score_jobs(df: pd.DataFrame, keywords: list[str]) -> pd.DataFrame:
    out = df.copy()
    for col in ["source","source_id","company","title","location","description","apply_url","tags","published_date"]:
        if col not in out.columns:
            out[col] = ""
    if "remote" not in out.columns:
        out["remote"] = False

    haystack = (
        out["title"].fillna("").astype(str) + " " +
        out["description"].fillna("").astype(str) + " " +
        out["tags"].fillna("").astype(str) + " " +
        out["location"].fillna("").astype(str)
    ).str.lower()

    out["keyword_hits"] = haystack.apply(lambda s: sum(1 for k in keywords if k.lower() in s))
    out["sponsor_signal"] = haystack.apply(lambda s: any(term in s for term in SPONSOR_TERMS))
    out["priority_location"] = out["location"].fillna("").astype(str).str.lower().apply(
        lambda s: any(loc in s for loc in PRIORITY_LOCATIONS)
    )

    base = (out["keyword_hits"].clip(0,8) / 8 * 80)
    sponsor_bonus = out["sponsor_signal"].astype(int) * 12
    priority_bonus = out["priority_location"].astype(int) * 8
    out["match_score"] = (base + sponsor_bonus + priority_bonus).clip(0,100).round(0)
    out["uid"] = out.apply(make_uid, axis=1)
    out = out.drop_duplicates(subset=["uid"], keep="first")
    return out

def secret(key: str) -> str:
    try:
        return str(st.secrets.get(key,""))
    except Exception:
        return ""

def run_apify(actor_id: str, token: str, run_input: dict[str,Any], max_items: int) -> pd.DataFrame:
    actor = actor_id.replace("/","~")
    r = requests.post(
        f"https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items",
        headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"},
        params={"clean":"true","format":"json","maxItems":max_items,"timeout":120},
        json=run_input,
        timeout=135,
    )
    r.raise_for_status()
    payload = r.json()
    items = payload if isinstance(payload,list) else payload.get("items",[])
    return pd.json_normalize(items)

st.title("🧭 Shahpur Smart Job Finder Pro")
st.caption("Advanced company career-page harvesting + public job feeds + logistics-focused matching.")
st.markdown(
    '<span class="pill">Arbeitnow API</span><span class="pill">Apify-ready</span>'
    '<span class="pill">Match scoring</span><span class="pill">Duplicate removal</span>'
    '<span class="pill">Direct apply links</span>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Sources")
    use_sample = st.checkbox("Sample jobs", value=True)
    use_arbeitnow = st.checkbox("Live Arbeitnow", value=False)
    pages = st.slider("Arbeitnow pages", 1, 3, 1)
    st.divider()
    st.header("Targeting")
    keywords_text = st.text_area(
        "Keywords",
        value=", ".join(DEFAULT_KEYWORDS),
        height=120,
    )
    min_score = st.slider("Minimum match score", 0, 100, 20, 5)
    remote_only = st.toggle("Remote only", value=False)
    sponsor_only = st.toggle("Visa / relocation signal only", value=False)
    priority_only = st.toggle("Priority locations only", value=False)

frames = []
if use_sample:
    frames.append(load_sample())

if use_arbeitnow:
    for p in range(1, pages + 1):
        try:
            frames.append(fetch_arbeitnow(p))
        except Exception as exc:
            st.warning(f"Arbeitnow page {p} unavailable: {exc}")
            break

if not frames:
    st.info("Select at least one source.")
    st.stop()

keywords = [k.strip().lower() for k in keywords_text.split(",") if k.strip()]
df = score_jobs(pd.concat(frames, ignore_index=True, sort=False), keywords)

mask = df["match_score"] >= min_score
if remote_only:
    mask &= df["remote"].fillna(False).astype(bool)
if sponsor_only:
    mask &= df["sponsor_signal"]
if priority_only:
    mask &= df["priority_location"]

view = df.loc[mask].sort_values(
    by=["match_score","priority_location","sponsor_signal"],
    ascending=[False,False,False],
).reset_index(drop=True)

m1,m2,m3,m4 = st.columns(4)
m1.metric("Matching jobs", len(view))
m2.metric("Companies", view["company"].replace("",pd.NA).nunique())
m3.metric("Visa/relocation signals", int(view["sponsor_signal"].sum()) if len(view) else 0)
m4.metric("Priority-location jobs", int(view["priority_location"].sum()) if len(view) else 0)

tab1,tab2,tab3,tab4 = st.tabs(["Job intelligence","Career-page collector","Export","About"])

with tab1:
    st.subheader("Ranked job opportunities")
    if view.empty:
        st.info("No jobs match the current filters.")
    else:
        cols = [
            "match_score","company","title","location","remote","sponsor_signal",
            "priority_location","source","published_date","apply_url"
        ]
        st.dataframe(
            view[cols],
            use_container_width=True,
            hide_index=True,
            column_config={
                "match_score":st.column_config.ProgressColumn("Match",min_value=0,max_value=100,format="%.0f"),
                "apply_url":st.column_config.LinkColumn("Apply"),
            },
        )
        top = view.iloc[0]
        st.success(
            f"Top match: {top['title']} at {top['company']} — "
            f"{top['location']} — score {top['match_score']:.0f}/100."
        )

with tab2:
    st.subheader("Optional company career-page harvesting with Apify")
    st.write(
        "Use an Apify Actor to crawl selected company career pages. "
        "This keeps the app flexible instead of hard-coding one website structure."
    )
    actor_id = st.text_input("Actor ID", value=secret("APIFY_ACTOR_ID"), placeholder="username/actor-name")
    token = st.text_input("Apify token", value=secret("APIFY_TOKEN"), type="password")
    urls_text = st.text_area(
        "Company career/search URLs, one per line",
        placeholder="https://company.example/careers",
        height=130,
    )
    max_items = st.number_input("Maximum returned items",1,300,50)
    actor_input = {
        "startUrls":[{"url":u.strip()} for u in urls_text.splitlines() if u.strip()],
        "maxCrawlPages":int(max_items),
    }
    with st.expander("Actor input preview"):
        st.code(json.dumps(actor_input,indent=2),language="json")

    if st.button("Run career-page harvester", type="primary"):
        if not actor_id or not token:
            st.error("Actor ID and token are required.")
        elif not actor_input["startUrls"]:
            st.error("Add at least one company career URL.")
        else:
            try:
                with st.spinner("Running Actor…"):
                    live = run_apify(actor_id,token,actor_input,int(max_items))
                st.success(f"Collected {len(live)} item(s).")
                st.dataframe(live,use_container_width=True,hide_index=True)
                if not live.empty:
                    st.download_button(
                        "Download raw harvested jobs",
                        live.to_csv(index=False).encode("utf-8-sig"),
                        file_name=f"career_page_jobs_{date.today().isoformat()}.csv",
                        mime="text/csv",
                    )
            except Exception as exc:
                st.error(f"Apify run failed: {exc}")

with tab3:
    st.subheader("Export shortlist")
    export_cols = [
        "company","title","location","remote","match_score","sponsor_signal",
        "priority_location","source","published_date","apply_url"
    ]
    st.download_button(
        "Download filtered jobs (CSV)",
        view[export_cols].to_csv(index=False).encode("utf-8-sig"),
        file_name=f"career_job_shortlist_{date.today().isoformat()}.csv",
        mime="text/csv",
        disabled=view.empty,
    )
    st.caption("The export is designed for later application tracking or import into a job-application tracker.")

with tab4:
    st.markdown(
        """
### What this app demonstrates

- Public no-key **Arbeitnow** job-feed integration.
- Flexible **Apify** career-page harvesting for company-specific vacancies.
- Logistics / aviation / supply-chain keyword matching.
- Priority-location boosts.
- Visa / relocation keyword signals.
- Duplicate detection.
- Direct apply links and CSV export.

This app does not claim that a visa is guaranteed. Sponsorship/relocation is only a text signal and must be verified in the official vacancy.
        """
    )

st.divider()
st.caption("Portfolio demo by Muhammad Naveed · Logistics · Aviation · Supply Chain")
