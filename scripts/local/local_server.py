import argparse
import base64
import mimetypes
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = ROOT / "frontend"
BACKEND_ROOT = ROOT / "backend"

sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_REGION", "sa-east-1")
os.environ.setdefault("AWS_DEFAULT_REGION", "sa-east-1")
os.environ.setdefault("TABLE_NAME", "torneio-sinuca-local")
os.environ.setdefault("MEDIA_BUCKET", "torneio-sinuca-local-media")
os.environ.setdefault("ADMIN_PASSWORD", "1234")
os.environ.setdefault("SECRET_KEY", "local-dev-secret")
os.environ.setdefault("DYNAMODB_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("S3_ENDPOINT_URL", "http://localhost:4566")
os.environ.setdefault("DATABASE_RESET_VERSION", "")
os.environ.setdefault("LOCAL_DEV", "1")

import app as lambda_app  # noqa: E402


ROUTES = {
    "/": "/index.html",
    "/admin": "/admin.html",
    "/admin/": "/admin.html",
    "/player": "/player.html",
    "/player/": "/player.html",
    "/telao": "/telao.html",
    "/telao/": "/telao.html",
    "/tv": "/telao.html",
    "/tv/": "/telao.html",
    "/admin/jogador": "/admin-player.html",
    "/admin/jogador/": "/admin-player.html",
    "/admin/patrocinador": "/sponsor-edit.html",
    "/admin/patrocinador/": "/sponsor-edit.html",
}


def query_params(query):
    parsed = parse_qs(query, keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def static_path_for(url_path):
    path = unquote(url_path)
    rewritten = ROUTES.get(path, path)
    relative = rewritten.lstrip("/")
    candidate = (FRONTEND_ROOT / relative).resolve()
    if FRONTEND_ROOT.resolve() not in [candidate, *candidate.parents]:
        return None
    return candidate


class DevHandler(BaseHTTPRequestHandler):
    server_version = "TorneioSinucaLocal/1.0"

    def do_OPTIONS(self):
        self.handle_api()

    def do_GET(self):
        self.route_request()

    def do_HEAD(self):
        self.route_request(head_only=True)

    def do_POST(self):
        self.route_request()

    def do_PUT(self):
        self.route_request()

    def do_PATCH(self):
        self.route_request()

    def do_DELETE(self):
        self.route_request()

    def route_request(self, head_only=False):
        parsed = urlparse(self.path)
        if parsed.path == "/__health":
            self.send_bytes(200, b"ok\n", {"Content-Type": "text/plain; charset=utf-8"}, head_only)
            return
        if parsed.path == "/api" or parsed.path.startswith("/api/"):
            self.handle_api(head_only=head_only)
            return
        if parsed.path == "/perfil" or parsed.path == "/perfil/" or parsed.path.startswith("/perfil/"):
            self.handle_api(head_only=head_only)
            return
        if parsed.path.startswith("/media/"):
            self.serve_media(parsed.path, head_only=head_only)
            return
        self.serve_static(parsed.path, head_only=head_only)

    def handle_api(self, head_only=False):
        parsed = urlparse(self.path)
        body_bytes = b""
        length = int(self.headers.get("Content-Length") or "0")
        if length:
            body_bytes = self.rfile.read(length)

        is_base64 = False
        try:
            body = body_bytes.decode("utf-8")
        except UnicodeDecodeError:
            body = base64.b64encode(body_bytes).decode("ascii")
            is_base64 = True

        event = {
            "version": "2.0",
            "rawPath": parsed.path,
            "rawQueryString": parsed.query,
            "queryStringParameters": query_params(parsed.query),
            "headers": {key: value for key, value in self.headers.items()},
            "requestContext": {"http": {"method": self.command, "path": parsed.path}},
            "body": body,
            "isBase64Encoded": is_base64,
        }

        result = lambda_app.lambda_handler(event, None)
        status = int(result.get("statusCode", 200))
        headers = result.get("headers", {})
        body = result.get("body", "")
        if isinstance(body, str):
            payload = body.encode("utf-8")
        else:
            payload = body or b""
        self.send_bytes(status, payload, headers, head_only)

    def serve_static(self, url_path, head_only=False):
        path = static_path_for(url_path)
        if not path or not path.exists() or not path.is_file():
            path = FRONTEND_ROOT / "index.html"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        headers = {"Content-Type": content_type}
        if path.name == "config.js":
            headers["Cache-Control"] = "no-store"
        self.send_bytes(200, path.read_bytes(), headers, head_only)

    def serve_media(self, url_path, head_only=False):
        if not lambda_app._s3 or not os.environ.get("MEDIA_BUCKET"):
            self.send_bytes(404, b"media bucket not configured", {"Content-Type": "text/plain"}, head_only)
            return
        key = unquote(url_path.lstrip("/"))
        try:
            obj = lambda_app._s3.get_object(Bucket=os.environ["MEDIA_BUCKET"], Key=key)
            payload = obj["Body"].read()
            content_type = obj.get("ContentType") or mimetypes.guess_type(key)[0] or "application/octet-stream"
            headers = {
                "Content-Type": content_type,
                "Cache-Control": obj.get("CacheControl") or "no-store",
            }
            self.send_bytes(200, payload, headers, head_only)
        except ClientError:
            self.send_bytes(404, b"media not found", {"Content-Type": "text/plain"}, head_only)

    def send_bytes(self, status, payload, headers=None, head_only=False):
        headers = headers or {}
        self.send_response(status)
        for key, value in headers.items():
            if key.lower() == "content-length":
                continue
            self.send_header(key, str(value))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def log_message(self, fmt, *args):
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))


def main():
    parser = argparse.ArgumentParser(description="Servidor local do torneio de sinuca.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DevHandler)
    print(f"Servidor local em http://{args.host}:{args.port}")
    print("API local em /api usando LocalStack DynamoDB/S3.")
    server.serve_forever()


if __name__ == "__main__":
    main()
