# German Job Search Collector

Small Python and React MVP for collecting German job postings with JobSpy, showing results in a web table, and exporting a clean CSV.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Python 3.11 or 3.12 is recommended for deployment. Python 3.14 may fail to install JobSpy's pinned NumPy dependency.

## CLI Usage

```bash
python search_jobs.py "Energy Data Analyst"
python search_jobs.py "Energiedaten" --location "Munich, Germany" --hours-old 24
```

The CSV is written to:

```text
output/Energy_Data_Analyst.csv
```

## Configuration

Edit `config.yaml` to change sources and result limits:

```yaml
sources:
  - linkedin
  - indeed
  - stepstone

country: Germany

results_per_source: 100
```

JobSpy currently supports LinkedIn and Indeed, but not StepStone. If `stepstone` is configured, the script reports it as skipped rather than using an unrequested source.

## Web App

Install frontend dependencies:

```bash
cd frontend
npm install
cd ..
```

Run the backend:

```bash
uvicorn job_search.api:app --reload
```

Run the frontend in another terminal:

```bash
cd frontend
npm run dev
```

Open `http://127.0.0.1:5173`.

The web app supports:

- Keyword and location input
- Distance, freshness, and results-per-source controls
- LinkedIn and Indeed source selection
- StepStone shown as unavailable because JobSpy does not support it
- Async search status
- Results table
- CSV download

## API

- `POST /api/searches`
- `GET /api/searches/{job_id}`
- `GET /api/searches/{job_id}/results`
- `GET /api/searches/{job_id}/csv`
- `GET /api/sources`

## Docker

```bash
docker build -t german-job-search .
docker run --rm -p 8000:8000 german-job-search
```

Open `http://127.0.0.1:8000`.

## Output Columns

- `job_title`
- `company_name`
- `location`
- `posting_date`
- `job_url`
- `source_website`
- `employment_type`

Rows without an HTTP or HTTPS job URL are removed. Duplicate jobs are removed by `job_url`. Results are sorted by most recent posting date, then job title.

## Notes

This is an experiment, not a production application. Job boards can throttle or block scraping, and returned fields vary by source.
