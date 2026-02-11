terraform {
  required_version = ">= 1.4.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "current" {}

locals {
  repo_subjects = [
    for branch in var.github_branches :
    "repo:${var.github_repo}:ref:refs/heads/${branch}"
  ]

  ecr_repo_arns = [
    for repo in var.ecr_repositories :
    "arn:aws:ecr:${var.region}:${data.aws_caller_identity.current.account_id}:repository/${repo}"
  ]
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = var.github_oidc_thumbprints
}

data "aws_iam_policy_document" "github_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = local.repo_subjects
    }
  }
}

resource "aws_iam_role" "ecr" {
  name               = var.ecr_role_name
  assume_role_policy = data.aws_iam_policy_document.github_assume_role.json
  description        = "GitHub Actions role for ECR builds (repo: ${var.github_repo})."
}

data "aws_iam_policy_document" "ecr_policy" {
  statement {
    effect    = "Allow"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    effect = "Allow"
    actions = [
      "ecr:CreateRepository",
      "ecr:DescribeRepositories",
      "ecr:BatchCheckLayerAvailability",
      "ecr:CompleteLayerUpload",
      "ecr:InitiateLayerUpload",
      "ecr:PutImage",
      "ecr:UploadLayerPart",
    ]
    resources = local.ecr_repo_arns
  }
}

resource "aws_iam_policy" "ecr_policy" {
  name   = var.ecr_policy_name
  policy = data.aws_iam_policy_document.ecr_policy.json
}

resource "aws_iam_role_policy_attachment" "ecr_policy_attach" {
  role       = aws_iam_role.ecr.name
  policy_arn = aws_iam_policy.ecr_policy.arn
}

resource "aws_iam_role" "ui" {
  name               = var.ui_role_name
  assume_role_policy = data.aws_iam_policy_document.github_assume_role.json
  description        = "GitHub Actions role for UI deploy (repo: ${var.github_repo})."
}

data "aws_iam_policy_document" "ui_policy" {
  statement {
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = ["arn:aws:s3:::${var.ui_bucket_name}"]
  }

  statement {
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucketMultipartUploads",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["arn:aws:s3:::${var.ui_bucket_name}/*"]
  }

  statement {
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = ["arn:aws:cloudfront::${data.aws_caller_identity.current.account_id}:distribution/${var.ui_cloudfront_distribution_id}"]
  }
}

resource "aws_iam_policy" "ui_policy" {
  name   = var.ui_policy_name
  policy = data.aws_iam_policy_document.ui_policy.json
}

resource "aws_iam_role_policy_attachment" "ui_policy_attach" {
  role       = aws_iam_role.ui.name
  policy_arn = aws_iam_policy.ui_policy.arn
}
