variable "aws_region" {
  type = string
}

variable "environment" {
  type = string
}

variable "bucket_name" {
  type = string
}

variable "voice_id" {
  type    = string
  default = "Joanna"
}

variable "project" {
  type    = string
  default = "pixel-learning-tts"
}