output "bucket_name" {
  description = "Value for S3_BUCKET in k8s/configmap.yaml"
  value       = aws_s3_bucket.videos.bucket
}

output "cloudfront_domain" {
  description = "Value for CLOUDFRONT_DOMAIN in k8s/configmap.yaml"
  value       = aws_cloudfront_distribution.videos.domain_name
}

output "app_iam_policy_arn" {
  description = "Attach this policy to the IRSA role used by the API pod"
  value       = aws_iam_policy.app.arn
}

output "ecr_repository_url" {
  description = "Image repository for the API container"
  value       = aws_ecr_repository.api.repository_url
}
