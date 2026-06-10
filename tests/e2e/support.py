import hashlib
import io
import os
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageFont


BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")


def get_bytes(path):
    with urlopen(f"{BASE_URL}{path}", timeout=60) as response:
        return response.read()


def deterministic_color(identifier):
    digest = hashlib.sha256(identifier.encode("utf-8")).digest()
    return tuple(48 + value % 176 for value in digest[:3])


def jpeg_data(identifier, width=400, height=400):
    background = deterministic_color(identifier)
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    label = identifier[:32]
    box = draw.textbbox((0, 0), label, font=font)
    text_width = box[2] - box[0]
    text_height = box[3] - box[1]
    padding = max(8, min(width, height) // 30)
    x = max(padding, (width - text_width) // 2)
    y = max(padding, (height - text_height) // 2)
    draw.rectangle(
        (
            x - padding,
            y - padding,
            x + text_width + padding,
            y + text_height + padding,
        ),
        fill=(10, 14, 18),
    )
    draw.text((x, y), label, fill=(255, 255, 255), font=font)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=False)
    return output.getvalue()
