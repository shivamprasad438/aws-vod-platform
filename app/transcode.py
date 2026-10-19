"""FFprobe metadata extraction and FFmpeg HLS packaging."""
import json
import subprocess
from pathlib import Path

# (name, height, video bitrate, audio bitrate)
RENDITIONS = [
    ("360p", 360, "800k", "96k"),
    ("720p", 720, "2500k", "128k"),
]


class TranscodeError(RuntimeError):
    pass


def probe(path: Path) -> dict:
    """Return duration, resolution and codecs of a video using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error", "-print_format", "json",
        "-show_format", "-show_streams", str(path),
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=60)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise TranscodeError(f"ffprobe failed: {exc}") from exc
    info = json.loads(out.stdout)
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise TranscodeError("file has no video stream")
    audio = next((s for s in info.get("streams", []) if s.get("codec_type") == "audio"), None)
    return {
        "duration_seconds": round(float(info["format"].get("duration", 0)), 2),
        "width": video.get("width"),
        "height": video.get("height"),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name") if audio else None,
        "size_bytes": int(info["format"].get("size", 0)),
    }


def build_hls(source: Path, out_dir: Path, segment_seconds: int = 6) -> list[str]:
    """Create one HLS rendition per entry in RENDITIONS plus a master playlist.

    Layout written to out_dir:
        master.m3u8
        360p/index.m3u8, 360p/seg_000.ts, ...
        720p/index.m3u8, 720p/seg_000.ts, ...
    Returns the names of the renditions that were produced.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    src_height = probe(source)["height"] or 0
    # Never upscale: skip renditions taller than the source (always keep the smallest).
    chosen = [r for r in RENDITIONS if r[1] <= src_height] or [RENDITIONS[0]]
    has_audio = probe(source)["audio_codec"] is not None

    produced = []
    for name, height, v_bitrate, a_bitrate in chosen:
        rdir = out_dir / name
        rdir.mkdir(exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-i", str(source),
            "-vf", f"scale=-2:{height}",
            "-c:v", "libx264", "-preset", "veryfast", "-b:v", v_bitrate,
            "-g", "48", "-keyint_min", "48", "-sc_threshold", "0",
        ]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", a_bitrate]
        else:
            cmd += ["-an"]
        cmd += [
            "-f", "hls", "-hls_time", str(segment_seconds),
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", str(rdir / "seg_%03d.ts"),
            str(rdir / "index.m3u8"),
        ]
        try:
            subprocess.run(cmd, capture_output=True, check=True, timeout=3600)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            detail = getattr(exc, "stderr", b"") or b""
            raise TranscodeError(f"ffmpeg failed for {name}: {detail[-300:]!r}") from exc
        produced.append(name)

    _write_master(out_dir, chosen, src_height)
    return produced


def _write_master(out_dir: Path, renditions, src_height: int) -> None:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for name, height, v_bitrate, a_bitrate in renditions:
        bandwidth = int(_kbps(v_bitrate) + _kbps(a_bitrate)) * 1000
        width = int(height * 16 / 9) // 2 * 2
        lines.append(f"#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={width}x{height}")
        lines.append(f"{name}/index.m3u8")
    (out_dir / "master.m3u8").write_text("\n".join(lines) + "\n")


def _kbps(value: str) -> float:
    return float(value.rstrip("k"))
