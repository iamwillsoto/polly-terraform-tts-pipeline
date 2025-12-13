import json
import os
import boto3
from datetime import datetime, timezone

polly = boto3.client("polly")
s3 = boto3.client("s3")

BUCKET = os.environ["BUCKET_NAME"]
ENV = os.environ.get("ENV_PREFIX", "beta")
VOICE = os.environ.get("VOICE_ID", "Joanna")

def lambda_handler(event, context):
    # Parse body safely
    payload = {}
    body = event.get("body")

    if isinstance(body, str) and body.strip():
        payload = json.loads(body)
    elif isinstance(body, dict):
        payload = body
    elif isinstance(event, dict) and "text" in event:
        payload = event

    text = (payload.get("text") or "").strip()   # <-- guarantees text exists

    if not text:
        return {
            "statusCode": 400,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"error": "Missing 'text' in request body"})
        }

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"polly-audio/{ENV}/{ts}.mp3"

    resp = polly.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=VOICE
    )

    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=resp["AudioStream"].read(),
        ContentType="audio/mpeg"
    )

    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"message": "Audio generated", "s3_uri": f"s3://{BUCKET}/{key}"})
    }
