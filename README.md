# Shahpur Smart Job Finder Pro

A Streamlit job-intelligence app that combines a public job API with optional Apify-powered company career-page collection.

## Core features

- Live **Arbeitnow** job-feed connector
- Optional **Apify** career-page harvester
- Logistics / aviation / supply-chain keyword matching
- Priority-location scoring
- Visa / relocation text-signal detection
- Duplicate removal
- Direct apply links
- CSV export

## How this extends Shahpur Smart Job Finder

Shahpur Smart Job Finder Pro extends the original Shahpur Smart Job Finder with **company-owned career-page harvesting**, public job feeds, stronger matching, visa/relocation signals, duplicate removal and direct vacancy links.

## Optional Apify secrets

```toml
APIFY_TOKEN = "your-token"
APIFY_ACTOR_ID = "username/actor-name"
```

Do not commit secrets.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy

Deploy `app.py` from the repository root on Streamlit Community Cloud.

## Important

A sponsorship/relocation match is only a text signal. Always verify the official vacancy and employer requirements.
