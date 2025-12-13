output "lambda_name" {
  value = aws_lambda_function.tts.function_name
}

output "api_invoke_url" {
  value = aws_apigatewayv2_api.http_api.api_endpoint
}

output "route" {
  value = var.environment == "beta" ? "/beta/syntehsize" : "/prod/synthesize"
}

output "s3_prefix" {
  value = "s3://${var.bucket_name}/polly-audio/${var.environment}/"
}