import os
import json
import base64
import logging
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

polly = boto3.client("polly")
s3 = boto3.client("s3")


def _resp(code: int, payload: dict):
    return {
        "statusCode": code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
        "isBase64Encoded": False,
    }


def _parse_event(event) -> dict:
    # Direct invoke: {"text":"..."}
    if isinstance(event, dict) and isinstance(event.get("text"), str):
        return {"text": event["text"]}

    if not isinstance(event, dict):
        return {}

    body = event.get("body")
    if body is None:
        return {}

    # HTTP API v2 can base64-encode the body
    if event.get("isBase64Encoded") is True and isinstance(body, str):
        try:
            body = base64.b64decode(body).decode("utf-8")
        except Exception:
            return {}

    if isinstance(body, str) and body.strip():
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {}

    if isinstance(body, dict):
        return body

    return {}


def lambda_handler(event, context):
    request_id = getattr(context, "aws_request_id", "n/a")

    try:
        bucket = (os.environ.get("BUCKET_NAME") or "").strip()
        env = (os.environ.get("ENVIRONMENT") or "beta").strip().lower()
        voice_id = (os.environ.get("VOICE_ID") or "Joanna").strip()

        # Force visibility: these should appear in CloudWatch once KMS is fixed
        logger.info("START request_id=%s", request_id)
        logger.info("CONFIG env=%s bucket=%s voice_id=%s", env, bucket or "<EMPTY>", voice_id)
        logger.info("EVENT keys=%s", list(event.keys()) if isinstance(event, dict) else str(type(event)))

        if not bucket:
            return _resp(500, {
                "error": "BUCKET_NAME is empty in Lambda env vars",
                "request_id": request_id
            })

        payload = _parse_event(event)
        text = (payload.get("text") or "").strip()
        if not text:
            return _resp(400, {"error": "Missing 'text' in request body", "request_id": request_id})

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        key = f"polly-audio/{env}/{ts}.mp3"
        logger.info("S3_KEY=%s", key)

        polly_resp = polly.synthesize_speech(
            Engine="neural",
            VoiceId=voice_id,
            OutputFormat="mp3",
            Text=text,
        )

        audio = polly_resp.get("AudioStream")
        if not audio:
            raise RuntimeError("Polly did not return AudioStream")

        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=audio.read(),
            ContentType="audio/mpeg",
        )

        logger.info("SUCCESS s3_uri=s3://%s/%s", bucket, key)
        return _resp(200, {"message": "OK", "s3_uri": f"s3://{bucket}/{key}", "request_id": request_id})

    except Exception as e:
        logger.exception("Unhandled error")
        return _resp(500, {"error": "Internal error", "detail": str(e), "request_id": request_id})
