# Serverless Text-to-Speech Pipeline with AWS Polly (Terraform + GitHub Actions)

## Overview
This project implements a fully serverless, production-grade **Text-to-Speech (TTS) API** using **Amazon Polly**, deployed and managed with **Terraform** and automated through **GitHub Actions CI/CD**.

The system converts incoming text into high-quality MP3 audio files and stores them in Amazon S3, enabling businesses to automatically generate audio content at scale without managing servers.

---

## Architecture Summary

**Request Flow**
1. Client sends a POST request with text
2. API Gateway triggers AWS Lambda
3. Lambda calls Amazon Polly to synthesize speech
4. Generated MP3 is stored in S3 under an environment-scoped prefix
5. API responds with the S3 URI of the audio file

**Environments**
- `beta` — validation/testing
- `prod` — production traffic  
Each environment has:
- Isolated Terraform state
- Environment-scoped IAM permissions
- Separate S3 prefixes

---

## AWS Resources Used

- **AWS Lambda**
  - Stateless text-to-speech execution
  - Encrypted environment variables
  - Least-privilege IAM role

- **Amazon Polly**
  - Neural text-to-speech synthesis
  - High-quality MP3 output

- **Amazon API Gateway (HTTP API v2)**
  - Public HTTPS endpoint
  - Lambda proxy integration

- **Amazon S3**
  - Durable storage for generated audio
  - Environment-scoped prefixes:
    - `polly-audio/beta/`
    - `polly-audio/prod/`

- **AWS IAM**
  - Fine-grained execution role
  - Scoped permissions for Logs, Polly, S3, and KMS

- **AWS KMS**
  - Encryption of Lambda environment variables

- **Terraform**
  - Infrastructure as Code
  - Remote S3 backend per environment
  - Deterministic, repeatable deployments

- **GitHub Actions**
  - CI/CD automation
  - Beta deploy + test on PR
  - Production deploy + live invocation on merge

---

## API Usage

### Endpoint
POST /{environment}/synthesize

### Example Request
```bash
curl -X POST "<API_URL>/prod/synthesize" \
  -H "content-type: application/json" \
  -d '{"text":"This is live production"}'

### Example Response
{
  "message": "OK",
  "s3_uri": "s3://<bucket>/polly-audio/prod/20251215T014010Z.mp3"
}

## Business Value

This solution enables organizations to:

- **Automate audio generation**  
  Convert documentation, training content, articles, or notifications into audio automatically.

- **Scale without servers**  
  Fully serverless architecture with on-demand execution.

- **Reduce operational overhead**  
  No EC2, no container management, no scaling logic required.

- **Support accessibility initiatives**  
  Audio versions of written content for visually impaired users.

- **Integrate easily**  
  Simple HTTP API suitable for web applications, CMS platforms, and internal tools.

