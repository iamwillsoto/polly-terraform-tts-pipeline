def lambda_handler(event, context):
    import os
    import json
    from datetime import datetime, timezone
    import boto3

    BUCKET = os.environ["BUCKET_NAME"]
    ENV = os.environ.get("ENV_PREFIX", "beta")   # <- matches Terraform variable name
    VOICE_ID = os.environ.get("VOICE_ID", "Joanna")

    polly = boto3.client("polly")
    s3 = boto3.client("s3")

    # ---------- Parse request safely ----------
    payload = {}
    body = event.get("body")

    if isinstance(body, str) and body.strip():
        payload = json.loads(body)
    elif isinstance(body, dict):
        payload = body
    elif isinstance(event, dict) and "text" in event:
        payload = event

    text = (payload.get("text") or "").strip()

    if not text:
        return {
            "statusCode": 400,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"error": "Missing 'text' in request body"})
        }

    # ---------- Generate S3 key ----------
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    key = f"polly-audio/{ENV}/{ts}.mp3"

    # ---------- Call Amazon Polly ----------
    response = polly.synthesize_speech(
        Engine="neural",
        VoiceId=VOICE_ID,
        OutputFormat="mp3",
        Text=text
    )

    audio_stream = response.get("AudioStream")
    if not audio_stream:
        raise RuntimeError("Polly did not return audio stream")

    # ---------- Upload to S3 ----------
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=audio_stream.read(),
        ContentType="audio/mpeg"
    )

    # ---------- Return success ----------
    return {
        "statusCode": 200,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({
            "message": "Audio generated successfully",
            "s3_uri": f"s3://{BUCKET}/{key}"
        })
    }
