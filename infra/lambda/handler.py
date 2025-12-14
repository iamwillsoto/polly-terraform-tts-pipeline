import os
import json
import logging
import traceback
from datetime import datetime, timezone

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

polly = boto3.client("polly")
s3 = boto3.client("s3")


def _json_response(code: int, payload: dict):
    return {
        "statusCode": code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(payload),
    }


def _safe_json_loads(s: str):
    """
    Try to parse JSON safely. Returns (obj, error_message).
    """
    try:
        return json.loads(s), None
    except Exception as e:
        return None, str(e)


def lambda_handler(event, context):
    """
    Forced visibility handler:
    - Logs important execution context and input shape
    - On error: logs full traceback and returns JSON with detail + trace_id
    """

    trace_id = getattr(context, "aws_request_id", None) or "no-aws-request-id"

    try:
        # ----------------------------
        # Environment / config
        # ----------------------------
        bucket = os.environ["BUCKET_NAME"]

        # Prefer ENVIRONMENT (Terraform), fall back to ENV_PREFIX (legacy), then beta.
        env = (os.environ.get("ENVIRONMENT") or os.environ.get("ENV_PREFIX") or "beta").strip().lower()

        voice_id = (os.environ.get("VOICE_ID") or "Joanna").strip()

        logger.info("trace_id=%s env=%s bucket=%s voice_id=%s", trace_id, env, bucket, voice_id)

        # Log a *safe* summary of the incoming event
        if isinstance(event, dict):
            logger.info("event_keys=%s", list(event.keys()))
            logger.info("event_version=%s", event.get("version"))
            logger.info("has_body=%s", "body" in event)
            logger.info("isBase64Encoded=%s", event.get("isBase64Encoded"))
            # avoid logging full body in case it's large/sensitive
            body_preview = event.get("body")
            if isinstance(body_preview, str):
                logger.info("body_preview=%s", body_preview[:200])
        else:
            logger.info("event_type=%s", type(event))

        # ----------------------------
        # Parse request
        # ----------------------------
        payload = {}
        body = event.get("body") if isinstance(event, dict) else None

        if isinstance(body, str) and body.strip():
            parsed, parse_err = _safe_json_loads(body)
            if parse_err:
                # Force visibility: invalid JSON should be a 400 with details
                logger.warning("trace_id=%s invalid_json=%s", trace_id, parse_err)
                return _json_response(400, {
                    "error": "Invalid JSON body",
                    "detail": parse_err,
                    "trace_id": trace_id,
                })
            payload = parsed or {}

        elif isinstance(body, dict):
            payload = body

        elif isinstance(event, dict) and "text" in event:
            # Allow direct invoke with {"text":"..."}
            payload = event

        text = (payload.get("text") or "").strip()
        if not text:
            return _json_response(400, {
                "error": "Missing 'text' in request body",
                "trace_id": trace_id,
            })

        # ----------------------------
        # Generate S3 key
        # ----------------------------
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        key = f"polly-audio/{env}/{ts}.mp3"   # <-- FIXED: uses `env`, not undefined ENV

        logger.info("trace_id=%s writing_s3_key=%s", trace_id, key)

        # ----------------------------
        # Call Polly
        # ----------------------------
        resp = polly.synthesize_speech(
            Engine="neural",
            VoiceId=voice_id,
            OutputFormat="mp3",
            Text=text,
        )

        audio = resp.get("AudioStream")
        if not audio:
            raise RuntimeError("Polly did not return AudioStream")

        # ----------------------------
        # Upload to S3
        # ----------------------------
        s3.put_object(
            Bucket=bucket,
            Key=key,
            Body=audio.read(),
            ContentType="audio/mpeg",
        )

        logger.info("trace_id=%s upload_success s3_uri=s3://%s/%s", trace_id, bucket, key)

        return _json_response(200, {
            "message": "Audio generated successfully",
            "s3_uri": f"s3://{bucket}/{key}",
            "trace_id": trace_id,
        })

    except Exception as e:
        # ----------------------------
        # FORCE VISIBILITY
        # ----------------------------
        tb = traceback.format_exc()

        # Full traceback in CloudWatch
        logger.error("trace_id=%s unhandled_error=%s", trace_id, str(e))
        logger.error("trace_id=%s traceback=%s", trace_id, tb)

        # Also return detail so API Gateway response isn't just "Internal Server Error"
        return _json_response(500, {
            "error": "Internal error",
            "detail": str(e),
            "trace_id": trace_id,
        })
