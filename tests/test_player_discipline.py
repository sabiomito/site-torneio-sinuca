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


def player(player_id, status="active"):
    return {
        "pk": "PLAYER",
        "sk": player_id,
        "type": "PLAYER",
        "player_id": player_id,
        "name": f"Jogador {player_id}",
        "division": 1,
        "chave": "A",
        "competition_status": status,
    }


def match(match_id, first="player-1", second="player-2", **overrides):
    item = {
        "pk": "MATCH",
        "sk": match_id,
        "type": "MATCH",
        "match_id": match_id,
        "pair_key": app.build_pair_key(1, "A", first, second),
        "division": 1,
        "chave": "A",
        "player1_id": first,
        "player1_name": f"Jogador {first}",
        "player2_id": second,
        "player2_name": f"Jogador {second}",
        "winner_id": "",
        "balls_p1": 0,
        "balls_p2": 0,
        "is_finished": False,
        "double_loss": False,
    }
    item.update(overrides)
    return item


def test_banning_player_replaces_pending_and_finished_results_with_seven_to_zero(monkeypatch):
    players = {
        "player-1": player("player-1"),
        "player-2": player("player-2"),
        "player-3": player("player-3"),
    }
    matches = [
        match("match-1"),
        match(
            "match-2",
            first="player-3",
            second="player-1",
            winner_id="player-1",
            balls_p1=2,
            balls_p2=7,
            is_finished=True,
        ),
    ]
    saved = []

    def fake_get_item(pk, sk):
        if pk == "PLAYER":
            return players.get(sk)
        return None

    monkeypatch.setattr(app, "get_item", fake_get_item)
    monkeypatch.setattr(app, "get_matches", lambda: matches)
    monkeypatch.setattr(app, "put_item", lambda item: saved.append(dict(item)))

    result = app.set_player_status({
        "player_id": "player-1",
        "competition_status": "banned",
    })

    assert result["player"]["competition_status"] == "banned"
    assert result["affected_matches"] == 2
    assert matches[0]["winner_id"] == "player-2"
    assert (matches[0]["balls_p1"], matches[0]["balls_p2"]) == (0, 7)
    assert matches[1]["winner_id"] == "player-3"
    assert (matches[1]["balls_p1"], matches[1]["balls_p2"]) == (7, 0)
    assert all(item["is_finished"] for item in matches)

    saved_results = [item for item in saved if item.get("type") == "RESULT"]
    assert len(saved_results) == 2
    assert {item["winner_id"] for item in saved_results} == {"player-2", "player-3"}
    assert all(
        sorted((item["balls_p1"], item["balls_p2"])) == [0, 7]
        for item in saved_results
    )


def test_new_match_with_disqualified_player_is_created_as_seven_to_zero(monkeypatch):
    monkeypatch.setattr(app, "get_config", lambda: {"duration_minutes": 30})
    monkeypatch.setattr(app, "result_for_pair", lambda pair_key: None)
    monkeypatch.setattr(app, "make_id", lambda prefix: "match-new")

    round_item = {
        "round_id": "round-1",
        "name": "Local",
        "round_number": 1,
        "division": 1,
        "chave": "A",
        "date": "2026-06-15",
        "start_time": "10:00",
        "place_id": "place-1",
        "place_name": "Local",
    }
    created = app.build_match_item(
        round_item,
        player("player-1"),
        player("player-2", "disqualified"),
        0,
    )

    assert created["is_finished"] is True
    assert created["winner_id"] == "player-1"
    assert (created["balls_p1"], created["balls_p2"]) == (7, 0)
    assert created["administrative_loss_player_ids"] == ["player-2"]


def test_new_knockout_match_with_banned_player_is_also_created_as_seven_to_zero(monkeypatch):
    monkeypatch.setattr(app, "get_config", lambda: {"duration_minutes": 30})
    monkeypatch.setattr(app, "make_id", lambda prefix: "match-knockout")

    round_item = {
        "round_id": "round-knockout",
        "name": "Local",
        "round_number": 1,
        "stage_name": "Semifinal",
        "bracket_round": 1,
        "date": "2026-06-15",
        "start_time": "10:00",
        "place_id": "place-1",
        "place_name": "Local",
    }
    bracket = {
        "bracket_id": "bracket-1",
        "division": 1,
    }

    created = app.build_knockout_match(
        round_item,
        bracket,
        "R1M1",
        player("player-1", "banned"),
        player("player-2"),
        0,
    )

    assert created["is_finished"] is True
    assert created["winner_id"] == "player-2"
    assert (created["balls_p1"], created["balls_p2"]) == (0, 7)
    assert created["administrative_loss_player_ids"] == ["player-1"]


def test_manual_result_cannot_override_disciplinary_loss(monkeypatch):
    current_match = match("match-1")
    players = {
        "player-1": player("player-1", "disqualified"),
        "player-2": player("player-2"),
    }
    saved = []

    def fake_get_item(pk, sk):
        if pk == "MATCH":
            return current_match
        if pk == "PLAYER":
            return players.get(sk)
        return None

    monkeypatch.setattr(app, "get_item", fake_get_item)
    monkeypatch.setattr(app, "put_item", lambda item: saved.append(dict(item)))

    result = app.set_match_result({
        "match_id": "match-1",
        "winner_id": "player-1",
        "balls_p1": 7,
        "balls_p2": 4,
    })

    assert result["winner_id"] == "player-2"
    assert (result["balls_p1"], result["balls_p2"]) == (0, 7)
    assert any(item.get("type") == "RESULT" for item in saved)

    cleared = app.set_match_result({"match_id": "match-1", "clear": True})

    assert cleared["is_finished"] is True
    assert cleared["winner_id"] == "player-2"
    assert (cleared["balls_p1"], cleared["balls_p2"]) == (0, 7)


def test_disciplinary_status_replaces_promotion_or_relegation_status():
    players = [
        player("player-1", "disqualified"),
        player("player-2", "banned"),
        player("player-3"),
    ]
    config = {
        "division_count": 1,
        "rules": {
            "1": {
                "key_count": 1,
                "promotion_count": 1,
                "relegation_count": 1,
            }
        },
    }

    rows = app.calculate_standings(players, [], [], config)["1"]["A"]
    by_id = {row["player_id"]: row for row in rows}

    assert by_id["player-1"]["rank_status"] == "disqualified"
    assert by_id["player-2"]["rank_status"] == "banned"
    assert by_id["player-3"]["rank_status"] in {"promotion", "relegation", "normal"}
