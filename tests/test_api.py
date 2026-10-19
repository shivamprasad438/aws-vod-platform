import time

import pytest

from .conftest import HAS_FFMPEG

needs_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg not installed")


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}


def test_metrics_exposed(client):
    client.get("/health")
    body = client.get("/metrics").text
    assert "vod_http_requests_total" in body


def test_unknown_video_returns_404(client):
    assert client.get("/videos/doesnotexist").status_code == 404


def test_empty_upload_rejected(client):
    resp = client.post("/videos", data={"title": "x"}, files={"file": ("a.mp4", b"")})
    assert resp.status_code == 400


def test_oversized_upload_rejected(client):
    big = b"0" * (6 * 1024 * 1024)  # limit is 5 MB in tests
    resp = client.post("/videos", data={"title": "x"}, files={"file": ("a.mp4", big)})
    assert resp.status_code == 413


def _wait_for(client, video_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        video = client.get(f"/videos/{video_id}").json()
        if video["status"] != "processing":
            return video
        time.sleep(0.5)
    raise AssertionError("video still processing")


def test_invalid_file_marked_failed(client):
    resp = client.post("/videos", data={"title": "junk"}, files={"file": ("a.mp4", b"not a video")})
    assert resp.status_code == 202
    video = _wait_for(client, resp.json()["id"])
    assert video["status"] == "failed"
    assert video["error"]


@needs_ffmpeg
def test_upload_produces_hls_and_metadata(client, sample_video):
    with sample_video.open("rb") as f:
        resp = client.post("/videos", data={"title": "demo"}, files={"file": ("sample.mp4", f)})
    assert resp.status_code == 202
    video = _wait_for(client, resp.json()["id"])

    assert video["status"] == "ready", video.get("error")
    assert video["metadata"]["height"] == 360
    assert video["metadata"]["video_codec"] == "h264"
    assert video["renditions"] == ["360p"]  # source is 360p, so 720p is skipped (no upscaling)

    master = client.get(video["playback_url"])
    assert master.status_code == 200
    assert "#EXTM3U" in master.text
    assert "360p/index.m3u8" in master.text

    playlist = client.get(video["playback_url"].replace("master.m3u8", "360p/index.m3u8"))
    assert playlist.status_code == 200
    assert ".ts" in playlist.text

    listing = client.get("/videos").json()
    assert any(v["id"] == video["id"] for v in listing)
