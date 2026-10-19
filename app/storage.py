"""Storage backends: local disk (dev/test) and Amazon S3 (production)."""
import mimetypes
from pathlib import Path

from .config import Settings

CONTENT_TYPES = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
}


class LocalStorage:
    def __init__(self, settings: Settings):
        self.root = Path(settings.data_dir) / "published"
        self.root.mkdir(parents=True, exist_ok=True)

    def publish_directory(self, local_dir: Path, key_prefix: str) -> None:
        dest = self.root / key_prefix
        dest.mkdir(parents=True, exist_ok=True)
        for path in local_dir.rglob("*"):
            if path.is_file():
                target = dest / path.relative_to(local_dir)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(path.read_bytes())

    def playback_url(self, key_prefix: str) -> str:
        return f"/media/{key_prefix}/master.m3u8"


class S3Storage:
    def __init__(self, settings: Settings):
        import boto3  # imported lazily so local runs do not need AWS config

        if not settings.s3_bucket:
            raise ValueError("S3_BUCKET must be set when STORAGE_BACKEND=s3")
        self.bucket = settings.s3_bucket
        self.prefix = settings.s3_prefix.strip("/")
        self.cloudfront_domain = settings.cloudfront_domain
        self.client = boto3.client("s3", region_name=settings.aws_region)

    def _key(self, key_prefix: str, relative: str) -> str:
        return "/".join(p for p in (self.prefix, key_prefix, relative) if p)

    def publish_directory(self, local_dir: Path, key_prefix: str) -> None:
        for path in local_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(local_dir).as_posix()
            content_type = CONTENT_TYPES.get(path.suffix) or (
                mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            )
            # Playlists are short-lived; segments never change, so cache them hard.
            cache = "max-age=60" if path.suffix == ".m3u8" else "max-age=31536000, immutable"
            self.client.upload_file(
                str(path), self.bucket, self._key(key_prefix, rel),
                ExtraArgs={"ContentType": content_type, "CacheControl": cache},
            )

    def playback_url(self, key_prefix: str) -> str:
        key = self._key(key_prefix, "master.m3u8")
        if self.cloudfront_domain:
            return f"https://{self.cloudfront_domain}/{key}"
        return f"https://{self.bucket}.s3.amazonaws.com/{key}"


def get_storage(settings: Settings):
    if settings.storage_backend == "s3":
        return S3Storage(settings)
    return LocalStorage(settings)
