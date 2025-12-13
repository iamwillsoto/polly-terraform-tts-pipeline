terraform {
  backend "s3" {
    bucket = "pixel-learning-tts-wsoto"
    key    = "terraform-state/polly-tts/terraform.tfstate"
    region = "us-east-1"
  }
}