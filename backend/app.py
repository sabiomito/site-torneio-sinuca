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

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME) if TABLE_NAME else None
_s3 = boto3.client("s3") if MEDIA_BUCKET else None
_reset_checked = False


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


def save_jpeg_media(data_url, key):
    raw = parse_image_payload(data_url)
    if raw is None:
        return ""
    if not MEDIA_BUCKET or not _s3:
        raise ValueError("Bucket de mídia não configurado no servidor.")
    _s3.put_object(
        Bucket=MEDIA_BUCKET,
        Key=key,
        Body=raw,
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000",
    )
    return "/" + key


def build_pair_key(division, chave, p1_id, p2_id):
    ordered = sorted([str(p1_id), str(p2_id)])
    return f"D{normalize_int(division, 1)}#K{normalize_chave(chave)}#{ordered[0]}#{ordered[1]}"


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
            "created_at": now_iso(),
        }
        put_item(item)
    item["division_count"] = normalize_int(item.get("division_count"), 2, 1, 20)
    item["duration_minutes"] = normalize_int(item.get("duration_minutes"), 30, 5, 240)
    item.setdefault("rules", {})
    for d in range(1, item["division_count"] + 1):
        raw = item["rules"].get(str(d), {}) or {}
        item["rules"][str(d)] = {
            "key_count": normalize_int(raw.get("key_count", 1), 1, 1, 99),
            "promotion_count": normalize_int(raw.get("promotion_count", 0), 0, 0, 100),
            "relegation_count": normalize_int(raw.get("relegation_count", 0), 0, 0, 100),
        }
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
        "rules": rules,
    })
    put_item(current)
    return current


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
    return sorted(matches, key=lambda m: (m.get("date") or "9999-99-99", m.get("time") or "99:99", m.get("place_name", ""), m.get("round_number", 999), m.get("chave", "A")))


def get_results():
    return scan_type("RESULT")


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
            done_or_scheduled = len(all_keys & used_pairs)
            remaining_pairs = max(0, total_pairs - done_or_scheduled)
            per_round = matches_per_round(len(ps))
            missing_rounds = 0 if per_round == 0 else (remaining_pairs + per_round - 1) // per_round
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
        "created_at": current.get("created_at") or data.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    photo_data_url = data.get("photo_data_url")
    if photo_data_url:
        item["photo_url"] = save_jpeg_media(photo_data_url, f"media/players/{player_id}/photo.jpg")
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


def delete_player(player_id):
    player_id = str(player_id or "")
    if not player_id:
        return
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
        "created_at": now_iso(),
    }
    if previous_result:
        item["winner_id"] = previous_result.get("winner_id", "")
        item["balls_p1"] = previous_result.get("balls_p1", 0)
        item["balls_p2"] = previous_result.get("balls_p2", 0)
        item["is_finished"] = True
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

    def rec(remaining, pairs, bye_used):
        nonlocal best
        if len(pairs) > len(best):
            best = pairs[:]
        if len(pairs) == target:
            return True
        if len(remaining) < 2:
            return False
        first = remaining[0]
        rest = remaining[1:]
        partners = rest[:]
        rng.shuffle(partners)
        for partner in partners:
            pair_key = build_pair_key(division, chave, first["player_id"], partner["player_id"])
            if pair_key in used_pairs:
                continue
            next_remaining = [p for p in rest if p["player_id"] != partner["player_id"]]
            if rec(next_remaining, pairs + [(first, partner)], bye_used):
                return True
        if len(players) % 2 == 1 and not bye_used:
            if rec(rest, pairs, True):
                return True
        return False

    rec(players, [], False)
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
    if data.get("clear"):
        match["winner_id"] = ""
        match["balls_p1"] = 0
        match["balls_p2"] = 0
        match["is_finished"] = False
        match["updated_at"] = now_iso()
        match["result_saved_at"] = ""
        put_item(match)
        delete_item("RESULT", pair_key)
        return match
    winner_id = str(data.get("winner_id", ""))
    if winner_id not in [match.get("player1_id"), match.get("player2_id")]:
        raise ValueError("Selecione o vencedor da partida.")
    balls_p1 = normalize_int(data.get("balls_p1", 0), 0, 0, 7)
    balls_p2 = normalize_int(data.get("balls_p2", 0), 0, 0, 7)
    if winner_id == match.get("player1_id"):
        balls_p1 = 7
    if winner_id == match.get("player2_id"):
        balls_p2 = 7
    saved_at = now_iso()
    match["winner_id"] = winner_id
    match["balls_p1"] = balls_p1
    match["balls_p2"] = balls_p2
    match["is_finished"] = True
    match["result_saved_at"] = saved_at
    match["updated_at"] = saved_at
    put_item(match)
    put_item({
        "pk": "RESULT",
        "sk": pair_key,
        "type": "RESULT",
        "pair_key": pair_key,
        "division": match.get("division"),
        "chave": match.get("chave"),
        "player1_id": match.get("player1_id"),
        "player1_name": match.get("player1_name"),
        "player2_id": match.get("player2_id"),
        "player2_name": match.get("player2_name"),
        "winner_id": winner_id,
        "balls_p1": balls_p1,
        "balls_p2": balls_p2,
        "is_finished": True,
        "created_at": saved_at,
        "result_saved_at": saved_at,
    })
    return match


def calculate_standings(players, matches, results, config):
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
        }

    result_by_pair = {}
    for r in results:
        if r.get("pair_key"):
            result_by_pair[str(r.get("pair_key"))] = r
    for m in matches:
        if m.get("is_finished") and m.get("pair_key"):
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
        if item.get("winner_id") == item.get("player1_id"):
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

    rules = config.get("rules", {}) or {}
    for division_str, chaves in grouped.items():
        rule = rules.get(str(division_str), {})
        promotion_count = normalize_int(rule.get("promotion_count", 0), 0, 0, 100)
        relegation_count = normalize_int(rule.get("relegation_count", 0), 0, 0, 100)
        for chave, rows in chaves.items():
            rows.sort(key=lambda r: (-r["points"], -r["balls_balance"], -r["balls_for"], -r["wins"], r["name"].lower()))
            for row in rows[:promotion_count]:
                row["rank_status"] = "promotion"
            if relegation_count:
                for row in rows[-relegation_count:]:
                    if row["rank_status"] != "promotion":
                        row["rank_status"] = "relegation"
    return grouped


def public_state():
    config = get_config()
    players = [clean_public_player(p) for p in get_players()]
    rounds = get_rounds()
    matches = get_matches()
    results = get_results()
    sponsors = get_sponsors()
    dates = derive_dates(matches, rounds)
    places = derive_places(matches, rounds)
    standings = calculate_standings(players, matches, results, config)
    requirements = round_requirements(config, players, rounds, matches, results)
    latest_result = latest_finished_match(matches)
    return {
        "config": config,
        "players": players,
        "rounds": rounds,
        "matches": matches,
        "results": results,
        "sponsors": sponsors,
        "dates": dates,
        "places": places,
        "standings": standings,
        "round_requirements": requirements,
        "latest_result": latest_result,
    }


def handle_admin_mutation(event, action):
    if not require_admin(event):
        return response(401, {"error": "Sessão expirada ou inválida."})
    data = parse_body(event)
    try:
        if action == "config":
            cfg = save_config(data)
            return response(200, {"config": cfg, "state": public_state()})
        if action == "player":
            item = upsert_player(data)
            return response(200, {"player": item, "state": public_state()})
        if action == "delete-player":
            delete_player(data.get("player_id"))
            return response(200, {"ok": True, "state": public_state()})
        if action == "update-player":
            item = upsert_player(data)
            return response(200, {"player": item, "state": public_state()})
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
        if action == "delete-round":
            result = delete_round(data.get("round_id"))
            return response(200, {**result, "state": public_state()})
        if action == "update-round":
            result = update_round_name(data)
            return response(200, {**result, "state": public_state()})
        if action == "result":
            item = set_match_result(data)
            return response(200, {"match": item, "state": public_state()})
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
            return response(200, public_state())

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
