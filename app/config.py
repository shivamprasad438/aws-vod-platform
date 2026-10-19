"""Application settings, read from environment variables."""
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # "local" stores files on disk (dev/test); "s3" uploads to Amazon S3.
    storage_backend: str = os.getenv("STORAGE_BACKEND", "local")
    data_dir: str = os.getenv("DATA_DIR", "./data")
    db_path: str = os.getenv("DB_PATH", "./data/videos.db")
    s3_bucket: str = os.getenv("S3_BUCKET", "")
    s3_prefix: str = os.getenv("S3_PREFIX", "videos")
    aws_region: str = os.getenv("AWS_REGION", "ap-south-1")
    # CloudFront domain, e.g. d1234abcd.cloudfront.net (no scheme).
    cloudfront_domain: str = os.getenv("CLOUDFRONT_DOMAIN", "")
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "200"))
    hls_segment_seconds: int = int(os.getenv("HLS_SEGMENT_SECONDS", "6"))


def get_settings() -> Settings:
    return Settings()
