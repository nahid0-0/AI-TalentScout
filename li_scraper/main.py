import logging
import uuid

from fastapi import FastAPI, HTTPException, BackgroundTasks

from models import ScrapeRequest, JobResponse, JobResult, JobStatus
from scraper import run_scrape_job, CircuitBreakerTripped

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("li_scraper")

app = FastAPI(title="LinkedIn Profile Scraper", version="0.1.0")

# In-memory job store. Fine for a single-process local tool;
# swap for Redis/DB if this ever needs to survive restarts or scale.
JOBS: dict[str, JobResult] = {}


@app.post("/scrape", response_model=JobResponse)
async def start_scrape(req: ScrapeRequest, background_tasks: BackgroundTasks):
    if req.min_wait_seconds > req.max_wait_seconds:
        raise HTTPException(400, "min_wait_seconds cannot exceed max_wait_seconds")
    if len(req.profile_urls) == 0:
        raise HTTPException(400, "profile_urls cannot be empty")
    if len(req.profile_urls) > 20:
        # Soft cap matching the volume ceiling already agreed on for this run.
        raise HTTPException(400, "Refusing to queue more than 20 profiles in a single job")

    job_id = str(uuid.uuid4())
    JOBS[job_id] = JobResult(
        job_id=job_id,
        status=JobStatus.pending,
        total_requested=len(req.profile_urls),
        completed=0,
        results=[],
    )

    background_tasks.add_task(
        _execute_job, job_id, req.profile_urls, req.min_wait_seconds, req.max_wait_seconds
    )
    return JobResponse(job_id=job_id, status=JobStatus.pending)


async def _execute_job(job_id: str, urls: list[str], min_wait: int, max_wait: int):
    job = JOBS[job_id]
    job.status = JobStatus.running

    async def on_result(result):
        job.results.append(result)
        job.completed += 1

    try:
        await run_scrape_job(urls, min_wait, max_wait, on_result=on_result)
        job.status = JobStatus.completed
    except CircuitBreakerTripped as e:
        job.status = JobStatus.stopped
        job.message = str(e)
    except FileNotFoundError as e:
        job.status = JobStatus.failed
        job.message = str(e)
    except Exception as e:
        logger.exception("Job failed")
        job.status = JobStatus.failed
        job.message = str(e)


@app.get("/scrape/{job_id}", response_model=JobResult)
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/health")
async def health():
    return {"status": "ok"}
