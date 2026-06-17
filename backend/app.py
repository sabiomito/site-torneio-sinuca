import base64
import hashlib
import hmac
import json
import os
import random
import re
import time
import uuid
from datetime import datetime
from decimal import Decimal
from html import escape as html_escape
from itertools import combinations
from urllib.parse import quote, unquote

import boto3
from boto3.dynamodb.conditions import Attr

TABLE_NAME = os.environ.get("TABLE_NAME", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")
SECRET_KEY = os.environ.get("SECRET_KEY", "troque-esta-chave")
SESSION_SECONDS = int(os.environ.get("SESSION_SECONDS", "43200"))
DATABASE_RESET_VERSION = os.environ.get("DATABASE_RESET_VERSION", "")
MEDIA_BUCKET = os.environ.get("MEDIA_BUCKET", "")
AWS_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "sa-east-1"
DYNAMODB_ENDPOINT_URL = os.environ.get("DYNAMODB_ENDPOINT_URL", "")
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "")

_session = boto3.session.Session(region_name=AWS_REGION)
_dynamodb_options = {"endpoint_url": DYNAMODB_ENDPOINT_URL} if DYNAMODB_ENDPOINT_URL else {}
_s3_options = {"endpoint_url": S3_ENDPOINT_URL} if S3_ENDPOINT_URL else {}
_dynamodb = _session.resource("dynamodb", **_dynamodb_options)
_table = _dynamodb.Table(TABLE_NAME) if TABLE_NAME else None
_s3 = _session.client("s3", **_s3_options) if MEDIA_BUCKET else None
_reset_checked = False

PLAYER_STATUS_ACTIVE = "active"
PLAYER_STATUS_DISQUALIFIED = "disqualified"
PLAYER_STATUS_BANNED = "banned"
DISCIPLINARY_PLAYER_STATUSES = {
    PLAYER_STATUS_DISQUALIFIED,
    PLAYER_STATUS_BANNED,
}


def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    return str(value)


def to_dynamo(value):
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_dynamo(v) for v in value]
    return value


def response(status, data=None, headers=None):
    base_headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "content-type,authorization,x-admin-token",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
    }
    if headers:
        base_headers.update(headers)
    return {
        "statusCode": status,
        "headers": base_headers,
        "body": json.dumps(data or {}, ensure_ascii=False, default=json_default),
    }


def html_response(status, body, headers=None):
    base_headers = {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
    }
    if headers:
        base_headers.update(headers)
    return {
        "statusCode": status,
        "headers": base_headers,
        "body": body,
    }


def parse_body(event):
    body = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body).decode("utf-8")
    try:
        return json.loads(body or "{}")
    except json.JSONDecodeError:
        return {}


def get_method_path(event):
    request_context = event.get("requestContext", {})
    http = request_context.get("http", {})
    method = http.get("method") or event.get("httpMethod", "GET")
    path = event.get("rawPath") or event.get("path") or "/"
    if path == "/api" or path.startswith("/api/"):
        path = path[4:] or "/"
    path = path.rstrip("/") or "/"
    return method.upper(), path


def get_query_params(event):
    return event.get("queryStringParameters") or {}


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def make_token():
    payload = {"iat": int(time.time()), "exp": int(time.time()) + SESSION_SECONDS, "typ": "admin"}
    payload_part = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(SECRET_KEY.encode("utf-8"), payload_part.encode("utf-8"), hashlib.sha256).digest()
    return payload_part + "." + b64url(signature)


def verify_token(token):
    if not token or "." not in token:
        return False
    payload_part, signature_part = token.split(".", 1)
    expected = b64url(hmac.new(SECRET_KEY.encode("utf-8"), payload_part.encode("utf-8"), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, signature_part):
        return False
    try:
        payload = json.loads(b64url_decode(payload_part).decode("utf-8"))
    except Exception:
        return False
    return payload.get("typ") == "admin" and int(payload.get("exp", 0)) >= int(time.time())


def require_admin(event):
    headers = event.get("headers") or {}
    authorization = headers.get("authorization") or headers.get("Authorization") or ""
    if authorization.lower().startswith("bearer "):
        return verify_token(authorization.split(" ", 1)[1].strip())
    token = str(get_query_params(event).get("token") or "").strip()
    if token:
        return verify_token(token)
    body = parse_body(event)
    token = str(body.get("token") or "").strip()
    return verify_token(token) if token else False


def put_item(item):
    item["updated_at"] = now_iso()
    _table.put_item(Item=to_dynamo(item))


def delete_item(pk, sk):
    _table.delete_item(Key={"pk": pk, "sk": sk})


def get_item(pk, sk):
    result = _table.get_item(Key={"pk": pk, "sk": sk})
    return result.get("Item")


def scan_all_items():
    items = []
    kwargs = {}
    while True:
        result = _table.scan(**kwargs)
        items.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items


def scan_type(item_type):
    items = []
    kwargs = {"FilterExpression": Attr("type").eq(item_type)}
    while True:
        result = _table.scan(**kwargs)
        items.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return items


def clear_all_data(keep_reset_marker=True):
    for item in scan_all_items():
        delete_item(item["pk"], item["sk"])
    if keep_reset_marker and DATABASE_RESET_VERSION:
        put_item({
            "pk": "CONFIG",
            "sk": "RESET",
            "type": "RESET_MARKER",
            "reset_version": DATABASE_RESET_VERSION,
            "created_at": now_iso(),
        })


def ensure_reset_once():
    global _reset_checked
    if _reset_checked or not DATABASE_RESET_VERSION:
        return
    marker = get_item("CONFIG", "RESET")
    if not marker or marker.get("reset_version") != DATABASE_RESET_VERSION:
        clear_all_data(keep_reset_marker=True)
    _reset_checked = True


def normalize_int(value, default=0, min_value=None, max_value=None):
    try:
        result = int(value)
    except Exception:
        result = default
    if min_value is not None and result < min_value:
        result = min_value
    if max_value is not None and result > max_value:
        result = max_value
    return result


def normalize_bool(value, default=False):
    if value is None:
        return bool(default)
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off"}
    return bool(value)


def normalize_date(value):
    try:
        datetime.strptime(str(value), "%Y-%m-%d")
        return str(value)
    except Exception:
        return ""


def normalize_time(value, default="09:00"):
    try:
        datetime.strptime(str(value), "%H:%M")
        return str(value)
    except Exception:
        return default


def normalize_chave(value, default="A"):
    chave = str(value or "").strip().upper()
    if not chave:
        chave = default
    return chave[:40]


def chave_name(index):
    # 1 -> A, 2 -> B ... 27 -> AA
    index = max(1, int(index))
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def available_chaves_for_division(config, division):
    rule = (config.get("rules") or {}).get(str(division), {})
    key_count = normalize_int(rule.get("key_count", 1), 1, 1, 99)
    return [chave_name(i) for i in range(1, key_count + 1)]


TV_FILTER_KEYS = ("date", "round", "place", "player", "division", "chave", "status")


def normalize_tv_config(raw=None, bracket_game_filter_fallback="all"):
    raw = raw or {}
    filters_in = raw.get("filters") or {}
    filters = {
        key: str(filters_in.get(key, "") or "").strip()
        for key in TV_FILTER_KEYS
    }
    if filters["status"] not in {"finished", "pending"}:
        filters["status"] = ""
    bracket_game_filter = str(
        raw.get("bracket_game_filter") or bracket_game_filter_fallback or "all"
    ).strip().lower()
    if bracket_game_filter not in {"all", "pending"}:
        bracket_game_filter = "all"
    return {
        "table_seconds": normalize_int(raw.get("table_seconds"), 60, 1, 3600),
        "bracket_seconds": normalize_int(raw.get("bracket_seconds"), 60, 1, 3600),
        "bracket_game_filter": bracket_game_filter,
        "sponsor_seconds": normalize_int(raw.get("sponsor_seconds"), 30, 1, 3600),
        "match_seconds": normalize_int(raw.get("match_seconds"), 5, 1, 3600),
        "filters": filters,
    }


def time_to_minutes(time_str):
    dt = datetime.strptime(str(time_str), "%H:%M")
    return dt.hour * 60 + dt.minute


def minutes_to_time(minutes):
    minutes = minutes % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def add_minutes_to_time(time_str, duration):
    return minutes_to_time(time_to_minutes(time_str) + duration)


def make_id(prefix):
    return prefix + "_" + uuid.uuid4().hex[:12]


class RoundConflictError(ValueError):
    def __init__(self, conflicts):
        self.conflicts = conflicts
        message = "Alguns confrontos da rodada manual já aconteceram ou já estão cadastrados."
        super().__init__(message)



def slugify_name(name):
    text = str(name or "").strip().lower()
    replacements = {
        "á": "a", "à": "a", "ã": "a", "â": "a", "ä": "a",
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "í": "i", "ì": "i", "î": "i", "ï": "i",
        "ó": "o", "ò": "o", "õ": "o", "ô": "o", "ö": "o",
        "ú": "u", "ù": "u", "û": "u", "ü": "u",
        "ç": "c", "ñ": "n",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "jogador"


def player_profile_url(player):
    return "/perfil/" + quote(slugify_name(player.get("name", "")))


def clean_public_player(player):
    item = dict(player)
    item["slug"] = slugify_name(item.get("name", ""))
    item["profile_url"] = player_profile_url(item)
    item.setdefault("short_message", "")
    item.setdefault("photo_url", "")
    item["competition_status"] = normalize_player_status(item.get("competition_status"))
    return item


def parse_image_payload(data_url):
    if not data_url:
        return None
    text = str(data_url)
    if "," not in text or not text.startswith("data:image/"):
        raise ValueError("Imagem inválida.")
    header, payload = text.split(",", 1)
    if "base64" not in header:
        raise ValueError("Imagem inválida.")
    raw = base64.b64decode(payload)
    if len(raw) > 4_500_000:
        raise ValueError("Imagem muito grande. Envie uma imagem menor.")
    return raw


def media_key_from_url(url):
    key = unquote(str(url or "")).split("?", 1)[0].lstrip("/")
    return key if key.startswith("media/") else ""


def delete_media_url(url):
    key = media_key_from_url(url)
    if key and MEDIA_BUCKET and _s3:
        _s3.delete_object(Bucket=MEDIA_BUCKET, Key=key)
        return True
    return False


def save_jpeg_media(data_url, key, previous_url=""):
    raw = parse_image_payload(data_url)
    if raw is None:
        return ""
    if not MEDIA_BUCKET or not _s3:
        raise ValueError("Bucket de mídia não configurado no servidor.")
    stem, extension = os.path.splitext(key)
    content_version = hashlib.sha256(raw).hexdigest()[:16]
    versioned_key = f"{stem}-{content_version}{extension or '.jpg'}"
    _s3.put_object(
        Bucket=MEDIA_BUCKET,
        Key=versioned_key,
        Body=raw,
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000, immutable",
    )
    previous_key = media_key_from_url(previous_url)
    if previous_key and previous_key != versioned_key:
        delete_media_url(previous_url)
    return "/" + versioned_key


def build_pair_key(division, chave, p1_id, p2_id):
    ordered = sorted([str(p1_id), str(p2_id)])
    return f"D{normalize_int(division, 1)}#K{normalize_chave(chave)}#{ordered[0]}#{ordered[1]}"


def normalize_player_status(value):
    status = str(value or PLAYER_STATUS_ACTIVE).strip().lower()
    if status in DISCIPLINARY_PLAYER_STATUSES:
        return status
    return PLAYER_STATUS_ACTIVE


def is_disciplinary_player_status(value):
    return normalize_player_status(value) in DISCIPLINARY_PLAYER_STATUSES


def get_config():
    item = get_item("CONFIG", "TOURNAMENT")
    if not item:
        item = {
            "pk": "CONFIG",
            "sk": "TOURNAMENT",
            "type": "CONFIG",
            "division_count": 2,
            "duration_minutes": 30,
            "rules": {
                "1": {"key_count": 1, "promotion_count": 0, "relegation_count": 0},
                "2": {"key_count": 1, "promotion_count": 0, "relegation_count": 0},
            },
            "show_bracket_scoreboard": True,
            "show_bracket_tv": True,
            "tv_config": normalize_tv_config(),
            "created_at": now_iso(),
        }
        put_item(item)
    item["division_count"] = normalize_int(item.get("division_count"), 2, 1, 20)
    item["duration_minutes"] = normalize_int(item.get("duration_minutes"), 30, 5, 240)
    item["show_bracket_scoreboard"] = normalize_bool(item.get("show_bracket_scoreboard"), True)
    item["show_bracket_tv"] = normalize_bool(item.get("show_bracket_tv"), True)
    item.setdefault("rules", {})
    for d in range(1, item["division_count"] + 1):
        raw = item["rules"].get(str(d), {}) or {}
        item["rules"][str(d)] = {
            "key_count": normalize_int(raw.get("key_count", 1), 1, 1, 99),
            "promotion_count": normalize_int(raw.get("promotion_count", 0), 0, 0, 100),
            "relegation_count": normalize_int(raw.get("relegation_count", 0), 0, 0, 100),
        }
    item["tv_config"] = normalize_tv_config(
        item.get("tv_config"),
        item.get("tv_bracket_game_filter", "all"),
    )
    item["tv_bracket_game_filter"] = item["tv_config"]["bracket_game_filter"]
    return item


def save_config(data):
    current = get_config()
    division_count = normalize_int(data.get("division_count", current.get("division_count", 2)), 2, 1, 20)
    duration_minutes = normalize_int(data.get("duration_minutes", current.get("duration_minutes", 30)), 30, 5, 240)
    rules_in = data.get("rules", {}) or {}
    rules = {}
    for division in range(1, division_count + 1):
        old = (current.get("rules") or {}).get(str(division), {})
        raw = rules_in.get(str(division)) or rules_in.get(division) or old or {}
        rules[str(division)] = {
            "key_count": normalize_int(raw.get("key_count", old.get("key_count", 1)), 1, 1, 99),
            "promotion_count": normalize_int(raw.get("promotion_count", old.get("promotion_count", 0)), 0, 0, 100),
            "relegation_count": normalize_int(raw.get("relegation_count", old.get("relegation_count", 0)), 0, 0, 100),
        }
    current.update({
        "pk": "CONFIG",
        "sk": "TOURNAMENT",
        "type": "CONFIG",
        "division_count": division_count,
        "duration_minutes": duration_minutes,
        "show_bracket_scoreboard": normalize_bool(
            data.get("show_bracket_scoreboard"),
            current.get("show_bracket_scoreboard", True),
        ),
        "show_bracket_tv": normalize_bool(
            data.get("show_bracket_tv"),
            current.get("show_bracket_tv", True),
        ),
        "tv_bracket_game_filter": current.get("tv_config", {}).get(
            "bracket_game_filter",
            current.get("tv_bracket_game_filter", "all"),
        ),
        "rules": rules,
    })
    put_item(current)
    return current


def save_tv_config(data):
    current = get_config()
    current["tv_config"] = normalize_tv_config(
        data,
        current.get("tv_bracket_game_filter", "all"),
    )
    current["tv_bracket_game_filter"] = current["tv_config"]["bracket_game_filter"]
    put_item(current)
    return current["tv_config"]


def get_players():
    config = get_config()
    players = scan_type("PLAYER")
    normalized = []
    for p in players:
        division = normalize_int(p.get("division"), 1, 1, config["division_count"])
        chave = normalize_chave(p.get("chave", "A"))
        if chave not in available_chaves_for_division(config, division):
            chave = "A"
        p["division"] = division
        p["chave"] = chave
        p["competition_status"] = normalize_player_status(p.get("competition_status"))
        normalized.append(p)
    return sorted(normalized, key=lambda p: (p["division"], p["chave"], str(p.get("name", "")).lower()))


def get_rounds():
    rounds = scan_type("ROUND")
    for r in rounds:
        r["division"] = normalize_int(r.get("division"), 1, 1, 20)
        r["chave"] = normalize_chave(r.get("chave", "A"))
        r["round_number"] = normalize_int(r.get("round_number", 0), 0, 0, 999)
    return sorted(rounds, key=lambda r: (r.get("date", "9999-99-99"), r.get("start_time", "99:99"), r["division"], r["chave"], r["round_number"], r.get("name", "")))


def get_matches():
    matches = scan_type("MATCH")
    for match in matches:
        match["double_loss"] = bool(match.get("double_loss", False))
    return sorted(matches, key=lambda m: (m.get("date") or "9999-99-99", m.get("time") or "99:99", m.get("place_name", ""), m.get("round_number", 999), m.get("chave", "A")))


def match_passes_filters(match, filters):
    filters = filters or {}
    if filters.get("date") and str(match.get("date") or "") != str(filters["date"]):
        return False
    if filters.get("round") and str(match.get("round_id") or "") != str(filters["round"]):
        return False
    if filters.get("place") and str(match.get("place_id") or "") != str(filters["place"]):
        return False
    if filters.get("player") and str(filters["player"]) not in {
        str(match.get("player1_id") or ""),
        str(match.get("player2_id") or ""),
    }:
        return False
    if filters.get("division") and str(match.get("division") or "") != str(filters["division"]):
        return False
    if filters.get("chave") and normalize_chave(match.get("chave")) != normalize_chave(filters["chave"]):
        return False
    if filters.get("status") == "finished" and not match.get("is_finished"):
        return False
    if filters.get("status") == "pending" and match.get("is_finished"):
        return False
    return True


def filtered_matches(matches, filters):
    return [match for match in matches if match_passes_filters(match, filters)]


def tv_cycle_matches(matches, tv_config):
    filters = (tv_config or {}).get("filters") or {}
    if any(str(filters.get(key) or "").strip() for key in TV_FILTER_KEYS):
        selected = filtered_matches(matches, filters)
    else:
        finished = [match for match in matches if match.get("is_finished")]
        selected = sorted(
            finished,
            key=lambda match: str(
                match.get("result_saved_at")
                or match.get("updated_at")
                or match.get("created_at")
                or ""
            ),
            reverse=True,
        )[:20]
    return sorted(
        selected,
        key=lambda match: (
            match.get("date") or "9999-99-99",
            match.get("time") or "99:99",
            match.get("place_name") or "",
            normalize_int(match.get("round_number"), 999),
            match.get("match_id") or "",
        ),
    )


def get_results():
    results = scan_type("RESULT")
    for result in results:
        result["double_loss"] = bool(result.get("double_loss", False))
    return results


def get_tiebreak_decisions():
    if _table is None:
        return []
    return scan_type("TIEBREAK")


def derive_dates(matches, rounds):
    values = {}
    for item in list(rounds) + list(matches):
        date = str(item.get("date") or "")
        if date:
            values[date] = {"date": date, "date_id": date}
    return [values[k] for k in sorted(values)]


def derive_places(matches, rounds):
    values = {}
    for item in list(rounds) + list(matches):
        name = str(item.get("place_name") or item.get("name") or "").strip()
        if name:
            place_id = str(item.get("place_id") or name.lower())
            values[place_id] = {"place_id": place_id, "name": name}
    return sorted(values.values(), key=lambda p: p["name"].lower())


def group_players(players):
    grouped = {}
    for p in players:
        grouped.setdefault((normalize_int(p.get("division"), 1), normalize_chave(p.get("chave", "A"))), []).append(p)
    return grouped


def get_used_pair_map(include_pending=True):
    used = {}
    for m in get_matches():
        pair_key = str(m.get("pair_key") or build_pair_key(m.get("division"), m.get("chave"), m.get("player1_id"), m.get("player2_id")))
        if include_pending or m.get("is_finished"):
            status = "já aconteceu" if m.get("is_finished") else "já está cadastrado"
            used[pair_key] = {
                "pair_key": pair_key,
                "player1_id": m.get("player1_id"),
                "player1_name": m.get("player1_name"),
                "player2_id": m.get("player2_id"),
                "player2_name": m.get("player2_name"),
                "status": status,
                "round_name": m.get("round_name") or m.get("place_name") or "",
                "date": m.get("date") or "",
            }
    for r in get_results():
        if r.get("pair_key"):
            pair_key = str(r.get("pair_key"))
            used[pair_key] = {
                "pair_key": pair_key,
                "player1_id": r.get("player1_id"),
                "player1_name": r.get("player1_name"),
                "player2_id": r.get("player2_id"),
                "player2_name": r.get("player2_name"),
                "status": "já aconteceu",
                "round_name": r.get("round_name") or "resultado salvo",
                "date": r.get("date") or "",
            }
    return used


def get_used_pair_keys(include_pending=True):
    return set(get_used_pair_map(include_pending=include_pending).keys())


def all_pair_keys_for_group(group_players_list, division, chave):
    return {
        build_pair_key(division, chave, a["player_id"], b["player_id"])
        for a, b in combinations(group_players_list, 2)
    }


def total_rounds_needed(player_count):
    if player_count < 2:
        return 0
    return player_count - 1 if player_count % 2 == 0 else player_count


def matches_per_round(player_count):
    return max(0, player_count // 2)


def round_requirements(config, players, rounds, matches, results):
    grouped = group_players(players)
    used_pairs = set()
    for m in matches:
        if m.get("pair_key"):
            used_pairs.add(str(m.get("pair_key")))
    for r in results:
        if r.get("pair_key"):
            used_pairs.add(str(r.get("pair_key")))
    reqs = []
    for division in range(1, config["division_count"] + 1):
        for chave in available_chaves_for_division(config, division):
            ps = grouped.get((division, chave), [])
            total_pairs = len(ps) * (len(ps) - 1) // 2
            all_keys = all_pair_keys_for_group(ps, division, chave)
            remaining_keys = all_keys - used_pairs
            done_or_scheduled = len(all_keys) - len(remaining_keys)
            remaining_pairs = max(0, total_pairs - done_or_scheduled)
            per_round = matches_per_round(len(ps))
            pending_by_player = {str(player["player_id"]): 0 for player in ps}
            for first, second in combinations(ps, 2):
                pair_key = build_pair_key(division, chave, first["player_id"], second["player_id"])
                if pair_key in remaining_keys:
                    pending_by_player[str(first["player_id"])] += 1
                    pending_by_player[str(second["player_id"])] += 1
            capacity_rounds = 0 if per_round == 0 else (remaining_pairs + per_round - 1) // per_round
            player_rounds = max(pending_by_player.values(), default=0)
            missing_rounds = max(capacity_rounds, player_rounds)
            complete_rounds_remaining = 0 if per_round == 0 else remaining_pairs // per_round
            partial_round_games = 0 if per_round == 0 else remaining_pairs % per_round
            games_missing_to_full_round = 0
            if per_round and partial_round_games:
                games_missing_to_full_round = per_round - partial_round_games
            created_rounds = [r for r in rounds if normalize_int(r.get("division"), 1) == division and normalize_chave(r.get("chave", "A")) == chave]
            reqs.append({
                "division": division,
                "chave": chave,
                "players": len(ps),
                "total_pairs": total_pairs,
                "done_or_scheduled_pairs": done_or_scheduled,
                "remaining_pairs": remaining_pairs,
                "matches_per_round": per_round,
                "total_rounds_needed": total_rounds_needed(len(ps)),
                "created_rounds": len(created_rounds),
                "missing_rounds": missing_rounds,
                "complete_rounds_remaining": complete_rounds_remaining,
                "partial_round_games": partial_round_games,
                "games_missing_to_full_round": games_missing_to_full_round,
            })
    return reqs

def upsert_player(data):
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Informe o nome do jogador.")
    config = get_config()
    division = normalize_int(data.get("division", 1), 1, 1, config["division_count"])
    chave = normalize_chave(data.get("chave", "A"))
    if chave not in available_chaves_for_division(config, division):
        raise ValueError("Selecione uma chave disponível para essa divisão.")
    player_id = str(data.get("player_id") or data.get("id") or make_id("player"))

    for other in get_players():
        if other.get("player_id") != player_id and str(other.get("name", "")).strip().lower() == name.lower():
            raise ValueError("Já existe um jogador com esse nome. Escolha um nome único.")

    current = get_item("PLAYER", player_id) or {}
    item = {
        "pk": "PLAYER",
        "sk": player_id,
        "type": "PLAYER",
        "player_id": player_id,
        "name": name,
        "division": division,
        "chave": chave,
        "short_message": str(data.get("short_message", current.get("short_message", "")) or "").strip()[:160],
        "photo_url": current.get("photo_url", ""),
        "competition_status": normalize_player_status(current.get("competition_status")),
        "created_at": current.get("created_at") or data.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    photo_data_url = data.get("photo_data_url")
    if photo_data_url:
        item["photo_url"] = save_jpeg_media(
            photo_data_url,
            f"media/players/{player_id}/photo.jpg",
            current.get("photo_url", ""),
        )
    put_item(item)

    # Mantém nomes já exibidos nas partidas novas/pendentes quando o nome muda.
    if current and current.get("name") != name:
        for m in get_matches():
            changed = False
            if m.get("player1_id") == player_id:
                m["player1_name"] = name
                changed = True
            if m.get("player2_id") == player_id:
                m["player2_name"] = name
                changed = True
            if changed:
                put_item(m)
    return item


def result_item_for_match(match, saved_at=None):
    saved_at = saved_at or now_iso()
    return {
        "pk": "RESULT",
        "sk": str(match.get("pair_key") or ""),
        "type": "RESULT",
        "pair_key": str(match.get("pair_key") or ""),
        "division": match.get("division"),
        "chave": match.get("chave"),
        "player1_id": match.get("player1_id"),
        "player1_name": match.get("player1_name"),
        "player2_id": match.get("player2_id"),
        "player2_name": match.get("player2_name"),
        "winner_id": match.get("winner_id", ""),
        "balls_p1": match.get("balls_p1", 0),
        "balls_p2": match.get("balls_p2", 0),
        "is_finished": True,
        "double_loss": bool(match.get("double_loss")),
        "administrative_loss_player_ids": list(match.get("administrative_loss_player_ids") or []),
        "phase": match.get("phase", "group"),
        "bracket_id": match.get("bracket_id", ""),
        "bracket_display_name": match.get("bracket_display_name", ""),
        "bracket_node_id": match.get("bracket_node_id", ""),
        "bracket_round": match.get("bracket_round", 0),
        "bracket_match_kind": match.get("bracket_match_kind", ""),
        "created_at": saved_at,
        "result_saved_at": saved_at,
    }


def apply_disciplinary_result(match, players_by_id):
    participant_ids = (
        str(match.get("player1_id") or ""),
        str(match.get("player2_id") or ""),
    )
    sanctioned_ids = [
        player_id
        for player_id in participant_ids
        if is_disciplinary_player_status((players_by_id.get(player_id) or {}).get("competition_status"))
    ]
    if not sanctioned_ids:
        return False

    saved_at = now_iso()
    match["administrative_loss_player_ids"] = sanctioned_ids
    match["is_finished"] = True
    match["result_saved_at"] = saved_at
    match["updated_at"] = saved_at

    if len(sanctioned_ids) == 2:
        match["winner_id"] = ""
        match["balls_p1"] = 0
        match["balls_p2"] = 0
        match["double_loss"] = True
        return True

    losing_player_id = sanctioned_ids[0]
    match["winner_id"] = (
        match.get("player2_id")
        if losing_player_id == match.get("player1_id")
        else match.get("player1_id")
    )
    match["balls_p1"] = 0 if losing_player_id == match.get("player1_id") else 7
    match["balls_p2"] = 0 if losing_player_id == match.get("player2_id") else 7
    match["double_loss"] = False
    return True


def persist_disciplinary_result(match):
    put_item(match)
    put_item(result_item_for_match(match, match.get("result_saved_at")))


def disciplinary_players_for_match(match):
    players_by_id = {}
    for player_id in {str(match.get("player1_id") or ""), str(match.get("player2_id") or "")}:
        if player_id:
            players_by_id[player_id] = get_item("PLAYER", player_id) or {}
    return players_by_id


def set_player_status(data):
    player_id = str(data.get("player_id") or "")
    status = normalize_player_status(data.get("competition_status"))
    if not player_id:
        raise ValueError("Jogador não informado.")
    if status not in DISCIPLINARY_PLAYER_STATUSES:
        raise ValueError("Selecione desclassificado ou banido.")

    player = get_item("PLAYER", player_id)
    if not player:
        raise ValueError("Jogador não encontrado.")
    player["competition_status"] = status
    put_item(player)

    players_by_id = {player_id: player}
    affected_matches = 0
    for match in get_matches():
        participant_ids = {
            str(match.get("player1_id") or ""),
            str(match.get("player2_id") or ""),
        }
        if player_id not in participant_ids:
            continue
        opponent_ids = participant_ids - {player_id, ""}
        for opponent_id in opponent_ids:
            if opponent_id not in players_by_id:
                players_by_id[opponent_id] = get_item("PLAYER", opponent_id) or {}
        if apply_disciplinary_result(match, players_by_id):
            persist_disciplinary_result(match)
            affected_matches += 1
    return {"player": player, "affected_matches": affected_matches}


def delete_player(player_id):
    player_id = str(player_id or "")
    if not player_id:
        return
    for bracket in get_brackets():
        if any(str(item.get("player_id") or "") == player_id for item in bracket.get("qualifiers", [])):
            raise ValueError("Este jogador já faz parte de um chaveamento criado e não pode ser excluído.")
    current = get_item("PLAYER", player_id)
    if current:
        delete_media_url(current.get("photo_url", ""))
    delete_item("PLAYER", player_id)
    for m in get_matches():
        if m.get("player1_id") == player_id or m.get("player2_id") == player_id:
            if not m.get("is_finished"):
                delete_item("MATCH", m["sk"])


def next_round_number(division, chave):
    nums = [normalize_int(r.get("round_number"), 0) for r in get_rounds() if normalize_int(r.get("division"), 1) == division and normalize_chave(r.get("chave")) == chave]
    return (max(nums) if nums else 0) + 1


def result_for_pair(pair_key):
    return get_item("RESULT", pair_key)


def build_match_item(round_item, p1, p2, order_index):
    config = get_config()
    duration = config["duration_minutes"]
    start_min = time_to_minutes(round_item["start_time"]) + (order_index * duration)
    time_str = minutes_to_time(start_min)
    end_time = minutes_to_time(start_min + duration)
    pair_key = build_pair_key(round_item["division"], round_item["chave"], p1["player_id"], p2["player_id"])
    previous_result = result_for_pair(pair_key)
    match_id = make_id("match")
    item = {
        "pk": "MATCH",
        "sk": match_id,
        "type": "MATCH",
        "match_id": match_id,
        "pair_key": pair_key,
        "round_id": round_item["round_id"],
        "round_name": round_item["name"],
        "round_number": round_item["round_number"],
        "division": round_item["division"],
        "chave": round_item["chave"],
        "date": round_item["date"],
        "time": time_str,
        "end_time": end_time,
        "duration_minutes": duration,
        "place_id": round_item["place_id"],
        "place_name": round_item["place_name"],
        "player1_id": p1["player_id"],
        "player1_name": p1["name"],
        "player2_id": p2["player_id"],
        "player2_name": p2["name"],
        "winner_id": "",
        "balls_p1": 0,
        "balls_p2": 0,
        "is_finished": False,
        "double_loss": False,
        "created_at": now_iso(),
    }
    if previous_result:
        item["winner_id"] = previous_result.get("winner_id", "")
        item["balls_p1"] = previous_result.get("balls_p1", 0)
        item["balls_p2"] = previous_result.get("balls_p2", 0)
        item["is_finished"] = True
        item["double_loss"] = bool(previous_result.get("double_loss"))
    apply_disciplinary_result(item, {
        str(p1["player_id"]): p1,
        str(p2["player_id"]): p2,
    })
    return item


def validate_round_base(data):
    config = get_config()
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Informe o nome/local da rodada.")
    division = normalize_int(data.get("division", 1), 1, 1, config["division_count"])
    chave = normalize_chave(data.get("chave", "A"))
    if chave not in available_chaves_for_division(config, division):
        raise ValueError("Selecione uma chave disponível para essa divisão.")
    date = normalize_date(str(data.get("date", "")).strip())
    if not date:
        raise ValueError("Informe uma data válida.")
    start_time = normalize_time(str(data.get("start_time") or "09:00").strip(), "09:00")
    return {"name": name, "division": division, "chave": chave, "date": date, "start_time": start_time}


def players_for_group(division, chave):
    return [p for p in get_players() if normalize_int(p.get("division"), 1) == division and normalize_chave(p.get("chave")) == chave]


def find_automatic_pairs(players, division, chave, used_pairs, seed=None):
    if len(players) < 2:
        return []
    rng = random.Random(seed or time.time_ns())
    players = players[:]
    rng.shuffle(players)
    target = matches_per_round(len(players))
    best = []
    seen = {}

    def available_partners(player, remaining):
        return [
            other
            for other in remaining
            if other["player_id"] != player["player_id"]
            and build_pair_key(division, chave, player["player_id"], other["player_id"]) not in used_pairs
        ]

    def rec(remaining, pairs):
        nonlocal best
        if len(pairs) > len(best):
            best = pairs[:]
        if len(pairs) == target:
            return True
        if len(remaining) < 2:
            return False
        if len(pairs) + len(remaining) // 2 <= len(best):
            return False

        state = tuple(sorted(str(player["player_id"]) for player in remaining))
        if seen.get(state, -1) >= len(pairs):
            return False
        seen[state] = len(pairs)

        # Começar pelo jogador com menos opções reduz bastante a busca e,
        # numa rodada parcial, permite ignorar quem já enfrentou todos.
        first = min(remaining, key=lambda player: len(available_partners(player, remaining)))
        rest = [player for player in remaining if player["player_id"] != first["player_id"]]
        partners = available_partners(first, remaining)
        rng.shuffle(partners)
        for partner in partners:
            next_remaining = [p for p in rest if p["player_id"] != partner["player_id"]]
            if rec(next_remaining, pairs + [(first, partner)]):
                return True

        # Rodadas finais podem ser parciais mesmo com uma chave de tamanho par.
        # Portanto qualquer jogador sem confronto disponível pode ficar de fora.
        if rec(rest, pairs):
            return True
        return False

    rec(players, [])
    return best


def create_round(data, manual=False):
    base = validate_round_base(data)
    players = players_for_group(base["division"], base["chave"])
    if len(players) < 2:
        raise ValueError("Essa divisão/chave precisa ter pelo menos 2 competidores.")

    used_pair_map = get_used_pair_map(include_pending=True)
    used_pairs = set(used_pair_map.keys())
    seed = time.time_ns()
    skipped_conflicts = []
    if manual:
        raw_pairs = data.get("pairs") or []
        confirm_skip_existing = bool(data.get("confirm_skip_existing"))
        player_by_id = {p["player_id"]: p for p in players}
        pairs = []
        involved = set()
        seen_this_round = set()
        requested_valid_pairs = 0
        for raw in raw_pairs:
            p1_id = str(raw.get("player1_id") or "")
            p2_id = str(raw.get("player2_id") or "")
            if not p1_id and not p2_id:
                continue
            if not p1_id or not p2_id or p1_id == p2_id:
                raise ValueError("Preencha os dois lados de cada jogo manual e não repita o mesmo jogador no confronto.")
            if p1_id not in player_by_id or p2_id not in player_by_id:
                raise ValueError("A rodada manual contém jogador fora da divisão/chave selecionada.")
            if p1_id in involved or p2_id in involved:
                raise ValueError("Na mesma rodada, cada jogador só pode aparecer em um confronto.")
            involved.add(p1_id)
            involved.add(p2_id)
            pair_key = build_pair_key(base["division"], base["chave"], p1_id, p2_id)
            if pair_key in seen_this_round:
                raise ValueError("O mesmo confronto foi escolhido mais de uma vez nessa rodada.")
            seen_this_round.add(pair_key)
            requested_valid_pairs += 1
            if pair_key in used_pairs:
                detail = dict(used_pair_map.get(pair_key, {}))
                detail.update({
                    "pair_key": pair_key,
                    "player1_id": p1_id,
                    "player1_name": player_by_id[p1_id]["name"],
                    "player2_id": p2_id,
                    "player2_name": player_by_id[p2_id]["name"],
                    "status": detail.get("status") or "já aconteceu ou já está cadastrado",
                })
                skipped_conflicts.append(detail)
                continue
            pairs.append((player_by_id[p1_id], player_by_id[p2_id]))
        expected = matches_per_round(len(players))
        if requested_valid_pairs != expected:
            if len(players) % 2 == 1:
                raise ValueError(f"Essa chave precisa de {expected} confronto(s) nessa rodada, com 1 jogador de folga.")
            raise ValueError(f"Essa chave precisa de {expected} confronto(s) nessa rodada.")
        if skipped_conflicts and not confirm_skip_existing:
            raise RoundConflictError(skipped_conflicts)
        if not pairs:
            if skipped_conflicts:
                raise ValueError("Todos os jogos escolhidos já aconteceram ou já estão cadastrados. Nenhuma partida nova foi criada.")
            raise ValueError("Informe pelo menos um confronto válido para criar a rodada manual.")
    else:
        pairs = find_automatic_pairs(players, base["division"], base["chave"], used_pairs, seed)
        if not pairs:
            raise ValueError("Não há confrontos disponíveis sem repetir adversários nessa divisão/chave.")

    round_id = make_id("round")
    round_item = {
        "pk": "ROUND",
        "sk": round_id,
        "type": "ROUND",
        "round_id": round_id,
        "name": base["name"],
        "place_id": "round_place_" + hashlib.sha1(base["name"].lower().encode("utf-8")).hexdigest()[:10],
        "place_name": base["name"],
        "division": base["division"],
        "chave": base["chave"],
        "date": base["date"],
        "start_time": base["start_time"],
        "round_number": next_round_number(base["division"], base["chave"]),
        "mode": "manual" if manual else "automatic",
        "seed": seed,
        "created_at": now_iso(),
    }
    put_item(round_item)

    matches = []
    for idx, (p1, p2) in enumerate(pairs):
        match = build_match_item(round_item, p1, p2, idx)
        put_item(match)
        if match.get("administrative_loss_player_ids"):
            put_item(result_item_for_match(match, match.get("result_saved_at")))
        matches.append(match)
    return {"round": round_item, "matches": matches, "created": len(matches), "skipped_conflicts": skipped_conflicts, "skipped": len(skipped_conflicts)}


def update_round_name(data):
    round_id = str(data.get("round_id") or "")
    name = str(data.get("name") or "").strip()
    if not round_id:
        raise ValueError("Rodada não informada.")
    if not name:
        raise ValueError("Informe o novo nome/local da rodada.")
    round_item = get_item("ROUND", round_id)
    if not round_item:
        raise ValueError("Rodada não encontrada.")
    place_id = "round_place_" + hashlib.sha1(name.lower().encode("utf-8")).hexdigest()[:10]
    round_item["name"] = name
    round_item["place_id"] = place_id
    round_item["place_name"] = name
    put_item(round_item)
    updated_matches = 0
    for match in get_matches():
        if str(match.get("round_id")) == round_id:
            match["round_name"] = name
            match["place_id"] = place_id
            match["place_name"] = name
            put_item(match)
            updated_matches += 1
    return {"round": round_item, "updated_matches": updated_matches}


def delete_round(round_id):
    round_id = str(round_id or "")
    if not round_id:
        return {"deleted_pending_matches": 0, "preserved_finished_matches": 0}
    round_item = get_item("ROUND", round_id)
    if round_item and round_item.get("phase") == "knockout":
        bracket = get_bracket_by_id(round_item.get("bracket_id")) or get_bracket(round_item.get("division"))
        round_matches = [
            match for match in get_matches()
            if str(match.get("round_id") or "") == round_id
        ]
        descendant_ids = set()
        for match in round_matches:
            if bracket:
                descendant_ids.update(knockout_descendant_node_ids(match, bracket))

        related_matches = [
            match for match in get_matches()
            if match.get("phase") == "knockout"
            and match.get("bracket_id") == round_item.get("bracket_id")
            and (
                normalize_int(round_item.get("bracket_round"), 0) == 1
                or
                str(match.get("round_id") or "") == round_id
                or match.get("bracket_node_id") in descendant_ids
            )
        ]
        affected_round_ids = {str(match.get("round_id") or "") for match in related_matches}
        for match in related_matches:
            if match.get("pair_key"):
                delete_item("RESULT", str(match["pair_key"]))
            delete_item("MATCH", match["sk"])
        for affected_round_id in affected_round_ids:
            if affected_round_id:
                delete_item("ROUND", affected_round_id)

        remaining = [
            match for match in get_matches()
            if match.get("phase") == "knockout"
            and match.get("bracket_id") == round_item.get("bracket_id")
        ]
        bracket_unfrozen = False
        if not remaining and bracket and bracket_kind(bracket) == "division":
            delete_item("BRACKET", bracket["sk"])
            bracket_unfrozen = True
        return {
            "deleted_knockout_matches": len(related_matches),
            "deleted_pending_matches": len([match for match in related_matches if not match.get("is_finished")]),
            "deleted_finished_matches": len([match for match in related_matches if match.get("is_finished")]),
            "preserved_finished_matches": 0,
            "bracket_unfrozen": bracket_unfrozen,
        }

    delete_item("ROUND", round_id)
    deleted = 0
    preserved = 0
    for m in get_matches():
        if str(m.get("round_id")) != round_id:
            continue
        if m.get("is_finished"):
            preserved += 1
            m["round_deleted"] = True
            put_item(m)
        else:
            delete_item("MATCH", m["sk"])
            deleted += 1
    return {"deleted_pending_matches": deleted, "preserved_finished_matches": preserved}


def set_match_result(data):
    match_id = str(data.get("match_id", ""))
    match = get_item("MATCH", match_id)
    if not match:
        raise ValueError("Partida não encontrada.")
    pair_key = str(match.get("pair_key") or build_pair_key(match.get("division"), match.get("chave"), match.get("player1_id"), match.get("player2_id")))
    if apply_disciplinary_result(match, disciplinary_players_for_match(match)):
        persist_disciplinary_result(match)
        return match
    if data.get("clear"):
        if match.get("phase") == "knockout" and match.get("is_finished"):
            invalidate_pending_knockout_descendants(match)
        match["winner_id"] = ""
        match["balls_p1"] = 0
        match["balls_p2"] = 0
        match["is_finished"] = False
        match["double_loss"] = False
        match["updated_at"] = now_iso()
        match["result_saved_at"] = ""
        put_item(match)
        delete_item("RESULT", pair_key)
        return match
    double_loss = bool(data.get("double_loss"))
    if match.get("phase") == "knockout" and double_loss:
        raise ValueError("No chaveamento é necessário selecionar um vencedor.")
    winner_id = "" if double_loss else str(data.get("winner_id", ""))
    if not double_loss and winner_id not in [match.get("player1_id"), match.get("player2_id")]:
        raise ValueError("Selecione o vencedor ou marque derrota para ambos.")
    balls_p1 = 0 if double_loss else normalize_int(data.get("balls_p1", 0), 0, 0, 7)
    balls_p2 = 0 if double_loss else normalize_int(data.get("balls_p2", 0), 0, 0, 7)
    if not double_loss and winner_id == match.get("player1_id"):
        balls_p1 = 7
    if not double_loss and winner_id == match.get("player2_id"):
        balls_p2 = 7
    if (
        match.get("phase") == "knockout"
        and match.get("is_finished")
        and match.get("winner_id")
        and match.get("winner_id") != winner_id
    ):
        invalidate_pending_knockout_descendants(match)
    saved_at = now_iso()
    match["winner_id"] = winner_id
    match["balls_p1"] = balls_p1
    match["balls_p2"] = balls_p2
    match["is_finished"] = True
    match["double_loss"] = double_loss
    match["result_saved_at"] = saved_at
    match["updated_at"] = saved_at
    put_item(match)
    put_item(result_item_for_match(match, saved_at))
    return match


def tiebreak_decision_id(division, chave, player_ids):
    raw = "|".join([
        str(normalize_int(division, 1)),
        normalize_chave(chave),
        *sorted(str(player_id) for player_id in player_ids),
    ])
    return "TIEBREAK#" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def group_tiebreak_signature(rows, group_results):
    payload = {
        "players": sorted([
            {
                "player_id": row.get("player_id"),
                "points": row.get("points", 0),
                "wins": row.get("wins", 0),
                "balls_for": row.get("balls_for", 0),
                "balls_against": row.get("balls_against", 0),
                "balls_balance": row.get("balls_balance", 0),
                "competition_status": row.get("competition_status", PLAYER_STATUS_ACTIVE),
            }
            for row in rows
        ], key=lambda item: str(item["player_id"])),
        "results": sorted([
            {
                "pair_key": item.get("pair_key"),
                "winner_id": item.get("winner_id", ""),
                "balls_p1": normalize_int(item.get("balls_p1"), 0, 0, 7),
                "balls_p2": normalize_int(item.get("balls_p2"), 0, 0, 7),
                "double_loss": bool(item.get("double_loss")),
            }
            for item in group_results
        ], key=lambda item: str(item["pair_key"])),
    }
    serialized = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()


def provisional_tiebreak_sort(rows):
    return sorted(
        rows,
        key=lambda row: (
            -normalize_int(row.get("balls_balance"), 0),
            -normalize_int(row.get("balls_for"), 0),
            -normalize_int(row.get("wins"), 0),
            str(row.get("name", "")).lower(),
        ),
    )


def resolve_points_tie(
    rows,
    result_by_pair,
    division,
    chave,
    group_complete,
    context_signature,
    decisions_by_id,
):
    direct_checks = []
    manual_groups = []
    balance_used = False
    pending_direct = False

    def resolve_subset(subset):
        nonlocal balance_used, pending_direct
        if len(subset) < 2:
            return list(subset)

        direct_results = []
        missing_pairs = []
        for first, second in combinations(subset, 2):
            pair_key = build_pair_key(
                division,
                chave,
                first["player_id"],
                second["player_id"],
            )
            result = result_by_pair.get(pair_key)
            if not result or not result.get("is_finished"):
                missing_pairs.append(pair_key)
            else:
                direct_results.append(result)

        if missing_pairs:
            pending_direct = True
            direct_checks.append({
                "player_ids": [row["player_id"] for row in subset],
                "status": "pending",
                "scores": [],
                "missing_games": len(missing_pairs),
            })
            return provisional_tiebreak_sort(subset)

        scores = {str(row["player_id"]): 0 for row in subset}
        for result in direct_results:
            winner_id = str(result.get("winner_id") or "")
            if winner_id in scores and not result.get("double_loss"):
                scores[winner_id] += 3

        score_groups = {}
        for row in subset:
            score_groups.setdefault(scores[str(row["player_id"])], []).append(row)
        direct_checks.append({
            "player_ids": [row["player_id"] for row in subset],
            "status": "tied" if len(score_groups) == 1 else "resolved",
            "scores": [
                {
                    "player_id": row["player_id"],
                    "name": row.get("name", ""),
                    "points": scores[str(row["player_id"])],
                }
                for row in sorted(
                    subset,
                    key=lambda item: (
                        -scores[str(item["player_id"])],
                        str(item.get("name", "")).lower(),
                    ),
                )
            ],
            "missing_games": 0,
        })

        if len(score_groups) > 1:
            ordered = []
            for score in sorted(score_groups, reverse=True):
                tied_score_rows = score_groups[score]
                ordered.extend(
                    resolve_subset(tied_score_rows)
                    if len(tied_score_rows) > 1
                    else tied_score_rows
                )
            return ordered

        balance_used = True
        balance_groups = {}
        for row in subset:
            balance_groups.setdefault(normalize_int(row.get("balls_balance"), 0), []).append(row)

        ordered = []
        for balance in sorted(balance_groups, reverse=True):
            balance_rows = balance_groups[balance]
            if len(balance_rows) == 1:
                ordered.extend(balance_rows)
                continue

            player_ids = [str(row["player_id"]) for row in balance_rows]
            decision_id = tiebreak_decision_id(division, chave, player_ids)
            saved = decisions_by_id.get(decision_id) or {}
            saved_order = [str(player_id) for player_id in saved.get("ordered_player_ids", [])]
            saved_is_current = (
                saved.get("context_signature") == context_signature
                and len(saved_order) == len(player_ids)
                and set(saved_order) == set(player_ids)
            )
            default_order = provisional_tiebreak_sort(balance_rows)
            if len({normalize_int(row.get("balls_balance"), 0) for row in balance_rows}) == 1:
                default_order = sorted(
                    balance_rows,
                    key=lambda row: str(row.get("name", "")).lower(),
                )
            row_by_id = {str(row["player_id"]): row for row in balance_rows}
            if saved_is_current:
                resolved_rows = [row_by_id[player_id] for player_id in saved_order]
            else:
                resolved_rows = default_order
                if group_complete:
                    for row in resolved_rows:
                        row["tiebreak_pending"] = True

            manual_groups.append({
                "decision_id": decision_id,
                "player_ids": player_ids,
                "players": [
                    {
                        "player_id": row["player_id"],
                        "name": row.get("name", ""),
                        "balls_balance": row.get("balls_balance", 0),
                    }
                    for row in default_order
                ],
                "ordered_player_ids": saved_order if saved_is_current else [],
                "context_signature": context_signature,
                "status": (
                    "resolved"
                    if saved_is_current
                    else "required"
                    if group_complete
                    else "waiting_group"
                ),
            })
            ordered.extend(resolved_rows)
        return ordered

    ordered_rows = resolve_subset(rows)
    unresolved_manual = any(item["status"] == "required" for item in manual_groups)
    waiting_group = any(item["status"] == "waiting_group" for item in manual_groups)
    resolved_manual = any(item["status"] == "resolved" for item in manual_groups)
    if pending_direct:
        resolution = "pending_direct"
        reason = "Há confrontos diretos pendentes; a ordem exibida ainda é provisória."
    elif waiting_group:
        resolution = "waiting_group"
        reason = "Confronto direto e saldo seguem iguais; aguarde a conclusão dos jogos da chave."
    elif unresolved_manual:
        resolution = "manual_required"
        reason = "Confronto direto e saldo de bolas terminaram iguais. É necessário um novo confronto de desempate e registrar a ordem final."
    elif resolved_manual:
        resolution = "manual"
        reason = "A ordem foi definida no painel de desempate após o novo confronto."
    elif balance_used:
        resolution = "balls_balance"
        reason = "O confronto direto terminou empatado ou circular; o saldo de bolas decidiu a ordem."
    else:
        resolution = "direct"
        reason = "O confronto direto decidiu a ordem."

    return ordered_rows, {
        "division": normalize_int(division, 1),
        "chave": normalize_chave(chave),
        "points": normalize_int(rows[0].get("points"), 0) if rows else 0,
        "player_ids": [str(row["player_id"]) for row in rows],
        "players": [
            {
                "player_id": row["player_id"],
                "name": row.get("name", ""),
                "points": row.get("points", 0),
                "balls_balance": row.get("balls_balance", 0),
            }
            for row in ordered_rows
        ],
        "resolution": resolution,
        "reason": reason,
        "direct_checks": direct_checks,
        "manual_groups": manual_groups,
        "context_signature": context_signature,
    }


def calculate_standings_details(players, matches, results, config, tiebreak_decisions=None):
    table = {}
    for p in players:
        pid = p["player_id"]
        table[pid] = {
            "player_id": pid,
            "name": p.get("name", ""),
            "short_message": p.get("short_message", ""),
            "photo_url": p.get("photo_url", ""),
            "slug": slugify_name(p.get("name", "")),
            "profile_url": player_profile_url(p),
            "division": normalize_int(p.get("division"), 1),
            "chave": normalize_chave(p.get("chave", "A")),
            "played": 0,
            "wins": 0,
            "losses": 0,
            "points": 0,
            "balls_for": 0,
            "balls_against": 0,
            "balls_balance": 0,
            "rank_status": "normal",
            "competition_status": normalize_player_status(p.get("competition_status")),
        }

    result_by_pair = {}
    for r in results:
        if r.get("pair_key") and r.get("phase") != "knockout":
            result_by_pair[str(r.get("pair_key"))] = r
    for m in matches:
        if m.get("is_finished") and m.get("pair_key") and m.get("phase") != "knockout":
            result_by_pair[str(m.get("pair_key"))] = m

    for item in result_by_pair.values():
        p1 = table.get(item.get("player1_id"))
        p2 = table.get(item.get("player2_id"))
        if not p1 or not p2:
            continue
        balls_p1 = normalize_int(item.get("balls_p1", 0), 0, 0, 7)
        balls_p2 = normalize_int(item.get("balls_p2", 0), 0, 0, 7)
        p1["played"] += 1
        p2["played"] += 1
        p1["balls_for"] += balls_p1
        p1["balls_against"] += balls_p2
        p2["balls_for"] += balls_p2
        p2["balls_against"] += balls_p1
        if item.get("double_loss"):
            p1["losses"] += 1
            p2["losses"] += 1
        elif item.get("winner_id") == item.get("player1_id"):
            p1["wins"] += 1
            p1["points"] += 3
            p2["losses"] += 1
        elif item.get("winner_id") == item.get("player2_id"):
            p2["wins"] += 1
            p2["points"] += 3
            p1["losses"] += 1

    grouped = {str(d): {} for d in range(1, config["division_count"] + 1)}
    for row in table.values():
        row["balls_balance"] = row["balls_for"] - row["balls_against"]
        grouped.setdefault(str(row["division"]), {}).setdefault(row["chave"], []).append(row)

    decisions_by_id = {
        str(item.get("tiebreak_id") or item.get("sk") or ""): item
        for item in (tiebreak_decisions or [])
    }
    tiebreaks = []
    rules = config.get("rules", {}) or {}
    for division_str, chaves in grouped.items():
        rule = rules.get(str(division_str), {})
        promotion_count = normalize_int(rule.get("promotion_count", 0), 0, 0, 100)
        relegation_count = normalize_int(rule.get("relegation_count", 0), 0, 0, 100)
        for chave, rows in chaves.items():
            division = normalize_int(division_str, 1)
            group_results = [
                item
                for item in result_by_pair.values()
                if normalize_int(item.get("division"), 1) == division
                and normalize_chave(item.get("chave")) == normalize_chave(chave)
            ]
            context_signature = group_tiebreak_signature(rows, group_results)
            expected_pairs = {
                build_pair_key(division, chave, first["player_id"], second["player_id"])
                for first, second in combinations(rows, 2)
            }
            group_complete = expected_pairs.issubset(set(result_by_pair))

            rows_by_points = {}
            for row in rows:
                rows_by_points.setdefault(normalize_int(row.get("points"), 0), []).append(row)
            ordered_rows = []
            for points in sorted(rows_by_points, reverse=True):
                points_rows = rows_by_points[points]
                if len(points_rows) == 1:
                    ordered_rows.extend(points_rows)
                    continue
                resolved_rows, detail = resolve_points_tie(
                    points_rows,
                    result_by_pair,
                    division,
                    chave,
                    group_complete,
                    context_signature,
                    decisions_by_id,
                )
                ordered_rows.extend(resolved_rows)
                tiebreaks.append(detail)
            rows[:] = ordered_rows
            for index, row in enumerate(rows):
                row["group_rank"] = index + 1
            for row in rows[:promotion_count]:
                row["rank_status"] = "promotion"
            if relegation_count:
                for row in rows[-relegation_count:]:
                    if row["rank_status"] != "promotion":
                        row["rank_status"] = "relegation"
            for row in rows:
                if row.get("tiebreak_pending"):
                    row["rank_status"] = "tiebreak_pending"
                if row["competition_status"] in DISCIPLINARY_PLAYER_STATUSES:
                    row["rank_status"] = row["competition_status"]
    return {
        "standings": grouped,
        "tiebreaks": tiebreaks,
    }


def calculate_standings(players, matches, results, config, tiebreak_decisions=None):
    return calculate_standings_details(
        players,
        matches,
        results,
        config,
        tiebreak_decisions,
    )["standings"]


def save_tiebreak_decision(data):
    decision_id = str(data.get("decision_id") or "")
    if not decision_id:
        raise ValueError("Desempate não informado.")

    players = get_players()
    matches = get_matches()
    results = get_results()
    config = get_config()
    decisions = get_tiebreak_decisions()
    details = calculate_standings_details(
        players,
        matches,
        results,
        config,
        decisions,
    )
    parent = None
    issue = None
    for tiebreak in details["tiebreaks"]:
        for manual_group in tiebreak.get("manual_groups", []):
            if manual_group.get("decision_id") == decision_id:
                parent = tiebreak
                issue = manual_group
                break
        if issue:
            break
    if not issue or issue.get("status") == "waiting_group":
        raise ValueError("Este desempate não está disponível para decisão manual.")

    player_ids = [str(player_id) for player_id in issue.get("player_ids", [])]
    ordered_player_ids = [
        str(player_id)
        for player_id in data.get("ordered_player_ids", [])
        if str(player_id)
    ]
    winner_id = str(data.get("winner_id") or "")
    if len(player_ids) == 2 and winner_id:
        ordered_player_ids = [winner_id] + [
            player_id for player_id in player_ids if player_id != winner_id
        ]
    if (
        len(ordered_player_ids) != len(player_ids)
        or set(ordered_player_ids) != set(player_ids)
    ):
        raise ValueError("Informe cada jogador uma única vez na ordem final do desempate.")

    saved_at = now_iso()
    item = {
        "pk": "TIEBREAK",
        "sk": decision_id,
        "type": "TIEBREAK",
        "tiebreak_id": decision_id,
        "division": parent.get("division"),
        "chave": parent.get("chave"),
        "points": parent.get("points"),
        "player_ids": player_ids,
        "ordered_player_ids": ordered_player_ids,
        "context_signature": issue.get("context_signature"),
        "reason": parent.get("reason", ""),
        "created_at": saved_at,
    }
    put_item(item)
    return item


def get_brackets():
    if _table is None:
        return []
    brackets = scan_type("BRACKET")
    return sorted(brackets, key=lambda item: (
        1 if bracket_kind(item) == "custom" else 0,
        normalize_int(item.get("division"), 1),
        str(item.get("display_name") or "").lower(),
        str(item.get("bracket_id") or ""),
    ))


def get_bracket(division):
    return get_item("BRACKET", f"DIVISION#{normalize_int(division, 1)}")


def bracket_kind(bracket):
    return "custom" if str((bracket or {}).get("bracket_kind") or "").lower() == "custom" else "division"


def bracket_display_name(bracket):
    return str((bracket or {}).get("display_name") or "").strip()


def get_bracket_by_id(bracket_id):
    bracket_id = str(bracket_id or "")
    if not bracket_id:
        return None
    for bracket in get_brackets():
        if str(bracket.get("bracket_id") or "") == bracket_id:
            return bracket
    return None


def bracket_has_created_rounds(bracket_id):
    bracket_id = str(bracket_id or "")
    if not bracket_id:
        return False
    if any(
        item.get("phase") == "knockout"
        and str(item.get("bracket_id") or "") == bracket_id
        for item in get_rounds()
    ):
        return True
    return any(
        item.get("phase") == "knockout"
        and str(item.get("bracket_id") or "") == bracket_id
        for item in get_matches()
    )


def assert_bracket_editable(bracket_id):
    if bracket_has_created_rounds(bracket_id):
        raise ValueError(
            "Este chaveamento ja possui rodada criada. Limpe os resultados e exclua a rodada de chaveamento antes de editar ou limpar a chave."
        )


def next_power_of_two(value):
    size = 1
    while size < max(2, normalize_int(value, 2)):
        size *= 2
    return size


def division_group_phase_complete(division, players, matches, results, config):
    division = normalize_int(division, 1)
    grouped = group_players(players)
    finished_pairs = set()
    for item in list(results) + list(matches):
        if item.get("phase") == "knockout" or not item.get("is_finished"):
            continue
        if item.get("pair_key"):
            finished_pairs.add(str(item["pair_key"]))

    has_players = False
    for chave in available_chaves_for_division(config, division):
        group = grouped.get((division, chave), [])
        if group:
            has_players = True
        required = all_pair_keys_for_group(group, division, chave)
        if not required.issubset(finished_pairs):
            return False
    return has_players


def qualifier_sort_key(row):
    return (
        normalize_int(row.get("group_rank"), 999),
        -normalize_int(row.get("points"), 0),
        -normalize_int(row.get("balls_balance"), 0),
        -normalize_int(row.get("balls_for"), 0),
        -normalize_int(row.get("wins"), 0),
        normalize_chave(row.get("chave")),
        str(row.get("name", "")).lower(),
    )


def division_qualifiers(division, standings):
    qualifiers = []
    chaves = (standings or {}).get(str(normalize_int(division, 1)), {}) or {}
    if any(
        row.get("rank_status") == "tiebreak_pending"
        for rows in chaves.values()
        for row in rows
    ):
        raise ValueError("Resolva os desempates pendentes antes de criar o chaveamento.")
    for chave in sorted(chaves):
        for index, row in enumerate(chaves[chave]):
            if row.get("rank_status") != "promotion":
                continue
            item = dict(row)
            item["chave"] = normalize_chave(chave)
            item["group_rank"] = normalize_int(item.get("group_rank"), index + 1, 1)
            qualifiers.append(item)
    qualifiers.sort(key=qualifier_sort_key)
    for seed, item in enumerate(qualifiers, start=1):
        item["seed"] = seed
    return qualifiers


def pair_qualifiers_cross_group(qualifiers):
    remaining = list(qualifiers)
    pairs = []
    while len(remaining) >= 2:
        strongest = remaining.pop(0)
        opponent_index = len(remaining) - 1
        for index in range(len(remaining) - 1, -1, -1):
            if normalize_chave(remaining[index].get("chave")) != normalize_chave(strongest.get("chave")):
                opponent_index = index
                break
        weakest = remaining.pop(opponent_index)
        pairs.append((strongest, weakest))
    return pairs


def qualifier_bracket_order_key(qualifier):
    return (
        normalize_chave(qualifier.get("chave")),
        normalize_int(qualifier.get("group_rank"), 999, 1),
        normalize_int(qualifier.get("seed"), 999, 1),
        str(qualifier.get("name", "")).lower(),
    )


def bracket_entry_order_key(entry, chaves):
    ranks_by_chave = {}
    for qualifier in entry:
        chave = normalize_chave(qualifier.get("chave"))
        rank = normalize_int(qualifier.get("group_rank"), 999, 1)
        ranks_by_chave[chave] = min(rank, ranks_by_chave.get(chave, rank))
    return (
        *(ranks_by_chave.get(chave, 999) for chave in chaves),
        min((normalize_int(item.get("seed"), 999, 1) for item in entry), default=999),
    )


def bracket_slots_for_qualifiers(qualifiers):
    bracket_size = next_power_of_two(len(qualifiers))
    first_round_nodes = bracket_size // 2
    bye_count = bracket_size - len(qualifiers)
    byes = list(qualifiers[:bye_count])
    playing = list(qualifiers[bye_count:])
    pairs = pair_qualifiers_cross_group(playing)
    chaves = sorted({normalize_chave(item.get("chave")) for item in qualifiers})
    entries = [[bye] for bye in byes] + [list(pair) for pair in pairs]
    for entry in entries:
        entry.sort(key=qualifier_bracket_order_key)
    entries.sort(key=lambda entry: bracket_entry_order_key(entry, chaves))

    entries = entries[:first_round_nodes]
    while len(entries) < first_round_nodes:
        entries.append([])
    slots = []
    for entry in entries:
        player_ids = [str(item.get("player_id") or "") for item in entry[:2]]
        player_ids.extend([""] * (2 - len(player_ids)))
        slots.extend(player_ids)
    return bracket_size, slots


def build_bracket_spec(division, standings):
    qualifiers = division_qualifiers(division, standings)
    if len(qualifiers) < 2:
        raise ValueError("Essa divisão precisa ter pelo menos 2 classificados em verde para criar o chaveamento.")
    bracket_size, slots = bracket_slots_for_qualifiers(qualifiers)
    bracket_id = f"bracket_division_{normalize_int(division, 1)}"
    return {
        "pk": "BRACKET",
        "sk": f"DIVISION#{normalize_int(division, 1)}",
        "type": "BRACKET",
        "bracket_id": bracket_id,
        "bracket_kind": "division",
        "division": normalize_int(division, 1),
        "display_name": "",
        "manual_override": False,
        "participant_count": len(qualifiers),
        "bracket_size": bracket_size,
        "qualifiers": [{
            "player_id": item.get("player_id"),
            "name": item.get("name", ""),
            "photo_url": item.get("photo_url", ""),
            "profile_url": item.get("profile_url", ""),
            "chave": item.get("chave", "A"),
            "group_rank": item.get("group_rank", 0),
            "seed": item.get("seed", 0),
        } for item in qualifiers],
        "slots": slots,
        "created_at": now_iso(),
    }


def bracket_stage_name(round_number, total_rounds):
    distance = total_rounds - round_number
    if distance == 0:
        return "Final"
    if distance == 1:
        return "Semifinal"
    if distance == 2:
        return "Quartas de final"
    if distance == 3:
        return "Oitavas de final"
    return f"{round_number}ª fase"


def bracket_source_pairs(source_count):
    source_count = normalize_int(source_count, 0, 0)
    if source_count < 2:
        return []
    if source_count == 2:
        return [(0, 1)]
    if source_count == 4:
        return [(0, 3), (1, 2)]
    # Aumenta o salto com o tamanho da chave e reaplica a regra nas fases seguintes.
    offset = (source_count // 2) - 1
    return [
        (source_index, (source_index + offset) % source_count)
        for source_index in range(0, source_count, 2)
    ]


def standard_seed_order(size):
    size = next_power_of_two(size)
    order = [0, 1]
    while len(order) < size:
        next_size = len(order) * 2
        order = [
            value
            for seed in order
            for value in (seed, next_size - 1 - seed)
        ]
    return order[:size]


def bracket_round_source_pairs(bracket, target_round_number, source_count):
    chaves = {
        normalize_chave(item.get("chave"))
        for item in bracket.get("qualifiers", [])
        if item.get("player_id")
    }
    if len(chaves) == 1:
        if target_round_number == 2:
            order = standard_seed_order(source_count)
            return [
                (order[index], order[index + 1])
                for index in range(0, len(order), 2)
            ]
        return [
            (source_index, source_index + 1)
            for source_index in range(0, source_count, 2)
        ]
    return bracket_source_pairs(source_count)


def bracket_source_indices_for_node(bracket, target_round_number, target_node_index, source_count):
    source_pairs = bracket_round_source_pairs(
        bracket,
        target_round_number,
        source_count,
    )
    if target_node_index < 0 or target_node_index >= len(source_pairs):
        return ()
    source_indices = source_pairs[target_node_index]
    if target_round_number == 2:
        first_round_order = bracket_first_round_node_order(bracket)
        source_indices = tuple(
            first_round_order[source_index]
            for source_index in source_indices
            if source_index < len(first_round_order)
        )
    return source_indices


def bracket_layout_indices(bracket, bracket_size):
    bracket_size = next_power_of_two(bracket_size)
    total_rounds = max(1, bracket_size.bit_length() - 1)
    children_by_node = {}
    for round_number in range(2, total_rounds + 1):
        node_count = bracket_size // (2 ** round_number)
        source_count = bracket_size // (2 ** (round_number - 1))
        for node_index in range(node_count):
            children_by_node[(round_number, node_index)] = [
                (round_number - 1, source_index)
                for source_index in bracket_source_indices_for_node(
                    bracket,
                    round_number,
                    node_index,
                    source_count,
                )
            ]

    orders = {round_number: [] for round_number in range(1, total_rounds + 1)}

    def visit(node):
        round_number, _node_index = node
        for child in children_by_node.get(node, []):
            visit(child)
        orders[round_number].append(node)

    visit((total_rounds, 0))
    return {
        node: layout_index
        for round_nodes in orders.values()
        for layout_index, node in enumerate(round_nodes)
    }


def bracket_first_round_node_order(bracket):
    bracket_size = next_power_of_two(bracket.get("bracket_size") or len(bracket.get("slots", [])))
    slots = [str(value or "") for value in bracket.get("slots", [])]
    slots.extend([""] * max(0, bracket_size - len(slots)))
    qualifiers = {
        str(item.get("player_id") or ""): item
        for item in bracket.get("qualifiers", [])
        if item.get("player_id")
    }
    chaves = sorted({
        normalize_chave(item.get("chave"))
        for item in qualifiers.values()
    })
    entries = []
    for node_index in range(bracket_size // 2):
        player_ids = slots[node_index * 2:node_index * 2 + 2]
        entry = [qualifiers[player_id] for player_id in player_ids if player_id in qualifiers]
        entries.append((node_index, entry))
    entries.sort(key=lambda item: (
        bracket_entry_order_key(item[1], chaves),
        item[0],
    ))
    return [node_index for node_index, _entry in entries]


def bracket_player_map(bracket, players):
    player_map = {str(player.get("player_id")): clean_public_player(player) for player in players}
    for qualifier in bracket.get("qualifiers", []):
        player_id = str(qualifier.get("player_id") or "")
        if player_id and player_id not in player_map:
            player_map[player_id] = clean_public_player(qualifier)
    return player_map


def build_bracket_view(bracket, players, matches, group_phase_complete=True, is_preview=False):
    bracket_size = next_power_of_two(bracket.get("bracket_size") or len(bracket.get("slots", [])))
    total_rounds = max(1, bracket_size.bit_length() - 1)
    bracket_id = str(bracket.get("bracket_id") or "")
    player_map = bracket_player_map(bracket, players)
    match_map = {
        str(match.get("bracket_node_id")): match
        for match in matches
        if match.get("phase") == "knockout"
        and str(match.get("bracket_id") or "") == bracket_id
        and match.get("bracket_node_id")
    }
    slots = [str(value or "") for value in bracket.get("slots", [])]
    slots.extend([""] * max(0, bracket_size - len(slots)))
    layout_indices = bracket_layout_indices(bracket, bracket_size)
    resolved_nodes = {}
    rounds = []

    for round_number in range(1, total_rounds + 1):
        node_count = bracket_size // (2 ** round_number)
        round_nodes = []
        for node_index in range(node_count):
            node_id = f"R{round_number}M{node_index}"
            source_node_ids = []
            if round_number == 1:
                side_states = []
                for slot_index in (node_index * 2, node_index * 2 + 1):
                    player_id = slots[slot_index] if slot_index < len(slots) else ""
                    side_states.append(("resolved", player_id) if player_id else ("empty", ""))
            else:
                previous_node_count = bracket_size // (2 ** (round_number - 1))
                source_indices = bracket_source_indices_for_node(
                    bracket,
                    round_number,
                    node_index,
                    previous_node_count,
                )
                source_node_ids = [
                    f"R{round_number - 1}M{source_index}"
                    for source_index in source_indices
                ]
                first_source = resolved_nodes[source_node_ids[0]]
                second_source = resolved_nodes[source_node_ids[1]]
                side_states = [
                    (first_source["outcome_status"], first_source["outcome_player_id"]),
                    (second_source["outcome_status"], second_source["outcome_player_id"]),
                ]

            player_ids = [
                player_id if status == "resolved" else ""
                for status, player_id in side_states
            ]
            match = match_map.get(node_id)
            if match and match.get("is_finished") and match.get("winner_id"):
                outcome_status = "resolved"
                outcome_player_id = str(match.get("winner_id"))
                node_status = "finished"
            elif side_states[0][0] == "resolved" and side_states[1][0] == "empty":
                outcome_status = "resolved"
                outcome_player_id = player_ids[0]
                node_status = "bye"
            elif side_states[1][0] == "resolved" and side_states[0][0] == "empty":
                outcome_status = "resolved"
                outcome_player_id = player_ids[1]
                node_status = "bye"
            elif side_states[0][0] == "empty" and side_states[1][0] == "empty":
                outcome_status = "empty"
                outcome_player_id = ""
                node_status = "empty"
            else:
                outcome_status = "pending"
                outcome_player_id = ""
                node_status = "pending"

            participants = []
            for side, player_id in enumerate(player_ids, start=1):
                slot_state = "unknown"
                if player_id:
                    if node_status == "finished":
                        slot_state = "winner" if player_id == outcome_player_id else "loser"
                    elif node_status == "bye":
                        slot_state = "winner"
                    else:
                        slot_state = "pending"
                participants.append({
                    "side": side,
                    "player": player_map.get(player_id) if player_id else None,
                    "state": slot_state,
                })

            node = {
                "node_id": node_id,
                "round_number": round_number,
                "node_index": node_index,
                "layout_index": layout_indices.get((round_number, node_index), node_index),
                "status": node_status,
                "player1": participants[0],
                "player2": participants[1],
                "match": match,
                "source_node_ids": source_node_ids,
                "outcome_status": outcome_status,
                "outcome_player_id": outcome_player_id,
            }
            resolved_nodes[node_id] = node
            round_nodes.append(node)
        rounds.append({
            "round_number": round_number,
            "name": bracket_stage_name(round_number, total_rounds),
            "nodes": round_nodes,
        })

    final_node = resolved_nodes.get(f"R{total_rounds}M0", {})
    final_match = final_node.get("match") or {}
    champion_id = str(final_match.get("winner_id") or "") if final_match.get("is_finished") else ""
    finalist_ids = [
        ((final_node.get("player1") or {}).get("player") or {}).get("player_id", ""),
        ((final_node.get("player2") or {}).get("player") or {}).get("player_id", ""),
    ]
    runner_up_id = next((player_id for player_id in finalist_ids if player_id and player_id != champion_id), "")

    semifinal_losers = []
    if total_rounds >= 2:
        semifinal_round = total_rounds - 1
        for node_index in range(2):
            semifinal = resolved_nodes.get(f"R{semifinal_round}M{node_index}", {})
            semifinal_match = semifinal.get("match") or {}
            if not semifinal_match.get("is_finished"):
                continue
            participant_ids = [
                str(semifinal_match.get("player1_id") or ""),
                str(semifinal_match.get("player2_id") or ""),
            ]
            loser_id = next(
                (player_id for player_id in participant_ids if player_id and player_id != semifinal_match.get("winner_id")),
                "",
            )
            if loser_id:
                semifinal_losers.append(loser_id)

    third_match = match_map.get("THIRD")
    third_place_id = ""
    if third_match and third_match.get("is_finished"):
        third_place_id = str(third_match.get("winner_id") or "")
    elif len(semifinal_losers) == 1:
        third_place_id = semifinal_losers[0]

    third_place = {
        "node_id": "THIRD",
        "name": "Disputa de 3º lugar",
        "player1": player_map.get(semifinal_losers[0]) if len(semifinal_losers) >= 1 else None,
        "player2": player_map.get(semifinal_losers[1]) if len(semifinal_losers) >= 2 else None,
        "match": third_match,
    } if total_rounds >= 2 else None

    created_matches = [match for match in match_map.values()]
    return {
        "bracket_id": bracket_id,
        "bracket_kind": bracket_kind(bracket),
        "division": normalize_int(bracket.get("division"), 1),
        "display_name": bracket_display_name(bracket),
        "manual_override": bool(bracket.get("manual_override")),
        "participant_count": normalize_int(bracket.get("participant_count"), len(bracket.get("qualifiers", []))),
        "bracket_size": bracket_size,
        "total_rounds": total_rounds,
        "qualifiers": bracket.get("qualifiers", []),
        "rounds": rounds,
        "third_place": third_place,
        "podium": {
            "champion": player_map.get(champion_id) if champion_id else None,
            "runner_up": player_map.get(runner_up_id) if runner_up_id else None,
            "third_place": player_map.get(third_place_id) if third_place_id else None,
        },
        "group_phase_complete": bool(group_phase_complete),
        "is_preview": bool(is_preview),
        "started": bool(created_matches),
        "finished": bool(champion_id and (third_place_id or total_rounds == 1)),
    }


def build_public_brackets(config, players, matches, results, standings):
    persisted_items = get_brackets()
    persisted = {
        normalize_int(item.get("division"), 1): item
        for item in persisted_items
        if bracket_kind(item) == "division"
    }
    views = {}
    for division in range(1, config["division_count"] + 1):
        complete = division_group_phase_complete(division, players, matches, results, config)
        bracket = persisted.get(division)
        is_preview = False
        if not bracket:
            try:
                bracket = build_bracket_spec(division, standings)
                is_preview = True
            except ValueError:
                bracket = None
        if bracket:
            views[str(division)] = build_bracket_view(
                bracket,
                players,
                matches,
                group_phase_complete=complete,
                is_preview=is_preview,
            )
    for bracket in persisted_items:
        if bracket_kind(bracket) != "custom":
            continue
        views[str(bracket.get("bracket_id") or bracket.get("sk") or "")] = build_bracket_view(
            bracket,
            players,
            matches,
            group_phase_complete=True,
            is_preview=False,
        )
    return views


def division_from_bracket_id(bracket_id):
    match = re.match(r"^bracket_division_(\d+)$", str(bracket_id or ""))
    return normalize_int(match.group(1), 0, 1) if match else 0


def standings_context():
    config = get_config()
    players = get_players()
    matches = get_matches()
    results = get_results()
    standings = calculate_standings(
        players,
        matches,
        results,
        config,
        get_tiebreak_decisions(),
    )
    return config, players, matches, results, standings


def editable_bracket_from_data(data):
    bracket_id = str(data.get("bracket_id") or "")
    bracket = get_bracket_by_id(bracket_id)
    if bracket:
        return bracket

    config, players, matches, results, standings = standings_context()
    division = division_from_bracket_id(bracket_id) or normalize_int(
        data.get("division"),
        1,
        1,
        config["division_count"],
    )
    if not division_group_phase_complete(division, players, matches, results, config):
        raise ValueError("Finalize todos os jogos da fase de pontos dessa divisao antes de editar o chaveamento.")
    return build_bracket_spec(division, standings)


def normalize_bracket_slots_payload(raw_slots, bracket_size):
    bracket_size = next_power_of_two(bracket_size)
    if not isinstance(raw_slots, list):
        raise ValueError("Informe os confrontos do chaveamento.")
    slots = [str(value or "") for value in raw_slots]
    if len(slots) != bracket_size:
        raise ValueError(f"Este chaveamento precisa de {bracket_size} posicoes de competidor.")
    return slots


def player_qualifier_entry(player, source=None, seed=0):
    source = dict(source or {})
    clean = clean_public_player(player)
    return {
        "player_id": clean.get("player_id"),
        "name": clean.get("name", ""),
        "photo_url": clean.get("photo_url", ""),
        "profile_url": clean.get("profile_url", ""),
        "division": clean.get("division", source.get("division", 1)),
        "chave": source.get("chave", clean.get("chave", "A")),
        "group_rank": source.get("group_rank", 0),
        "seed": source.get("seed", seed),
    }


def validate_bracket_slots(bracket, slots, players):
    selected = [player_id for player_id in slots if player_id]
    if len(selected) != len(set(selected)):
        raise ValueError("Cada competidor so pode aparecer uma vez no chaveamento.")

    player_by_id = {
        str(player.get("player_id") or ""): player
        for player in players
        if player.get("player_id")
    }
    source_by_id = {
        str(item.get("player_id") or ""): item
        for item in bracket.get("qualifiers", [])
        if item.get("player_id")
    }

    expected_count = normalize_int(bracket.get("participant_count"), 0, 2)
    if len(selected) != expected_count:
        raise ValueError(f"Selecione exatamente {expected_count} competidor(es) para esta chave.")

    invalid = [player_id for player_id in selected if player_id not in player_by_id]
    if invalid:
        raise ValueError("O chaveamento contem competidor que nao existe mais.")

    qualifiers = []
    for seed, player_id in enumerate(selected, start=1):
        player = player_by_id.get(player_id) or source_by_id.get(player_id)
        qualifiers.append(player_qualifier_entry(player, source_by_id.get(player_id), seed))
    return qualifiers


def save_bracket_structure(data):
    bracket = editable_bracket_from_data(data)
    assert_bracket_editable(bracket.get("bracket_id"))
    config, players, matches, results, _standings = standings_context()
    if bracket_kind(bracket) == "division" and not division_group_phase_complete(
        bracket.get("division"),
        players,
        matches,
        results,
        config,
    ):
        raise ValueError("Finalize todos os jogos da fase de pontos dessa divisao antes de editar o chaveamento.")

    bracket_size = next_power_of_two(bracket.get("bracket_size") or len(bracket.get("slots", [])))
    slots = normalize_bracket_slots_payload(data.get("slots"), bracket_size)
    qualifiers = validate_bracket_slots(bracket, slots, players)
    bracket["slots"] = slots
    bracket["qualifiers"] = qualifiers
    bracket["participant_count"] = len(qualifiers)
    bracket["bracket_size"] = bracket_size
    bracket["manual_override"] = True
    bracket["bracket_kind"] = bracket_kind(bracket)
    bracket["created_at"] = bracket.get("created_at") or now_iso()
    put_item(bracket)
    return {"bracket": bracket}


def clear_bracket_structure(data):
    bracket_id = str(data.get("bracket_id") or "")
    bracket = get_bracket_by_id(bracket_id)
    if not bracket:
        return {"ok": True}
    if bracket_kind(bracket) == "custom":
        raise ValueError("Chave criada manualmente nao volta para a tabela. Exclua a chave se quiser remove-la.")
    assert_bracket_editable(bracket.get("bracket_id"))
    delete_item("BRACKET", bracket["sk"])
    return {"ok": True}


def next_custom_bracket_division(config):
    used = [normalize_int(item.get("division"), 0) for item in get_brackets()]
    return max([1000, normalize_int(config.get("division_count"), 1), *used]) + 1


def create_custom_bracket(data):
    config = get_config()
    name = str(data.get("name") or "").strip()[:80]
    participant_count = normalize_int(data.get("participant_count"), 0, 2, 512)
    if not name:
        raise ValueError("Informe o nome da nova chave.")
    existing_names = {
        bracket_display_name(item).lower()
        for item in get_brackets()
        if bracket_kind(item) == "custom"
    }
    if name.lower() in existing_names:
        raise ValueError("Ja existe uma chave criada com esse nome.")

    bracket_size = next_power_of_two(participant_count)
    bracket_id = make_id("bracket_custom")
    item = {
        "pk": "BRACKET",
        "sk": f"CUSTOM#{bracket_id}",
        "type": "BRACKET",
        "bracket_id": bracket_id,
        "bracket_kind": "custom",
        "division": next_custom_bracket_division(config),
        "display_name": name,
        "manual_override": True,
        "participant_count": participant_count,
        "bracket_size": bracket_size,
        "qualifiers": [],
        "slots": [""] * bracket_size,
        "created_at": now_iso(),
    }
    put_item(item)
    return {"bracket": item}


def delete_custom_bracket(data):
    bracket = get_bracket_by_id(data.get("bracket_id"))
    if not bracket:
        raise ValueError("Chaveamento nao encontrado.")
    if bracket_kind(bracket) != "custom":
        raise ValueError("Somente chaveamentos criados manualmente podem ser excluidos por aqui.")
    assert_bracket_editable(bracket.get("bracket_id"))
    delete_item("BRACKET", bracket["sk"])
    return {"ok": True}


def build_knockout_match(round_item, bracket, node_id, player1, player2, order_index, kind="main"):
    config = get_config()
    duration = config["duration_minutes"]
    start_min = time_to_minutes(round_item["start_time"]) + (order_index * duration)
    time_str = minutes_to_time(start_min)
    end_time = minutes_to_time(start_min + duration)
    match_id = make_id("match")
    item = {
        "pk": "MATCH",
        "sk": match_id,
        "type": "MATCH",
        "match_id": match_id,
        "pair_key": f"KNOCKOUT#{bracket['bracket_id']}#{node_id}",
        "round_id": round_item["round_id"],
        "round_name": round_item["name"],
        "round_number": round_item["round_number"],
        "stage_name": round_item["stage_name"],
        "division": bracket["division"],
        "chave": "CHAVEAMENTO",
        "phase": "knockout",
        "bracket_id": bracket["bracket_id"],
        "bracket_display_name": bracket_display_name(bracket),
        "bracket_node_id": node_id,
        "bracket_round": round_item["bracket_round"],
        "bracket_match_kind": kind,
        "date": round_item["date"],
        "time": time_str,
        "end_time": end_time,
        "duration_minutes": duration,
        "place_id": round_item["place_id"],
        "place_name": round_item["place_name"],
        "player1_id": player1["player_id"],
        "player1_name": player1["name"],
        "player2_id": player2["player_id"],
        "player2_name": player2["name"],
        "winner_id": "",
        "balls_p1": 0,
        "balls_p2": 0,
        "is_finished": False,
        "double_loss": False,
        "created_at": now_iso(),
    }
    apply_disciplinary_result(item, {
        str(player1["player_id"]): player1,
        str(player2["player_id"]): player2,
    })
    return item


def create_knockout_rounds(data):
    config = get_config()
    requested_bracket_id = str(data.get("bracket_id") or "")
    bracket = get_bracket_by_id(requested_bracket_id) if requested_bracket_id else None
    if requested_bracket_id and not bracket:
        raise ValueError("Chaveamento nao encontrado.")
    max_division = max(
        normalize_int(config.get("division_count"), 1),
        normalize_int((bracket or {}).get("division"), 1),
    )
    division = normalize_int(
        data.get("division"),
        normalize_int((bracket or {}).get("division"), 1),
        1,
        max_division,
    )
    name = str(data.get("name") or "").strip()
    date = normalize_date(str(data.get("date") or "").strip())
    start_time = normalize_time(str(data.get("start_time") or "09:00").strip(), "09:00")
    if not name:
        raise ValueError("Informe o nome do bar/local.")
    if not date:
        raise ValueError("Informe uma data válida.")

    players = get_players()
    matches = get_matches()
    results = get_results()
    standings = calculate_standings(
        players,
        matches,
        results,
        config,
        get_tiebreak_decisions(),
    )
    bracket = bracket or get_bracket(division)
    if not bracket:
        if not division_group_phase_complete(division, players, matches, results, config):
            raise ValueError("Finalize todos os jogos da fase de pontos dessa divisão antes de criar o chaveamento.")
        bracket = build_bracket_spec(division, standings)
        put_item(bracket)
    division = normalize_int(bracket.get("division"), division)

    view = build_bracket_view(bracket, players, matches, group_phase_complete=True)
    creatable = []
    for round_item in view["rounds"]:
        for node in round_item["nodes"]:
            player1 = (node["player1"] or {}).get("player")
            player2 = (node["player2"] or {}).get("player")
            if player1 and player2 and not node.get("match"):
                creatable.append({
                    "node_id": node["node_id"],
                    "round_number": round_item["round_number"],
                    "stage_name": round_item["name"],
                    "player1": player1,
                    "player2": player2,
                    "kind": "main",
                })

    third = view.get("third_place") or {}
    if third.get("player1") and third.get("player2") and not third.get("match"):
        creatable.append({
            "node_id": "THIRD",
            "round_number": view["total_rounds"],
            "stage_name": "Disputa de 3º lugar",
            "player1": third["player1"],
            "player2": third["player2"],
            "kind": "third_place",
        })

    if not creatable:
        if view.get("finished"):
            raise ValueError("O chaveamento dessa divisão já foi concluído.")
        raise ValueError("Ainda não há novos confrontos definidos. Lance os resultados pendentes do chaveamento.")

    creatable.sort(key=lambda item: (
        item["round_number"],
        0 if item["kind"] == "third_place" else 1,
        item["node_id"],
    ))
    place_id = "round_place_" + hashlib.sha1(name.lower().encode("utf-8")).hexdigest()[:10]
    duration = config["duration_minutes"]
    created_rounds = []
    created_matches = []
    elapsed_games = 0

    grouped_specs = {}
    for spec in creatable:
        grouped_specs.setdefault(spec["round_number"], []).append(spec)

    for bracket_round in sorted(grouped_specs):
        specs = grouped_specs[bracket_round]
        stage_names = {spec["stage_name"] for spec in specs}
        stage_name = (
            "Final e disputa de 3º lugar"
            if "Final" in stage_names and "Disputa de 3º lugar" in stage_names
            else " / ".join(sorted(stage_names))
        )
        round_id = make_id("round")
        round_start = add_minutes_to_time(start_time, elapsed_games * duration)
        round_item = {
            "pk": "ROUND",
            "sk": round_id,
            "type": "ROUND",
            "round_id": round_id,
            "name": name,
            "place_id": place_id,
            "place_name": name,
            "division": division,
            "chave": "CHAVEAMENTO",
            "date": date,
            "start_time": round_start,
            "round_number": bracket_round,
            "bracket_round": bracket_round,
            "stage_name": stage_name,
            "phase": "knockout",
            "mode": "knockout",
            "bracket_id": bracket["bracket_id"],
            "bracket_display_name": bracket_display_name(bracket),
            "created_at": now_iso(),
        }
        put_item(round_item)
        created_rounds.append(round_item)
        for local_index, spec in enumerate(specs):
            match = build_knockout_match(
                round_item,
                bracket,
                spec["node_id"],
                spec["player1"],
                spec["player2"],
                local_index,
                kind=spec["kind"],
            )
            put_item(match)
            if match.get("administrative_loss_player_ids"):
                put_item(result_item_for_match(match, match.get("result_saved_at")))
            created_matches.append(match)
        elapsed_games += len(specs)

    return {
        "bracket": bracket,
        "rounds": created_rounds,
        "matches": created_matches,
        "created": len(created_matches),
    }


def knockout_descendant_node_ids(match, bracket):
    node_id = str(match.get("bracket_node_id") or "")
    if not node_id.startswith("R") or "M" not in node_id:
        return set()
    round_text, index_text = node_id[1:].split("M", 1)
    round_number = normalize_int(round_text, 0)
    node_index = normalize_int(index_text, 0)
    bracket_size = next_power_of_two(bracket.get("bracket_size", 2))
    total_rounds = max(1, bracket_size.bit_length() - 1)
    descendants = set()
    if round_number == total_rounds - 1:
        descendants.add("THIRD")
    while round_number < total_rounds:
        next_round_number = round_number + 1
        source_count = bracket_size // (2 ** round_number)
        target_count = bracket_size // (2 ** next_round_number)
        next_node_index = None
        for target_index in range(target_count):
            source_indices = bracket_source_indices_for_node(
                bracket,
                next_round_number,
                target_index,
                source_count,
            )
            if node_index in source_indices:
                next_node_index = target_index
                break
        if next_node_index is None:
            break
        round_number = next_round_number
        node_index = next_node_index
        descendants.add(f"R{round_number}M{node_index}")
    return descendants


def invalidate_pending_knockout_descendants(match):
    bracket = get_bracket_by_id(match.get("bracket_id")) or get_bracket(match.get("division"))
    if not bracket:
        return 0
    descendant_ids = knockout_descendant_node_ids(match, bracket)
    if not descendant_ids:
        return 0
    dependent = [
        item for item in get_matches()
        if item.get("phase") == "knockout"
        and item.get("bracket_id") == match.get("bracket_id")
        and item.get("bracket_node_id") in descendant_ids
    ]
    if any(item.get("is_finished") for item in dependent):
        raise ValueError("Não é possível alterar este resultado porque uma fase posterior já foi finalizada.")
    round_ids = {str(item.get("round_id") or "") for item in dependent}
    for item in dependent:
        delete_item("MATCH", item["sk"])
    remaining_matches = get_matches()
    for round_id in round_ids:
        if round_id and not any(str(item.get("round_id") or "") == round_id for item in remaining_matches):
            delete_item("ROUND", round_id)
    return len(dependent)



def get_sponsors():
    sponsors = scan_type("SPONSOR")
    return sorted(sponsors, key=lambda s: str(s.get("name", "")).lower())


def upsert_sponsor(data):
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Informe o nome do patrocinador.")
    sponsor_id = str(data.get("sponsor_id") or data.get("id") or make_id("sponsor"))
    for other in get_sponsors():
        if other.get("sponsor_id") != sponsor_id and str(other.get("name", "")).strip().lower() == name.lower():
            raise ValueError("Já existe um patrocinador com esse nome.")
    current = get_item("SPONSOR", sponsor_id) or {}
    item = {
        "pk": "SPONSOR",
        "sk": sponsor_id,
        "type": "SPONSOR",
        "sponsor_id": sponsor_id,
        "name": name,
        "square_image_url": current.get("square_image_url", ""),
        "rect_image_url": current.get("rect_image_url", ""),
        "created_at": current.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    if data.get("square_image_data_url"):
        item["square_image_url"] = save_jpeg_media(
            data.get("square_image_data_url"),
            f"media/sponsors/{sponsor_id}/square.jpg",
            current.get("square_image_url", ""),
        )
    if data.get("rect_image_data_url"):
        item["rect_image_url"] = save_jpeg_media(
            data.get("rect_image_data_url"),
            f"media/sponsors/{sponsor_id}/rect.jpg",
            current.get("rect_image_url", ""),
        )
    put_item(item)
    return item


def delete_sponsor(sponsor_id):
    sponsor_id = str(sponsor_id or "")
    if not sponsor_id:
        return
    current = get_item("SPONSOR", sponsor_id)
    if current:
        delete_media_url(current.get("square_image_url", ""))
        delete_media_url(current.get("rect_image_url", ""))
    delete_item("SPONSOR", sponsor_id)


def latest_finished_match(matches):
    finished = [m for m in matches if m.get("is_finished")]
    if not finished:
        return None
    return sorted(
        finished,
        key=lambda m: str(m.get("result_saved_at") or m.get("updated_at") or m.get("created_at") or ""),
        reverse=True,
    )[0]


def request_origin(event):
    headers = {
        str(key).lower(): str(value)
        for key, value in (event.get("headers") or {}).items()
    }
    host = headers.get("x-site-host") or headers.get("x-forwarded-host") or headers.get("host") or ""
    if not host:
        return ""
    scheme = headers.get("x-forwarded-proto") or "https"
    if host.startswith("localhost") or host.startswith("127.0.0.1"):
        scheme = "http"
    return f"{scheme}://{host}".rstrip("/")


def absolute_site_url(origin, path):
    value = str(path or "")
    if value.startswith("http://") or value.startswith("https://"):
        return value
    if not value.startswith("/"):
        value = "/" + value
    return origin + value if origin else value


def profile_html(event, slug):
    players = [clean_public_player(player) for player in get_players()]
    target = slugify_name(unquote(slug or ""))
    player = next((item for item in players if item.get("slug") == target), None)
    origin = request_origin(event)
    profile_path = f"/perfil/{quote(target)}"
    if player:
        title = f"Perfil de {player.get('name', '')} do 2° Campeonato de Sinuca de Entre Folhas"
        description = player.get("short_message") or "Perfil do jogador no campeonato de sinuca de Entre Folhas."
        image_path = player.get("photo_url") or "/img/entre-folhas-logo-card.png"
    else:
        title = "Perfil do jogador do 2° Campeonato de Sinuca de Entre Folhas"
        description = "Perfil do jogador no campeonato de sinuca de Entre Folhas."
        image_path = "/img/entre-folhas-logo-card.png"
    image_url = absolute_site_url(origin, image_path)
    page_url = absolute_site_url(origin, profile_path)
    safe_title = html_escape(title, quote=True)
    safe_description = html_escape(description, quote=True)
    safe_image = html_escape(image_url, quote=True)
    safe_page_url = html_escape(page_url, quote=True)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <meta property="og:title" content="{safe_title}">
  <meta property="og:description" content="{safe_description}">
  <meta property="og:type" content="profile">
  <meta property="og:url" content="{safe_page_url}">
  <meta property="og:image" content="{safe_image}">
  <meta property="og:image:alt" content="Foto de perfil do jogador">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{safe_title}">
  <meta name="twitter:description" content="{safe_description}">
  <meta name="twitter:image" content="{safe_image}">
  <link rel="icon" type="image/png" href="/img/favicon.png">
  <link rel="apple-touch-icon" href="/img/favicon-180.png">
  <link rel="stylesheet" href="/css/style.css">
</head>
<body>
  <header class="topbar">
    <a class="brand" href="/index.html">🎱 Segundo campeonato municipal de sinuca de Entre Folhas</a>
    <nav>
      <a href="/index.html">Placar</a>
      <a href="/telao">Telão</a>
      <a href="/admin">Admin</a>
    </nav>
  </header>
  <main class="container">
    <section id="profile-root" class="profile-page"></section>
  </main>
  <script src="/config.js"></script>
  <script src="/js/api.js"></script>
  <script src="/js/profile.js"></script>
</body>
</html>"""


def public_state(include_matches=True):
    config = get_config()
    players = [clean_public_player(p) for p in get_players()]
    rounds = get_rounds()
    matches = get_matches()
    results = get_results()
    sponsors = get_sponsors()
    dates = derive_dates(matches, rounds)
    places = derive_places(matches, rounds)
    tiebreak_decisions = get_tiebreak_decisions()
    standings_details = calculate_standings_details(
        players,
        matches,
        results,
        config,
        tiebreak_decisions,
    )
    standings = standings_details["standings"]
    brackets = build_public_brackets(config, players, matches, results, standings)
    requirements = round_requirements(config, players, rounds, matches, results)
    latest_result = latest_finished_match(matches)
    return {
        "config": config,
        "players": players,
        "rounds": rounds,
        "matches": matches if include_matches else [],
        "results": results if include_matches else [],
        "sponsors": sponsors,
        "dates": dates,
        "places": places,
        "standings": standings,
        "tiebreaks": standings_details["tiebreaks"],
        "brackets": brackets,
        "round_requirements": requirements,
        "latest_result": latest_result if include_matches else None,
        "tv_matches": tv_cycle_matches(matches, config.get("tv_config")) if include_matches else [],
    }


def handle_admin_mutation(event, action):
    if not require_admin(event):
        return response(401, {"error": "Sessão expirada ou inválida."})
    data = parse_body(event)
    try:
        if action == "config":
            cfg = save_config(data)
            return response(200, {"config": cfg, "state": public_state()})
        if action == "tv-config":
            cfg = save_tv_config(data)
            return response(200, {"tv_config": cfg, "state": public_state()})
        if action == "player":
            item = upsert_player(data)
            return response(200, {"player": item, "state": public_state()})
        if action == "delete-player":
            delete_player(data.get("player_id"))
            return response(200, {"ok": True, "state": public_state()})
        if action == "update-player":
            item = upsert_player(data)
            return response(200, {"player": item, "state": public_state()})
        if action == "player-status":
            result = set_player_status(data)
            return response(200, {**result, "state": public_state()})
        if action == "sponsor":
            item = upsert_sponsor(data)
            return response(200, {"sponsor": item, "state": public_state()})
        if action == "delete-sponsor":
            delete_sponsor(data.get("sponsor_id"))
            return response(200, {"ok": True, "state": public_state()})
        if action == "round-auto":
            result = create_round(data, manual=False)
            return response(200, {**result, "state": public_state()})
        if action == "round-manual":
            result = create_round(data, manual=True)
            return response(200, {**result, "state": public_state()})
        if action == "knockout-rounds":
            result = create_knockout_rounds(data)
            return response(200, {**result, "state": public_state()})
        if action == "save-bracket":
            result = save_bracket_structure(data)
            return response(200, {**result, "state": public_state()})
        if action == "clear-bracket":
            result = clear_bracket_structure(data)
            return response(200, {**result, "state": public_state()})
        if action == "create-bracket":
            result = create_custom_bracket(data)
            return response(200, {**result, "state": public_state()})
        if action == "delete-bracket":
            result = delete_custom_bracket(data)
            return response(200, {**result, "state": public_state()})
        if action == "delete-round":
            result = delete_round(data.get("round_id"))
            return response(200, {**result, "state": public_state()})
        if action == "update-round":
            result = update_round_name(data)
            return response(200, {**result, "state": public_state()})
        if action == "result":
            item = set_match_result(data)
            return response(200, {"match": item, "state": public_state()})
        if action == "tiebreak":
            item = save_tiebreak_decision(data)
            return response(200, {"tiebreak": item, "state": public_state()})
        if action == "clear-database":
            if str(data.get("confirm_text", "")).strip().upper() != "LIMPAR":
                raise ValueError("Digite LIMPAR para confirmar a limpeza definitiva do torneio.")
            clear_all_data(keep_reset_marker=True)
            return response(200, {"ok": True, "state": public_state()})
    except RoundConflictError as exc:
        return response(409, {"error": str(exc), "conflicts": exc.conflicts, "requires_confirmation": True})
    except ValueError as exc:
        return response(400, {"error": str(exc)})
    except Exception as exc:
        return response(500, {"error": f"Erro interno: {exc}"})
    return response(404, {"error": "Rota administrativa não encontrada."})


def lambda_handler(event, context):
    ensure_reset_once()
    method, path = get_method_path(event)
    if method == "OPTIONS":
        return response(200, {"ok": True})
    try:
        if method == "POST" and path == "/admin/login":
            data = parse_body(event)
            password = str(data.get("password", ""))
            if hmac.compare_digest(password, ADMIN_PASSWORD):
                return response(200, {"token": make_token(), "expires_in": SESSION_SECONDS})
            return response(401, {"error": "Senha inválida."})

        if method == "GET" and path in ["/state", "/admin/state"]:
            if path == "/admin/state" and not require_admin(event):
                return response(401, {"error": "Sessão expirada ou inválida."})
            include_matches = str(get_query_params(event).get("include_matches", "1")).lower() not in {"0", "false", "no"}
            return response(200, public_state(include_matches=include_matches))

        if method == "GET" and path == "/matches":
            query = get_query_params(event)
            filters = {key: str(query.get(key, "") or "").strip() for key in TV_FILTER_KEYS}
            if filters["status"] not in {"finished", "pending"}:
                filters["status"] = ""
            return response(200, {"matches": filtered_matches(get_matches(), filters)})

        if method in {"GET", "HEAD"} and (path == "/perfil" or path.startswith("/perfil/")):
            slug = path.split("/perfil/", 1)[1] if path.startswith("/perfil/") else ""
            return html_response(200, profile_html(event, slug))

        if method == "GET" and path.startswith("/player/"):
            player_id = path.split("/player/", 1)[1]
            state = public_state()
            player = next((p for p in state["players"] if p.get("player_id") == player_id), None)
            if not player:
                return response(404, {"error": "Jogador não encontrado."})
            matches = [m for m in state["matches"] if m.get("player1_id") == player_id or m.get("player2_id") == player_id]
            return response(200, {"player": player, "matches": matches, "state": state})

        if method == "POST" and path.startswith("/admin/"):
            action = path.split("/admin/", 1)[1]
            return handle_admin_mutation(event, action)

        return response(404, {"error": "Rota não encontrada.", "path": path})
    except Exception as exc:
        return response(500, {"error": f"Erro interno: {exc}"})
