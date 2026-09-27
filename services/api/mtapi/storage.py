"""S3-compatible object storage (Cloudflare R2 in production, MinIO locally). Browsers only ever get short-lived
signed URLs; bucket credentials never leave the server.

Key layout. Lifecycle rules can only match prefixes, so each retention class has its own top-level prefix:
  uploads/{user_id}/{upload_id}/{filename}            raw uploads            (bucket rule: expire after 1 day)
  users/{user_id}/jobs/{job_id}/source/{i}.{ext}      validated page images  (retention_days)
  users/{user_id}/jobs/{job_id}/intermediate/{i}.png  cleaned pages          (retention_days, editor needs them)
  users/{user_id}/jobs/{job_id}/output/{i}.jpg        translated pages       (retention_days)
  users/{user_id}/jobs/{job_id}/archive/{name}.zip    download archive       (retention_days)
Job data is deleted by the app when a job expires (system.cleanup); a bucket rule on users/ at 2x the longest
retention is the backstop. See docs/OPERATIONS.md.
"""

from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import get_settings


def _client(endpoint: str):
    s = get_settings()
    return boto3.client(
        "s3", endpoint_url=endpoint, aws_access_key_id=s.s3_access_key, aws_secret_access_key=s.s3_secret_key,
        region_name=s.s3_region, config=Config(signature_version="s3v4", retries={"max_attempts": 5, "mode": "standard"}),
    )


@lru_cache
def client():
    return _client(get_settings().s3_endpoint)


@lru_cache
def signing_client():
    s = get_settings()
    return _client(s.s3_public_endpoint or s.s3_endpoint)


def bucket() -> str:
    return get_settings().s3_bucket


def job_prefix(user_id, job_id) -> str:
    return f"users/{user_id}/jobs/{job_id}/"


def presign_put(key: str, size: int, content_type: str, ttl: int = 900) -> str:
    # ContentLength and ContentType are part of the signature, so the client cannot upload a different size/type.
    return signing_client().generate_presigned_url(
        "put_object", Params={"Bucket": bucket(), "Key": key, "ContentLength": size, "ContentType": content_type},
        ExpiresIn=ttl,
    )


def presign_get(key: str | None, ttl: int = 3600, download_name: str | None = None) -> str | None:
    if not key:
        return None
    params = {"Bucket": bucket(), "Key": key}
    if download_name:
        params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
    return signing_client().generate_presigned_url("get_object", Params=params, ExpiresIn=ttl)


def head(key: str) -> dict | None:
    try:
        return client().head_object(Bucket=bucket(), Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def get_bytes(key: str, max_bytes: int | None = None) -> bytes:
    body = client().get_object(Bucket=bucket(), Key=key)["Body"]
    data = body.read(max_bytes + 1 if max_bytes else None)
    if max_bytes and len(data) > max_bytes:
        raise ValueError("object larger than allowed")
    return data


def put_bytes(key: str, data: bytes, content_type: str) -> None:
    client().put_object(Bucket=bucket(), Key=key, Body=data, ContentType=content_type)


def delete_prefix(prefix: str) -> int:
    assert prefix.startswith(("users/", "uploads/")) and prefix.endswith("/") and prefix.count("/") >= 2, \
        "refusing to delete outside a user prefix"
    deleted = 0
    for page in client().get_paginator("list_objects_v2").paginate(Bucket=bucket(), Prefix=prefix):
        keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
        if keys:
            client().delete_objects(Bucket=bucket(), Delete={"Objects": keys, "Quiet": True})
            deleted += len(keys)
    return deleted


def ping() -> None:
    client().head_bucket(Bucket=bucket())
