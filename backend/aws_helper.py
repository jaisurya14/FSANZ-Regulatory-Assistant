import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv(dotenv_path="../.env")

# Connect to AWS S3
s3_client = boto3.client(
    's3',
    region_name=os.getenv("AWS_REGION")
)

BUCKET = os.getenv("S3_BUCKET")

def upload_file_to_s3(local_path: str, s3_key: str):
    """Upload a local file to S3"""
    print(f"Uploading {local_path} to S3...")
    s3_client.upload_file(local_path, BUCKET, s3_key)
    print(f"Uploaded to s3://{BUCKET}/{s3_key}")

def download_file_from_s3(s3_key: str, local_path: str):
    """Download a file from S3 to local"""
    print(f"Downloading s3://{BUCKET}/{s3_key}...")
    s3_client.download_file(BUCKET, s3_key, local_path)
    print(f"Downloaded to {local_path}")

def upload_json_to_s3(data: list, s3_key: str):
    """Upload a Python list/dict directly to S3 as JSON"""
    print(f"Uploading JSON to S3: {s3_key}")
    json_data = json.dumps(data, ensure_ascii=False, indent=2)
    s3_client.put_object(
        Bucket=BUCKET,
        Key=s3_key,
        Body=json_data.encode('utf-8'),
        ContentType='application/json'
    )
    print(f"JSON uploaded to s3://{BUCKET}/{s3_key}")

def download_json_from_s3(s3_key: str) -> list:
    """Download JSON directly from S3 into Python"""
    print(f"Downloading JSON from S3: {s3_key}")
    response = s3_client.get_object(Bucket=BUCKET, Key=s3_key)
    data = json.loads(response['Body'].read().decode('utf-8'))
    print(f"Loaded {len(data)} items from S3")
    return data

def list_s3_files(prefix: str = ""):
    """List all files in S3 bucket"""
    response = s3_client.list_objects_v2(Bucket=BUCKET, Prefix=prefix)
    if 'Contents' in response:
        for obj in response['Contents']:
            print(f"  {obj['Key']} ({obj['Size']} bytes)")
    else:
        print("No files found")
