resource "random_id" "ui_bucket_suffix" {
  byte_length = 4
}

locals {
  ui_bucket_name = var.ui_bucket_name != "" ? var.ui_bucket_name : "ai-training-ui-${random_id.ui_bucket_suffix.hex}"
  ui_domain_names = length(var.ui_domain_names) > 0 ? var.ui_domain_names : (
    var.ui_domain_name != "" ? [var.ui_domain_name] : []
  )
  ui_has_domain  = length(local.ui_domain_names) > 0 && var.ui_hosted_zone_id != ""
  api_has_domain = var.api_domain_name != "" && var.api_hosted_zone_id != ""
}

resource "aws_s3_bucket" "ui" {
  bucket = local.ui_bucket_name
}

resource "aws_s3_bucket_public_access_block" "ui" {
  bucket                  = aws_s3_bucket.ui.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "ui" {
  bucket = aws_s3_bucket.ui.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_versioning" "ui" {
  bucket = aws_s3_bucket.ui.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ui" {
  bucket = aws_s3_bucket.ui.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_cloudfront_origin_access_control" "ui" {
  name                              = "ai-training-ui-oac"
  description                       = "OAC for UI S3 bucket"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_acm_certificate" "ui" {
  count             = local.ui_has_domain ? 1 : 0
  provider          = aws.us_east_1
  domain_name       = local.ui_domain_names[0]
  subject_alternative_names = length(local.ui_domain_names) > 1 ? slice(local.ui_domain_names, 1, length(local.ui_domain_names)) : []
  validation_method = "DNS"
}

resource "aws_route53_record" "ui_cert_validation" {
  for_each = local.ui_has_domain ? {
    for dvo in aws_acm_certificate.ui[0].domain_validation_options : dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  } : {}

  zone_id = var.ui_hosted_zone_id
  name    = each.value.name
  type    = each.value.type
  records = [each.value.record]
  ttl     = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "ui" {
  count                   = local.ui_has_domain ? 1 : 0
  provider                = aws.us_east_1
  certificate_arn         = aws_acm_certificate.ui[0].arn
  validation_record_fqdns = [for record in aws_route53_record.ui_cert_validation : record.fqdn]
}

resource "aws_cloudfront_distribution" "ui" {
  enabled             = true
  default_root_object = "index.html"
  price_class         = var.ui_cloudfront_price_class
  aliases             = local.ui_has_domain ? local.ui_domain_names : []

  origin {
    domain_name              = aws_s3_bucket.ui.bucket_regional_domain_name
    origin_id                = "ui-s3-origin"
    origin_access_control_id = aws_cloudfront_origin_access_control.ui.id
  }

  default_cache_behavior {
    allowed_methods  = ["GET", "HEAD", "OPTIONS"]
    cached_methods   = ["GET", "HEAD", "OPTIONS"]
    target_origin_id = "ui-s3-origin"
    viewer_protocol_policy = "redirect-to-https"
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
    compress               = true
  }

  custom_error_response {
    error_code            = 403
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  custom_error_response {
    error_code            = 404
    response_code         = 200
    response_page_path    = "/index.html"
    error_caching_min_ttl = 0
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  dynamic "viewer_certificate" {
    for_each = local.ui_has_domain ? [1] : []
    content {
      acm_certificate_arn      = aws_acm_certificate_validation.ui[0].certificate_arn
      ssl_support_method       = "sni-only"
      minimum_protocol_version = "TLSv1.2_2021"
    }
  }

  dynamic "viewer_certificate" {
    for_each = local.ui_has_domain ? [] : [1]
    content {
      cloudfront_default_certificate = true
    }
  }
}

data "aws_iam_policy_document" "ui_bucket" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.ui.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.ui.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "ui" {
  bucket = aws_s3_bucket.ui.id
  policy = data.aws_iam_policy_document.ui_bucket.json
}

resource "aws_route53_record" "ui_alias_a" {
  for_each = local.ui_has_domain ? { for name in local.ui_domain_names : name => name } : {}
  zone_id = var.ui_hosted_zone_id
  name    = each.value
  type    = "A"
  alias {
    name                   = aws_cloudfront_distribution.ui.domain_name
    zone_id                = aws_cloudfront_distribution.ui.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "ui_alias_aaaa" {
  for_each = local.ui_has_domain ? { for name in local.ui_domain_names : name => name } : {}
  zone_id = var.ui_hosted_zone_id
  name    = each.value
  type    = "AAAA"
  alias {
    name                   = aws_cloudfront_distribution.ui.domain_name
    zone_id                = aws_cloudfront_distribution.ui.hosted_zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "api_alias_a" {
  count   = local.api_has_domain ? 1 : 0
  zone_id = var.api_hosted_zone_id
  name    = var.api_domain_name
  type    = "A"
  alias {
    name                   = aws_lb.control_plane.dns_name
    zone_id                = aws_lb.control_plane.zone_id
    evaluate_target_health = false
  }
}

resource "aws_route53_record" "api_alias_aaaa" {
  count   = local.api_has_domain ? 1 : 0
  zone_id = var.api_hosted_zone_id
  name    = var.api_domain_name
  type    = "AAAA"
  alias {
    name                   = aws_lb.control_plane.dns_name
    zone_id                = aws_lb.control_plane.zone_id
    evaluate_target_health = false
  }
}
