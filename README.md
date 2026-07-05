# 🤖 AI-TalentScout

An AI-powered LinkedIn candidate screening and talent pipeline tool. Upload a CSV of LinkedIn profile URLs, define your Ideal Candidate Profile (ICP), and let the system scrape profiles, score candidates 0–100 with LLM reasoning, generate personalized outreach emails, and export results to Excel — fully automated.

---

## Features

- 🔗 **CSV-based LinkedIn URL ingestion** — paste your prospect list, get it validated and cleaned automatically
- 🕵️ **Live LinkedIn profile scraping** via [Apify](https://apify.com/) (`anchor~linkedin-profile-enrichment` actor) or a self-hosted Playwright scraper (`li_scraper/`)
- 🧠 **LLM-based candidate evaluation** — one OpenAI GPT call per candidate, scored against 7 recruitment dimensions
- 📊 **ICP matching** — define an Ideal Candidate Profile URL; the system fetches and uses it as the evaluation benchmark
- 📬 **Personalized outreach email generation** — auto-drafted per candidate based on their actual profile details
- 📁 **Persistent Excel export** — all evaluations appended to `evaluations/master_evaluations.xlsx`
- ⚡ **Fully async & parallel** — all Apify calls and LLM evaluations run simultaneously with `asyncio.gather`
- 🖥️ **Single-page frontend UI** — built with vanilla HTML/JS/CSS, no framework required
- 🧪 **Mock mode** — test the pipeline without live API calls by injecting raw JSON

---

## Quick Start

### 1. Clone the repo

```bash
git clone https://github.com/nahid0-0/AI-TalentScout.git
cd AI-TalentScout
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your real credentials:

| Variable | Required | Description |
|---|---|---|
| `APIFY_API_TOKEN` | ✅ | Your Apify API token — get it from [apify.com/account](https://apify.com/account) |
| `APIFY_ACTOR_ID` | ✅ | Apify actor to use (default: `anchor~linkedin-profile-enrichment`) |
| `OPENAI_API_KEY` | ✅ | OpenAI API key for GPT-based candidate evaluation |
| `OPENAI_MODEL` | ✅ | Model name (e.g. `gpt-4o-mini`, `gpt-5.4-mini`) |
| `SCRAPINGDOG_API_KEY` | Optional | Alternative scraping provider key |

### 5. Run the server

```bash
uvicorn main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000) in your browser.

---

## How It Works

```
CSV Upload (LinkedIn URLs)
         │
         ▼
  URL Validation & Cleaning
         │
         ▼
  Parallel Apify Scraping ──── OR ──── Mock JSON Input
  (one call per profile)
         │
         ▼
  Profile Cleaning & Trajectory Analysis
  (tenure flags, title inflation, sparse About detection)
         │
         ▼
  Parallel LLM Evaluation (OpenAI GPT)
  (one call per candidate, scored against ICP)
         │
         ▼
  Score / Status / Justification / Outreach Email
         │
         ▼
  Append to master_evaluations.xlsx
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Serves the main frontend UI |
| `POST` | `/run-pipeline` | Ingest CSV + ICP URL, scrape profiles, return cleaned data |
| `POST` | `/evaluate-candidates` | Score candidates against ICP via LLM, save to Excel |
| `GET` | `/download-master-excel` | Download the persistent evaluation spreadsheet |

### `POST /run-pipeline`

**Form fields:**
- `csv_file` — CSV file with one LinkedIn URL per row
- `icp_description` — LinkedIn URL of the Ideal Candidate Profile
- `fetch_profiles` — `true` to trigger live Apify scraping, `false` to skip
- `mock_json` — raw JSON array of profiles (bypasses Apify entirely — for testing)

### `POST /evaluate-candidates`

**JSON body:**
```json
{
  "icp_data": { ... },
  "candidates_data": [ { ... }, ... ],
  "threshold": 75
}
```

Returns scores, justifications, outreach emails, and `Qualified` / `Rejected` status per candidate.

---

## Self-Hosted LinkedIn Scraper (`li_scraper/`)

A local Playwright-based alternative to Apify — your cookies never leave your machine.

```bash
cd li_scraper
pip install -r requirements.txt
playwright install chromium
```

Add your session cookies to `li_scraper/cookies.json` (export from browser), then:

```bash
uvicorn main:app --reload --port 8001
```

> ⚠️ `li_scraper/cookies.json` is gitignored — never commit it. See [`li_scraper/README.md`](li_scraper/README.md) for full usage.

---

## Project Structure

```
.
├── main.py                     # FastAPI app — pipeline + evaluation endpoints
├── index.html                  # Single-page frontend UI
├── styles.css                  # Frontend styling
├── requirements.txt            # Python dependencies
├── .env.example                # Env variable template (copy to .env)
├── .gitignore                  # Excludes .env, venv, evaluations/, jsons/, cookies
├── evaluations/                # gitignored — auto-generated Excel outputs
│   └── master_evaluations.xlsx
├── jsons/                      # gitignored — sample/test profile JSONs
├── li_scraper/                 # Self-hosted Playwright scraper module
│   ├── main.py                 # FastAPI app for scraper
│   ├── scraper.py              # Playwright scraping logic
│   ├── models.py               # Pydantic models
│   ├── requirements.txt        # Scraper-specific dependencies
│   ├── cookies.json            # gitignored — your LinkedIn session cookies
│   └── README.md               # Scraper-specific setup docs
└── combined_mock.json          # gitignored — mock profile dataset for testing
```

---

## Environment & Security

- 🔒 **`.env` is gitignored** — real API keys are never committed
- 🍪 **`li_scraper/cookies.json` is gitignored** — your LinkedIn session stays local
- 📁 **`evaluations/` is gitignored** — Excel files contain real candidate data
- Use `.env.example` as a safe template to share required variable names

---

## Requirements

```
fastapi
uvicorn[standard]
httpx
pydantic
python-dotenv
openpyxl
```

---

## License

MIT
