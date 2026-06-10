import base64
import hashlib
import importlib
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "sa-east-1")

app = importlib.import_module("app")


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.deleted = []

    def put_object(self, **kwargs):
        self.objects[kwargs["Key"]] = kwargs

    def delete_object(self, **kwargs):
        self.deleted.append(kwargs["Key"])
        self.objects.pop(kwargs["Key"], None)


def data_url(raw):
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")


def test_media_update_uses_content_versioned_url(monkeypatch):
    fake_s3 = FakeS3()
    monkeypatch.setattr(app, "_s3", fake_s3)
    monkeypatch.setattr(app, "MEDIA_BUCKET", "test-media")

    first_raw = b"first-jpeg-content"
    second_raw = b"second-jpeg-content"
    first_url = app.save_jpeg_media(data_url(first_raw), "media/players/player-1/photo.jpg")
    second_url = app.save_jpeg_media(
        data_url(second_raw),
        "media/players/player-1/photo.jpg",
        first_url,
    )

    assert first_url != second_url
    assert hashlib.sha256(first_raw).hexdigest()[:16] in first_url
    assert hashlib.sha256(second_raw).hexdigest()[:16] in second_url
    assert first_url.lstrip("/") in fake_s3.deleted
    assert first_url.lstrip("/") not in fake_s3.objects
    assert fake_s3.objects[second_url.lstrip("/")]["Body"] == second_raw
    assert fake_s3.objects[second_url.lstrip("/")]["CacheControl"].endswith("immutable")


def test_media_delete_never_leaves_media_prefix(monkeypatch):
    fake_s3 = FakeS3()
    monkeypatch.setattr(app, "_s3", fake_s3)
    monkeypatch.setattr(app, "MEDIA_BUCKET", "test-media")

    app.save_jpeg_media(
        data_url(b"new-content"),
        "media/players/player-1/photo.jpg",
        "/index.html",
    )

    assert fake_s3.deleted == []
