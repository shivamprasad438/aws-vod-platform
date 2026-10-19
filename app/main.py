"""Video-on-Demand API: upload a video, package it as HLS, serve metadata and playback URLs."""
import logging
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from .config import Settings, get_settings
from .db import VideoDB
from .storage import get_storage
from .transcode import TranscodeError, build_hls, probe

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("vod")

HTTP_REQUESTS = Counter("vod_http_requests_total", "HTTP requests", ["method", "path", "status"])
VIDEOS_PROCESSED = Counter("vod_videos_processed_total", "Videos processed", ["result"])
PROCESSING_SECONDS = Histogram(
    "vod_processing_seconds", "Time spent probing, packaging and publishing a video",
    buckets=(1, 5, 15, 30, 60, 120, 300, 600),
)
CHUNK = 1024 * 1024


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    db = VideoDB(settings.db_path)
    storage = get_storage(settings)
    work_dir = Path(settings.data_dir) / "work"
    work_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(title="AWS VOD Platform", version="1.0.0")

    @app.middleware("http")
    async def count_requests(request: Request, call_next):
        response = await call_next(request)
        route = request.scope.get("route")
        path = route.path if route else "unmatched"  # avoids high-cardinality labels
        HTTP_REQUESTS.labels(request.method, path, str(response.status_code)).inc()
        return response

    @app.get("/health")
    def health():
        """Liveness probe: the process is up."""
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        """Readiness probe: the metadata store is reachable."""
        try:
            db.ping()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")
        return {"status": "ready"}

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.post("/videos", status_code=202)
    async def upload_video(
        background: BackgroundTasks,
        file: UploadFile = File(...),
        title: str = Form(...),
    ):
        video_id = uuid.uuid4().hex[:12]
        upload_dir = work_dir / video_id
        upload_dir.mkdir(parents=True)
        source = upload_dir / "source"
        limit = settings.max_upload_mb * CHUNK
        written = 0
        with source.open("wb") as out:
            while chunk := await file.read(CHUNK):
                written += len(chunk)
                if written > limit:
                    out.close()
                    shutil.rmtree(upload_dir, ignore_errors=True)
                    raise HTTPException(413, f"file larger than {settings.max_upload_mb} MB")
                out.write(chunk)
        if written == 0:
            shutil.rmtree(upload_dir, ignore_errors=True)
            raise HTTPException(400, "empty file")

        db.insert(video_id, title, file.filename or "", datetime.now(timezone.utc).isoformat())
        background.add_task(process_video, video_id, upload_dir, source)
        return {"id": video_id, "status": "processing"}

    def process_video(video_id: str, upload_dir: Path, source: Path) -> None:
        started = time.monotonic()
        try:
            metadata = probe(source)
            hls_dir = upload_dir / "hls"
            renditions = build_hls(source, hls_dir, settings.hls_segment_seconds)
            storage.publish_directory(hls_dir, video_id)
            db.mark_ready(video_id, metadata, renditions, storage.playback_url(video_id))
            VIDEOS_PROCESSED.labels("ready").inc()
            log.info("video %s ready (%s)", video_id, ",".join(renditions))
        except (TranscodeError, OSError) as exc:
            db.mark_failed(video_id, str(exc))
            VIDEOS_PROCESSED.labels("failed").inc()
            log.error("video %s failed: %s", video_id, exc)
        except Exception as exc:  # noqa: BLE001 - never leave a video stuck in 'processing'
            db.mark_failed(video_id, f"unexpected error: {exc}")
            VIDEOS_PROCESSED.labels("failed").inc()
            log.exception("video %s crashed", video_id)
        finally:
            PROCESSING_SECONDS.observe(time.monotonic() - started)
            shutil.rmtree(upload_dir, ignore_errors=True)

    @app.get("/videos")
    def list_videos(limit: int = 50):
        return db.list(limit=min(max(limit, 1), 200))

    @app.get("/videos/{video_id}")
    def get_video(video_id: str):
        video = db.get(video_id)
        if video is None:
            raise HTTPException(404, "video not found")
        return video

    if settings.storage_backend == "local":
        # Serve published HLS files directly in local/dev mode.
        published = Path(settings.data_dir) / "published"
        app.mount("/media", StaticFiles(directory=str(published)), name="media")

    return app


app = create_app()
