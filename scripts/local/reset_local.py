from botocore.exceptions import ClientError

from init_local import (
    MEDIA_BUCKET,
    TABLE_NAME,
    create_bucket,
    create_table,
    guard_local,
    dynamodb_resource,
    s3_client,
)


def delete_table():
    dynamodb = dynamodb_resource()
    table = dynamodb.Table(TABLE_NAME)
    try:
        table.load()
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code == "ResourceNotFoundException":
            return
        raise
    table.delete()
    table.wait_until_not_exists()
    print(f"DynamoDB removido: {TABLE_NAME}")


def empty_and_delete_bucket():
    s3 = s3_client()
    try:
        s3.head_bucket(Bucket=MEDIA_BUCKET)
    except ClientError:
        return

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=MEDIA_BUCKET):
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects:
            s3.delete_objects(Bucket=MEDIA_BUCKET, Delete={"Objects": objects})

    s3.delete_bucket(Bucket=MEDIA_BUCKET)
    print(f"S3 removido: {MEDIA_BUCKET}")


def main():
    guard_local()
    delete_table()
    empty_and_delete_bucket()
    create_table()
    create_bucket()


if __name__ == "__main__":
    main()
