import os
import json
import logging
import base64
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
    }


def _parse_event(event: dict) -> dict:
    """
    Supports:
      - API Gateway HTTP API v2 proxy events (event['body'] is string; may be base64)
      - direct Lambda invoke with {"text":"..."}
    """
    if not isinstance(event, dict):
        return {}

    # direct invoke convenience
    if isinstance(event.get("text"), str):
        return {"text": event["text"]}

    body = event.get("body")

    # handle base64 bodies
    if event.get("isBase64Encoded") is True and isinstance(body, str):
        try:
            body = base64.b64decode(body).decode("utf-8")
        except Exception:
            return {}

    if isinstance(body, str) and body.strip():
        return json.loads(body)

    if isinstance(body, dict):
        return body

    return {}


def lambda_handler(event, context):
    try:
        bucket = os.environ["BUCKET_NAME"]
        env = (os.environ.get("ENVIRONMENT") or "beta").strip().lower()
        voice_id = (os.environ.get("VOICE_ID") or "Joanna").strip()

        logger.info("START env=%s bucket=%s voice_id=%s", env, bucket, voice_id)
        logger.info("event_keys=%s", list(event.keys()) if isinstance(event, dict) else str(type(event)))

        payload = _parse_event(event)
        text = (payload.get("text") or "").strip()
        if not text:
            return _resp(400, {"error": "Missing 'text' in request body"})

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        key = f"polly-audio/{env}/{ts}.mp3"
        logger.info("writing_s3_key=%s", key)

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
        return _resp(200, {"message": "Audio generated successfully", "s3_uri": f"s3://{bucket}/{key}"})

    except Exception as e:
        logger.exception("Unhandled error")
        # keep detail visible while debugging
        return _resp(500, {"error": "Internal error", "detail": str(e)})
