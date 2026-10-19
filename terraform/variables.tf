variable "aws_region" {
  description = "AWS region for the S3 bucket and ECR repository."
  type        = string
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "vod"
}

variable "bucket_name" {
  description = "Globally unique S3 bucket name for video files."
  type        = string
}

variable "s3_prefix" {
  description = "Key prefix the app writes under (must match the S3_PREFIX setting)."
  type        = string
  default     = "videos"
}

variable "cloudfront_price_class" {
  description = "PriceClass_100 = US/EU edge locations only (cheapest); PriceClass_All = global."
  type        = string
  default     = "PriceClass_100"
}
