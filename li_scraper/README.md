# LinkedIn Profile Scraper (self-hosted, FastAPI + Playwright)

Self-hosted replacement for the Apify actor — your cookies never leave your machine.

## Setup

```bash
cd li_scraper
python3 -m venv venv
source venv/bin/activate          # Mac/Linux
pip install -r requirements.txt
playwright install chromium
```

## Add your cookies

Create `cookies.json` in this folder (same format as your browser extension export —
the one with `name`, `value`, `domain`, etc. per cookie). This file is gitignored-by-convention;
do not commit it or send it anywhere.

```bash
# create the file, then paste your cookie JSON array into it
nano cookies.json
```

## Run the API

```bash
uvicorn main:app --reload --port 8000
```

## Use it

Start a scrape job:

```bash
curl -X POST http://localhost:8000/scrape \
  -H "Content-Type: application/json" \
  -d '{
    "profile_urls": ["https://www.linkedin.com/in/nahid-rahman-7a420324a/"],
    "min_wait_seconds": 15,
    "max_wait_seconds": 60
  }'
```

Response:
```json
{ "job_id": "xxxx-xxxx", "status": "pending" }
```

Poll for results:

```bash
curl http://localhost:8000/scrape/xxxx-xxxx
```

## Notes / things to know

- **Sequential, not concurrent** — one profile at a time, randomized delay (15-60s default)
  between each, deliberately mimicking human browsing pace.
- **Circuit breaker** — if LinkedIn redirects to a login wall or checkpoint page mid-run,
  the job stops immediately (status: `stopped`) instead of continuing to hammer a
  flagged/logged-out session.
- **20-profile cap per job** — hardcoded in `main.py`, matching the volume ceiling already
  agreed for this run. Raise it if you need to, but know LinkedIn's own stated safe ceiling
  is ~300-400/day across an entire account.
- **Selectors will break** — LinkedIn's HTML classes are hashed/obfuscated and change
  periodically. `scraper.py` targets relatively stable structural landmarks (`h1`, `section#about`,
  etc.) but expect to need touch-ups over time. This is true of any scraper, including
  the Apify actor — it's not unique to this build.
- **Account risk is still real** — this is your own personal `li_at` session driving the
  requests. Self-hosting keeps the cookie off third-party servers, but it does not make
  LinkedIn's bot detection go away. Keep the delays, keep the volume low.
