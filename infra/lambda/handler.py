def lambda_handler(event, context):
    import os
    import json
    import traceback
    from datetime import datetime, timezone
    import boto3

    # ----- Always log the basics so CloudWatch shows something -----
    print("EVENT_KEYS:", list(event.keys()) if isinstance(event, dict) else type(event))
    print("RAW_BODY_TYPE:", type(event.get("body")).__name__ if isinstance(event, dict) else "N/A")

    BUCKET = os.environ["BUCKET_NAME"]
    ENV = os.environ.get("ENVIRONMENT", "beta")   # ✅ matches Terraform
    VOICE_ID = os.environ.get("VOICE_ID", "Joanna")

    polly = boto3.client("polly")
    s3 = boto3.client("s3")

    try:
        # ---------- Parse request safely ----------
        payload = {}
        body = event.get("body") if isinstance(event, dict) else None

        if isinstance(body, str) and body.strip():
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return {
                    "statusCode": 400,
                    "headers": {"content-type": "application/json"},
                    "body": json.dumps({"error": "Request body must be valid JSON"})
                }
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

        print("TARGET_BUCKET:", BUCKET)
        print("TARGET_KEY:", key)
        print("VOICE_ID:", VOICE_ID)

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

        return {
            "statusCode": 200,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({
                "message": "Audio generated successfully",
                "s3_uri": f"s3://{BUCKET}/{key}"
            })
        }

    except Exception as e:
        print("ERROR:", str(e))
        print(traceback.format_exc())
        return {
            "statusCode": 500,
            "headers": {"content-type": "application/json"},
            "body": json.dumps({"error": "Internal Server Error", "detail": str(e)})
        }
