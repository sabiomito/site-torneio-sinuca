import os
import sys
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError


REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "sa-east-1"
TABLE_NAME = os.environ.get("TABLE_NAME", "torneio-sinuca-local")
MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "torneio-sinuca-local-media")
DYNAMODB_ENDPOINT_URL = os.environ.get("DYNAMODB_ENDPOINT_URL", "http://localhost:4566")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://localhost:4566")


def is_local_url(url):
    host = urlparse(url).hostname or ""
    return host in {"localhost", "127.0.0.1", "::1"}


def guard_local():
    if not is_local_url(DYNAMODB_ENDPOINT_URL) or not is_local_url(S3_ENDPOINT_URL):
        raise SystemExit("Abortado: endpoints locais precisam apontar para localhost.")
    if "local" not in TABLE_NAME.lower() or "local" not in MEDIA_BUCKET.lower():
        raise SystemExit("Abortado: nomes locais precisam conter 'local'.")


def dynamodb_resource():
    return boto3.resource("dynamodb", region_name=REGION, endpoint_url=DYNAMODB_ENDPOINT_URL)


def s3_client():
    return boto3.client("s3", region_name=REGION, endpoint_url=S3_ENDPOINT_URL)


def create_table():
    dynamodb = dynamodb_resource()
    table = dynamodb.Table(TABLE_NAME)
    try:
        table.load()
        print(f"DynamoDB OK: {TABLE_NAME}")
        return
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code != "ResourceNotFoundException":
            raise

    table = dynamodb.create_table(
        TableName=TABLE_NAME,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
    )
    table.wait_until_exists()
    print(f"DynamoDB criado: {TABLE_NAME}")


def create_bucket():
    s3 = s3_client()
    try:
        s3.head_bucket(Bucket=MEDIA_BUCKET)
        print(f"S3 OK: {MEDIA_BUCKET}")
        return
    except ClientError:
        pass

    kwargs = {"Bucket": MEDIA_BUCKET}
    if REGION != "us-east-1":
        kwargs["CreateBucketConfiguration"] = {"LocationConstraint": REGION}
    s3.create_bucket(**kwargs)
    print(f"S3 criado: {MEDIA_BUCKET}")


def main():
    guard_local()
    create_table()
    create_bucket()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Falha ao preparar ambiente local: {exc}", file=sys.stderr)
        raise
