import os, json, time
import boto3

s3 = boto3.client("s3")
polly = boto3.client("polly")

BUCKET = os.environ["BUCKET_NAME"]
ENV_PREFIX = os.environ["ENV_PREFIX"] # "beta" or "prod"
VOICE_ID = os.environ.get("VOICE_ID", "Joanna")

def _response(status, body):
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body)
    }
    
def lambda_handler(event, context):
    # API Gateway (HTTP API) sends the payload in event["body"] (string).
    raw_body = event.get("body") or "{}"
    try:
        payload = json.loads(raw_body) if isinstance(raw_body, str) else raw_body
    except Exception:
        return _response(400, {"error": "Missing required field: text"})
    
    # Polly synthesize -> mp3 bytes
    # (Polly SynthesizeSpeech API supports OutputFormat='mp3'. : contentReference[oaicite:1]{index=1})
    resp = polly.synthesize_speech(
        Text=text,
        OutputFormat="mp3",
        VoiceId=VOICE_ID
    )
    
    audio_stream = resp.get("AudioStream")
    if not audio_stream:
        return _response(500, {"error": "Polly returned no AudioStream"})
    
    ts = int(time.time())
    key = f"polly-audio/{ENV_PREFIX}/{ts}.mp3"
    
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=audio_stream.read(),
        ContentType="audio/mpeg"
    )
    
    return _response(200, {
        "message": "audio generated",
        "s3_url": f"s3://{BUCKET}/{key}",
        "voice": VOICE_ID
    })