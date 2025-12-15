terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

# ----------------------------
# Variables (kept in this file so variables.tf is not needed)
# ----------------------------
variable "aws_region" {
  type        = string
  description = "AWS region"
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "beta or prod"
  validation {
    condition     = contains(["beta", "prod"], var.environment)
    error_message = "environment must be 'beta' or 'prod'."
  }
}

variable "bucket_name" {
  type        = string
  description = "Target S3 bucket name"
}

variable "voice_id" {
  type        = string
  description = "Polly voice id"
  default     = "Joanna"
}

variable "project" {
  type        = string
  description = "Project tag/name"
  default     = "pixel-learning-tts"
}

provider "aws" {
  region = var.aws_region
}

# ----------------------------
# Locals
# ----------------------------
locals {
  fn_name    = var.environment == "beta" ? "PollyTextToSpeech_Beta" : "PollyTextToSpeech_Prod"
  api_name   = "${var.project}-${var.environment}-api"
  route_path = "/${var.environment}/synthesize"

  tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# ----------------------------
# Package Lambda (zip infra/lambda/)
# ----------------------------
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.module}/lambda"
  output_path = "${path.module}/lambda.zip"
}

# ----------------------------
# IAM Role for Lambda
# ----------------------------
resource "aws_iam_role" "lambda_role" {
  name = "${local.fn_name}-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect    = "Allow",
      Principal = { Service = "lambda.amazonaws.com" },
      Action    = "sts:AssumeRole"
    }]
  })

  tags = local.tags
}

# ----------------------------
# KMS CMK for Lambda environment variable encryption (THIS fixes aws/lambda key issue)
# ----------------------------
resource "aws_kms_key" "lambda_env" {
  description             = "CMK for ${local.fn_name} environment variable encryption"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = local.tags
}

resource "aws_kms_alias" "lambda_env" {
  name          = "alias/${var.project}-${var.environment}-lambda-env"
  target_key_id = aws_kms_key.lambda_env.key_id
}

# Key policy: allow account root full admin + allow THIS lambda role to use it
data "aws_caller_identity" "current" {}

resource "aws_kms_key_policy" "lambda_env" {
  key_id = aws_kms_key.lambda_env.key_id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      {
        Sid       = "AllowAccountRootAdmin",
        Effect    = "Allow",
        Principal = { AWS = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:root" },
        Action    = "kms:*",
        Resource  = "*"
      },
      {
        Sid       = "AllowLambdaRoleUseOfKey",
        Effect    = "Allow",
        Principal = { AWS = aws_iam_role.lambda_role.arn },
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ],
        Resource = "*"
      }
    ]
  })
}

# ----------------------------
# IAM Inline Policy (Logs + Polly + S3 env-scoped + KMS)
# NOTE: aws_iam_role_policy does NOT support tags.
# ----------------------------
resource "aws_iam_role_policy" "lambda_policy" {
  name = "${local.fn_name}-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [
      # CloudWatch Logs
      {
        Sid    = "AllowCloudWatchLogs",
        Effect = "Allow",
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ],
        Resource = "*"
      },

      # Polly
      {
        Sid      = "AllowPollySynthesize",
        Effect   = "Allow",
        Action   = ["polly:SynthesizeSpeech"],
        Resource = "*"
      },

      # S3 write only to env prefix
      {
        Sid      = "AllowWriteToEnvPrefix",
        Effect   = "Allow",
        Action   = ["s3:PutObject"],
        Resource = "arn:aws:s3:::${var.bucket_name}/polly-audio/${var.environment}/*"
      },

      # Allow Lambda runtime to use the CMK we created (scope to this key)
      {
        Sid    = "AllowKmsForLambdaEnvEncryption",
        Effect = "Allow",
        Action = [
          "kms:Decrypt",
          "kms:Encrypt",
          "kms:GenerateDataKey",
          "kms:DescribeKey"
        ],
        Resource = aws_kms_key.lambda_env.arn
      }
    ]
  })
}

# ----------------------------
# Lambda Function
# ----------------------------
resource "aws_lambda_function" "tts" {
  function_name = local.fn_name
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.12"
  handler       = "handler.lambda_handler"

  timeout     = 30
  memory_size = 256

  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256

  # Force Lambda to use our CMK (not aws/lambda managed key)
  kms_key_arn = aws_kms_key.lambda_env.arn

  environment {
    variables = {
      BUCKET_NAME = var.bucket_name
      ENVIRONMENT = var.environment
      VOICE_ID    = var.voice_id
    }
  }

  tags = local.tags

  depends_on = [aws_kms_key_policy.lambda_env]
}

# ----------------------------
# API Gateway (HTTP API v2)
# ----------------------------
resource "aws_apigatewayv2_api" "http_api" {
  name          = local.api_name
  protocol_type = "HTTP"
  tags          = local.tags
}

resource "aws_apigatewayv2_stage" "stage" {
  api_id      = aws_apigatewayv2_api.http_api.id
  name        = "$default"
  auto_deploy = true
  tags        = local.tags
}

resource "aws_apigatewayv2_integration" "lambda" {
  api_id                 = aws_apigatewayv2_api.http_api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.tts.arn
  integration_method     = "POST"
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "route" {
  api_id    = aws_apigatewayv2_api.http_api.id
  route_key = "POST ${local.route_path}"
  target    = "integrations/${aws_apigatewayv2_integration.lambda.id}"
}

resource "aws_lambda_permission" "apigw" {
  statement_id  = "AllowInvokeFromAPIGW-${var.environment}-${aws_apigatewayv2_api.http_api.id}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.tts.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http_api.execution_arn}/*/*"
}

# ----------------------------
# Outputs (kept in this file so outputs.tf is not needed)
# ----------------------------
output "api_invoke_url" {
  value = aws_apigatewayv2_api.http_api.api_endpoint
}

output "route" {
  value = local.route_path
}

output "s3_prefix" {
  value = "s3://${var.bucket_name}/polly-audio/${var.environment}/"
}

output "lambda_name" {
  value = aws_lambda_function.tts.function_name
}

output "lambda_env_kms_key_arn" {
  value = aws_kms_key.lambda_env.arn
}
