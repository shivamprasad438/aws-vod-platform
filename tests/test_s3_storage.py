import boto3
from moto import mock_aws

from app.config import Settings
from app.storage import S3Storage


@mock_aws
def test_s3_publish_sets_content_type_cache_and_cloudfront_url(tmp_path, monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    s3 = boto3.client("s3", region_name="ap-south-1")
    s3.create_bucket(
        Bucket="test-vod", CreateBucketConfiguration={"LocationConstraint": "ap-south-1"}
    )

    (tmp_path / "hls" / "360p").mkdir(parents=True)
    (tmp_path / "hls" / "master.m3u8").write_text("#EXTM3U\n")
    (tmp_path / "hls" / "360p" / "seg_000.ts").write_bytes(b"\x47" * 188)

    storage = S3Storage(
        Settings(s3_bucket="test-vod", s3_prefix="videos", aws_region="ap-south-1",
                 cloudfront_domain="d111.cloudfront.net")
    )
    storage.publish_directory(tmp_path / "hls", "abc123")

    playlist = s3.head_object(Bucket="test-vod", Key="videos/abc123/master.m3u8")
    segment = s3.head_object(Bucket="test-vod", Key="videos/abc123/360p/seg_000.ts")
    assert playlist["ContentType"] == "application/vnd.apple.mpegurl"
    assert playlist["CacheControl"] == "max-age=60"
    assert segment["ContentType"] == "video/mp2t"
    assert "immutable" in segment["CacheControl"]
    assert storage.playback_url("abc123") == "https://d111.cloudfront.net/videos/abc123/master.m3u8"
