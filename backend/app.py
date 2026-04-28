import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import combinations

import boto3
from boto3.dynamodb.conditions import Attr

TABLE_NAME = os.environ.get("TABLE_NAME", "")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")
SECRET_KEY = os.environ.get("SECRET_KEY", "troque-esta-chave")
SESSION_SECONDS = int(os.environ.get("SESSION_SECONDS", "43200"))  # 12 horas
TRAVEL_BUFFER_MINUTES = int(os.environ.get("TRAVEL_BUFFER_MINUTES", "30"))

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME) if TABLE_NAME else None


def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def json_default(value):
    if isinstance(value, Decimal):
        if value % 1 == 0:
            return int(value)
        return float(value)
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
        "Access-Control-Allow-Headers": "content-type,authorization",
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
    path = path.rstrip("/") or "/"
    return method.upper(), path


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def make_token():
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + SESSION_SECONDS,
        "typ": "admin",
    }
    payload_raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_part = b64url(payload_raw)
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
    return False


def put_item(item):
    item["updated_at"] = now_iso()
    _table.put_item(Item=to_dynamo(item))


def delete_item(pk, sk):
    _table.delete_item(Key={"pk": pk, "sk": sk})


def get_item(pk, sk):
    result = _table.get_item(Key={"pk": pk, "sk": sk})
    return result.get("Item")


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
        datetime.strptime(value, "%Y-%m-%d")
        return value
    except Exception:
        return ""


def normalize_time(value, default="09:00"):
    try:
        datetime.strptime(value, "%H:%M")
        return value
    except Exception:
        return default


def parse_dt(date_str, time_str):
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")


def minutes_to_time(minutes):
    minutes = minutes % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def time_to_minutes(time_str):
    dt = datetime.strptime(time_str, "%H:%M")
    return dt.hour * 60 + dt.minute


def add_minutes_to_time(time_str, duration):
    return minutes_to_time(time_to_minutes(time_str) + duration)


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
                "1": {"promotion_count": 0, "relegation_count": 0},
                "2": {"promotion_count": 0, "relegation_count": 0},
            },
            "created_at": now_iso(),
        }
        put_item(item)
    item["division_count"] = normalize_int(item.get("division_count"), 2, 1, 20)
    item["duration_minutes"] = normalize_int(item.get("duration_minutes"), 30, 5, 240)
    item.setdefault("rules", {})
    return item


def get_players():
    players = scan_type("PLAYER")
    return sorted(players, key=lambda p: (normalize_int(p.get("division"), 1), str(p.get("name", "")).lower()))


def get_places():
    places = scan_type("PLACE")
    return sorted(places, key=lambda p: str(p.get("name", "")).lower())


def get_dates():
    dates = scan_type("DATE")
    return sorted(dates, key=lambda d: (str(d.get("date", "")), str(d.get("start_time", "09:00"))))


def get_matches():
    matches = scan_type("MATCH")
    return sorted(matches, key=lambda m: (str(m.get("date", "9999-99-99")), str(m.get("time", "99:99")), str(m.get("place_name", ""))))


def build_pair_key(division, p1_id, p2_id):
    ordered = sorted([str(p1_id), str(p2_id)])
    return f"D{division}#{ordered[0]}#{ordered[1]}"


def make_id(prefix):
    return prefix + "_" + uuid.uuid4().hex[:12]


def save_config(data):
    current = get_config()
    division_count = normalize_int(data.get("division_count", current.get("division_count", 2)), 2, 1, 20)
    duration_minutes = normalize_int(data.get("duration_minutes", current.get("duration_minutes", 30)), 30, 5, 240)
    rules_in = data.get("rules", {}) or {}
    rules = {}
    for division in range(1, division_count + 1):
        raw = rules_in.get(str(division)) or rules_in.get(division) or {}
        rules[str(division)] = {
            "promotion_count": normalize_int(raw.get("promotion_count", 0), 0, 0, 100),
            "relegation_count": normalize_int(raw.get("relegation_count", 0), 0, 0, 100),
        }
    current.update({
        "division_count": division_count,
        "duration_minutes": duration_minutes,
        "rules": rules,
        "type": "CONFIG",
        "pk": "CONFIG",
        "sk": "TOURNAMENT",
    })
    put_item(current)
    return current


def upsert_player(data):
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Informe o nome do jogador.")
    config = get_config()
    division = normalize_int(data.get("division", 1), 1, 1, config["division_count"])
    player_id = str(data.get("player_id") or data.get("id") or make_id("player"))
    item = {
        "pk": "PLAYER",
        "sk": player_id,
        "type": "PLAYER",
        "player_id": player_id,
        "name": name,
        "division": division,
        "created_at": data.get("created_at") or now_iso(),
    }
    put_item(item)
    return item


def upsert_place(data):
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Informe o nome do local.")
    place_id = str(data.get("place_id") or data.get("id") or make_id("place"))
    item = {
        "pk": "PLACE",
        "sk": place_id,
        "type": "PLACE",
        "place_id": place_id,
        "name": name,
        "created_at": data.get("created_at") or now_iso(),
    }
    put_item(item)
    return item


def upsert_date(data):
    date = normalize_date(str(data.get("date", "")).strip())
    if not date:
        raise ValueError("Informe uma data válida.")
    start_time = normalize_time(str(data.get("start_time") or "09:00").strip(), "09:00")
    date_id = str(data.get("date_id") or data.get("id") or f"date_{date}")
    item = {
        "pk": "DATE",
        "sk": date_id,
        "type": "DATE",
        "date_id": date_id,
        "date": date,
        "start_time": start_time,
        "created_at": data.get("created_at") or now_iso(),
    }
    put_item(item)
    return item


def clear_all_data():
    for item_type in ["PLAYER", "PLACE", "DATE", "MATCH"]:
        for item in scan_type(item_type):
            delete_item(item["pk"], item["sk"])


def player_available(player_id, date, start_minutes, end_minutes, place_id, player_schedule):
    for game in player_schedule.get(player_id, []):
        if game["date"] != date:
            continue
        overlap = start_minutes < game["end"] and end_minutes > game["start"]
        if overlap:
            return False
        if game["place_id"] != place_id:
            enough_gap_after_old = start_minutes >= game["end"] + TRAVEL_BUFFER_MINUTES
            enough_gap_before_old = end_minutes + TRAVEL_BUFFER_MINUTES <= game["start"]
            if not (enough_gap_after_old or enough_gap_before_old):
                return False
    return True


def travel_penalty(player_id, date, place_id, player_schedule):
    penalty = 0
    for game in player_schedule.get(player_id, []):
        if game["date"] == date and game["place_id"] != place_id:
            penalty += 1
    return penalty


def slot_candidates(dates, places, duration_minutes, scheduled_count):
    # A cada rodada, abre uma quantidade grande de horários. Se o torneio crescer,
    # o algoritmo aumenta o limite automaticamente.
    matches_per_round = max(1, len(places))
    extra_slots = max(24, scheduled_count + 50)
    max_slots_per_place_day = max(24, (extra_slots // matches_per_round) + 10)
    candidates = []
    for date_item in dates:
        date = date_item["date"]
        start_time = normalize_time(date_item.get("start_time", "09:00"), "09:00")
        start_base = time_to_minutes(start_time)
        for slot_idx in range(max_slots_per_place_day):
            start = start_base + slot_idx * duration_minutes
            end = start + duration_minutes
            if end > 23 * 60 + 59:
                continue
            for place in places:
                candidates.append({
                    "date": date,
                    "time": minutes_to_time(start),
                    "end_time": minutes_to_time(end),
                    "start": start,
                    "end": end,
                    "place_id": place["place_id"],
                    "place_name": place["name"],
                })
    return candidates


def generate_schedule():
    config = get_config()
    duration = config["duration_minutes"]
    players = get_players()
    places = get_places()
    dates = get_dates()
    if not players:
        return {"created": 0, "message": "Cadastre jogadores antes de recalcular."}
    if not places:
        return {"created": 0, "message": "Cadastre pelo menos um local antes de recalcular."}
    if not dates:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        upsert_date({"date": today, "start_time": "09:00"})
        dates = get_dates()

    existing_matches = get_matches()
    previous_by_pair = {str(m.get("pair_key")): m for m in existing_matches if m.get("pair_key")}
    current_pair_keys = set()

    pairs = []
    for division in range(1, config["division_count"] + 1):
        division_players = [p for p in players if normalize_int(p.get("division"), 1) == division]
        division_players.sort(key=lambda p: str(p.get("name", "")).lower())
        for p1, p2 in combinations(division_players, 2):
            pair_key = build_pair_key(division, p1["player_id"], p2["player_id"])
            current_pair_keys.add(pair_key)
            pairs.append({
                "division": division,
                "player1_id": p1["player_id"],
                "player1_name": p1["name"],
                "player2_id": p2["player_id"],
                "player2_name": p2["name"],
                "pair_key": pair_key,
            })

    # Remove jogos que deixaram de existir por mudança de competidor/divisão.
    for old_match in existing_matches:
        if old_match.get("pair_key") not in current_pair_keys:
            delete_item(old_match["pk"], old_match["sk"])

    player_schedule = {}
    occupied_slots = set()
    scheduled_items = []
    unscheduled = []

    # Prioriza jogos ainda sem resultado para facilitar preservar os concluídos.
    pairs.sort(key=lambda x: (x["division"], x["player1_name"].lower(), x["player2_name"].lower()))

    for pair in pairs:
        previous = previous_by_pair.get(pair["pair_key"])
        best = None
        candidates = slot_candidates(dates, places, duration, len(scheduled_items))
        for candidate in candidates:
            slot_key = (candidate["date"], candidate["time"], candidate["place_id"])
            if slot_key in occupied_slots:
                continue
            p1_ok = player_available(pair["player1_id"], candidate["date"], candidate["start"], candidate["end"], candidate["place_id"], player_schedule)
            p2_ok = player_available(pair["player2_id"], candidate["date"], candidate["start"], candidate["end"], candidate["place_id"], player_schedule)
            if not (p1_ok and p2_ok):
                continue
            penalty = travel_penalty(pair["player1_id"], candidate["date"], candidate["place_id"], player_schedule)
            penalty += travel_penalty(pair["player2_id"], candidate["date"], candidate["place_id"], player_schedule)
            candidate_score = (penalty, candidate["date"], candidate["start"], candidate["place_name"])
            if not best or candidate_score < best[0]:
                best = (candidate_score, candidate)
                if penalty == 0:
                    break
        if not best:
            unscheduled.append(pair)
            continue

        candidate = best[1]
        occupied_slots.add((candidate["date"], candidate["time"], candidate["place_id"]))
        for pid in [pair["player1_id"], pair["player2_id"]]:
            player_schedule.setdefault(pid, []).append({
                "date": candidate["date"],
                "start": candidate["start"],
                "end": candidate["end"],
                "place_id": candidate["place_id"],
            })

        match_id = previous.get("match_id") if previous else make_id("match")
        item = {
            "pk": "MATCH",
            "sk": match_id,
            "type": "MATCH",
            "match_id": match_id,
            **pair,
            "date": candidate["date"],
            "time": candidate["time"],
            "end_time": candidate["end_time"],
            "duration_minutes": duration,
            "place_id": candidate["place_id"],
            "place_name": candidate["place_name"],
            "winner_id": previous.get("winner_id") if previous else "",
            "balls_p1": normalize_int(previous.get("balls_p1", 0), 0, 0, 7) if previous else 0,
            "balls_p2": normalize_int(previous.get("balls_p2", 0), 0, 0, 7) if previous else 0,
            "is_finished": bool(previous.get("is_finished")) if previous else False,
            "created_at": previous.get("created_at") if previous else now_iso(),
        }
        put_item(item)
        scheduled_items.append(item)

    for pair in unscheduled:
        previous = previous_by_pair.get(pair["pair_key"])
        match_id = previous.get("match_id") if previous else make_id("match")
        item = {
            "pk": "MATCH",
            "sk": match_id,
            "type": "MATCH",
            "match_id": match_id,
            **pair,
            "date": "",
            "time": "",
            "end_time": "",
            "duration_minutes": duration,
            "place_id": "",
            "place_name": "Sem horário disponível",
            "winner_id": previous.get("winner_id") if previous else "",
            "balls_p1": normalize_int(previous.get("balls_p1", 0), 0, 0, 7) if previous else 0,
            "balls_p2": normalize_int(previous.get("balls_p2", 0), 0, 0, 7) if previous else 0,
            "is_finished": bool(previous.get("is_finished")) if previous else False,
            "created_at": previous.get("created_at") if previous else now_iso(),
        }
        put_item(item)

    return {
        "created": len(scheduled_items),
        "unscheduled": len(unscheduled),
        "message": "Calendário recalculado.",
    }


def calculate_standings(players, matches, config):
    table = {}
    for p in players:
        pid = p["player_id"]
        table[pid] = {
            "player_id": pid,
            "name": p.get("name", ""),
            "division": normalize_int(p.get("division"), 1),
            "played": 0,
            "wins": 0,
            "losses": 0,
            "points": 0,
            "balls_for": 0,
            "balls_against": 0,
            "balls_balance": 0,
            "rank_status": "normal",
        }

    for m in matches:
        if not m.get("is_finished"):
            continue
        p1 = table.get(m.get("player1_id"))
        p2 = table.get(m.get("player2_id"))
        if not p1 or not p2:
            continue
        balls_p1 = normalize_int(m.get("balls_p1", 0), 0, 0, 7)
        balls_p2 = normalize_int(m.get("balls_p2", 0), 0, 0, 7)
        p1["played"] += 1
        p2["played"] += 1
        p1["balls_for"] += balls_p1
        p1["balls_against"] += balls_p2
        p2["balls_for"] += balls_p2
        p2["balls_against"] += balls_p1
        if m.get("winner_id") == m.get("player1_id"):
            p1["wins"] += 1
            p1["points"] += 3
            p2["losses"] += 1
        elif m.get("winner_id") == m.get("player2_id"):
            p2["wins"] += 1
            p2["points"] += 3
            p1["losses"] += 1

    grouped = {str(d): [] for d in range(1, config["division_count"] + 1)}
    for row in table.values():
        row["balls_balance"] = row["balls_for"] - row["balls_against"]
        grouped.setdefault(str(row["division"]), []).append(row)

    rules = config.get("rules", {}) or {}
    for division_str, rows in grouped.items():
        division = normalize_int(division_str, 1)
        rows.sort(key=lambda r: (-r["points"], -r["balls_balance"], -r["balls_for"], -r["wins"], r["name"].lower()))
        rule = rules.get(str(division), {})
        promotion_count = normalize_int(rule.get("promotion_count", 0), 0, 0, 100) if division > 1 else 0
        relegation_count = normalize_int(rule.get("relegation_count", 0), 0, 0, 100) if division < config["division_count"] else 0
        if promotion_count:
            for row in rows[:promotion_count]:
                row["rank_status"] = "promotion"
        if relegation_count:
            for row in rows[-relegation_count:]:
                if row["rank_status"] != "promotion":
                    row["rank_status"] = "relegation"
    return grouped


def public_state():
    config = get_config()
    players = get_players()
    places = get_places()
    dates = get_dates()
    matches = get_matches()
    standings = calculate_standings(players, matches, config)
    return {
        "config": config,
        "players": players,
        "places": places,
        "dates": dates,
        "matches": matches,
        "standings": standings,
    }


def set_match_result(data):
    match_id = str(data.get("match_id", ""))
    match = get_item("MATCH", match_id)
    if not match:
        raise ValueError("Partida não encontrada.")
    if data.get("clear"):
        match["winner_id"] = ""
        match["balls_p1"] = 0
        match["balls_p2"] = 0
        match["is_finished"] = False
        put_item(match)
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
    match["winner_id"] = winner_id
    match["balls_p1"] = balls_p1
    match["balls_p2"] = balls_p2
    match["is_finished"] = True
    put_item(match)
    return match


def setup_tournament(data):
    clear_all_data()
    config = save_config(data)
    for name in data.get("places", []):
        if isinstance(name, dict):
            upsert_place(name)
        elif str(name).strip():
            upsert_place({"name": str(name).strip()})
    for date_item in data.get("dates", []):
        if isinstance(date_item, dict):
            upsert_date(date_item)
    for player in data.get("players", []):
        if isinstance(player, dict):
            upsert_player(player)
    result = generate_schedule()
    return {"config": config, "schedule": result, "state": public_state()}


def handle_admin_mutation(event, action):
    if not require_admin(event):
        return response(401, {"error": "Sessão expirada ou inválida."})
    data = parse_body(event)
    try:
        if action == "setup":
            return response(200, setup_tournament(data))
        if action == "config":
            cfg = save_config(data)
            return response(200, {"config": cfg})
        if action == "player":
            item = upsert_player(data)
            return response(200, {"player": item})
        if action == "place":
            item = upsert_place(data)
            return response(200, {"place": item})
        if action == "date":
            item = upsert_date(data)
            return response(200, {"date": item})
        if action == "delete-player":
            delete_item("PLAYER", str(data.get("player_id", "")))
            return response(200, {"ok": True})
        if action == "delete-place":
            delete_item("PLACE", str(data.get("place_id", "")))
            return response(200, {"ok": True})
        if action == "delete-date":
            delete_item("DATE", str(data.get("date_id", "")))
            return response(200, {"ok": True})
        if action == "recalculate":
            result = generate_schedule()
            return response(200, result)
        if action == "result":
            item = set_match_result(data)
            return response(200, {"match": item})
    except ValueError as exc:
        return response(400, {"error": str(exc)})
    except Exception as exc:
        return response(500, {"error": f"Erro interno: {exc}"})
    return response(404, {"error": "Rota administrativa não encontrada."})


def lambda_handler(event, context):
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
