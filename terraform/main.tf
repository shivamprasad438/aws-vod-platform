############################
# S3: private bucket for HLS playlists and segments
############################
resource "aws_s3_bucket" "videos" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "videos" {
  bucket                  = aws_s3_bucket.videos.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "videos" {
  bucket = aws_s3_bucket.videos.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "videos" {
  bucket = aws_s3_bucket.videos.id

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"

    filter {}

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

############################
# CloudFront: the only way viewers reach the bucket
############################
resource "aws_cloudfront_origin_access_control" "videos" {
  name                              = "${var.project_name}-oac"
  description                       = "Lets CloudFront read the private video bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_distribution" "videos" {
  enabled         = true
  comment         = "${var.project_name} VOD delivery"
  price_class     = var.cloudfront_price_class
  http_version    = "http2and3"
  is_ipv6_enabled = true

  origin {
    domain_name              = aws_s3_bucket.videos.bucket_regional_domain_name
    origin_id                = "s3-videos"
    origin_access_control_id = aws_cloudfront_origin_access_control.videos.id
  }

  default_cache_behavior {
    target_origin_id       = "s3-videos"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

# Allow only this CloudFront distribution to read objects from the bucket.
data "aws_iam_policy_document" "bucket_policy" {
  statement {
    sid       = "AllowCloudFrontRead"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.videos.arn}/*"]

    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.videos.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "videos" {
  bucket     = aws_s3_bucket.videos.id
  policy     = data.aws_iam_policy_document.bucket_policy.json
  depends_on = [aws_s3_bucket_public_access_block.videos]
}

############################
# IAM: least-privilege policy for the API pod (attach it to an IRSA role)
############################
data "aws_iam_policy_document" "app" {
  statement {
    sid       = "WriteVideoObjects"
    actions   = ["s3:PutObject", "s3:AbortMultipartUpload"]
    resources = ["${aws_s3_bucket.videos.arn}/${var.s3_prefix}/*"]
  }

  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.videos.arn]
  }
}

resource "aws_iam_policy" "app" {
  name        = "${var.project_name}-api-s3-write"
  description = "Allows the VOD API to publish HLS files to the video bucket"
  policy      = data.aws_iam_policy_document.app.json
}

############################
# ECR: container image repository
############################
resource "aws_ecr_repository" "api" {
  name                 = "${var.project_name}-api"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 20 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 20
      }
      action = { type = "expire" }
    }]
  })
}
