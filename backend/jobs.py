"""DB-backed job worker. Every slow step runs here; HTTP requests only enqueue and poll."""

import logging
import threading
from typing import Any, Callable

import db

log = logging.getLogger("vre.jobs")

Handler = Callable[[dict[str, Any]], None]


class Worker:
    def __init__(self, handler: Handler, poll_seconds: float = 0.2):
        self._handler = handler
        self._poll = poll_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="vre-job-worker", daemon=True)

    def start(self) -> None:
        requeued = db.requeue_interrupted_jobs()
        if requeued:
            log.info("requeued %d interrupted job(s)", requeued)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            job = db.claim_next_job()
            if job is None:
                self._stop.wait(self._poll)
                continue
            try:
                self._handler(job)
            except Exception as exc:
                log.exception("job %s failed", job["id"])
                db.update_job(job["id"], status="failed", error=str(exc) or exc.__class__.__name__)
