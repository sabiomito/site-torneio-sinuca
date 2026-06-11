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


def base_match():
    return {
        "pk": "MATCH",
        "sk": "match-1",
        "type": "MATCH",
        "match_id": "match-1",
        "pair_key": "D1#KA#player-1#player-2",
        "division": 1,
        "chave": "A",
        "player1_id": "player-1",
        "player1_name": "Jogador 1",
        "player2_id": "player-2",
        "player2_name": "Jogador 2",
        "winner_id": "",
        "balls_p1": 0,
        "balls_p2": 0,
        "is_finished": False,
        "double_loss": False,
    }


def players():
    return [
        {"player_id": "player-1", "name": "Jogador 1", "division": 1, "chave": "A"},
        {"player_id": "player-2", "name": "Jogador 2", "division": 1, "chave": "A"},
    ]


def standings_rows(match):
    config = {
        "division_count": 1,
        "rules": {
            "1": {
                "key_count": 1,
                "promotion_count": 0,
                "relegation_count": 0,
            }
        },
    }
    rows = app.calculate_standings(players(), [match], [], config)["1"]["A"]
    return {row["player_id"]: row for row in rows}


def test_double_loss_is_saved_as_finished_zero_to_zero(monkeypatch):
    match = base_match()
    saved = []
    monkeypatch.setattr(app, "get_item", lambda pk, sk: match if pk == "MATCH" else None)
    monkeypatch.setattr(app, "put_item", lambda item: saved.append(dict(item)))

    result = app.set_match_result({
        "match_id": "match-1",
        "double_loss": True,
        "winner_id": "player-1",
        "balls_p1": 7,
        "balls_p2": 5,
    })

    assert result["is_finished"] is True
    assert result["double_loss"] is True
    assert result["winner_id"] == ""
    assert result["balls_p1"] == 0
    assert result["balls_p2"] == 0
    history = next(item for item in saved if item.get("type") == "RESULT")
    assert history["double_loss"] is True
    assert history["winner_id"] == ""
    assert history["balls_p1"] == history["balls_p2"] == 0


def test_double_loss_counts_game_and_loss_for_both_without_points_or_balls():
    match = {
        **base_match(),
        "is_finished": True,
        "double_loss": True,
    }

    rows = standings_rows(match)

    for player_id in ("player-1", "player-2"):
        row = rows[player_id]
        assert row["played"] == 1
        assert row["wins"] == 0
        assert row["losses"] == 1
        assert row["points"] == 0
        assert row["balls_for"] == 0
        assert row["balls_against"] == 0
        assert row["balls_balance"] == 0


def test_clearing_double_loss_returns_match_to_pending(monkeypatch):
    match = {
        **base_match(),
        "is_finished": True,
        "double_loss": True,
    }
    saved = []
    deleted = []
    monkeypatch.setattr(app, "get_item", lambda pk, sk: match)
    monkeypatch.setattr(app, "put_item", lambda item: saved.append(dict(item)))
    monkeypatch.setattr(app, "delete_item", lambda pk, sk: deleted.append((pk, sk)))

    result = app.set_match_result({"match_id": "match-1", "clear": True})

    assert result["is_finished"] is False
    assert result["double_loss"] is False
    assert result["winner_id"] == ""
    assert deleted == [("RESULT", match["pair_key"])]


def test_legacy_finished_result_without_double_loss_keeps_original_scoring():
    legacy_match = {
        key: value
        for key, value in {
            **base_match(),
            "is_finished": True,
            "winner_id": "player-1",
            "balls_p1": 7,
            "balls_p2": 3,
        }.items()
        if key != "double_loss"
    }

    rows = standings_rows(legacy_match)

    assert rows["player-1"]["played"] == 1
    assert rows["player-1"]["wins"] == 1
    assert rows["player-1"]["losses"] == 0
    assert rows["player-1"]["points"] == 3
    assert rows["player-1"]["balls_for"] == 7
    assert rows["player-1"]["balls_against"] == 3
    assert rows["player-1"]["balls_balance"] == 4
    assert rows["player-2"]["played"] == 1
    assert rows["player-2"]["wins"] == 0
    assert rows["player-2"]["losses"] == 1
    assert rows["player-2"]["points"] == 0
    assert rows["player-2"]["balls_for"] == 3
    assert rows["player-2"]["balls_against"] == 7
    assert rows["player-2"]["balls_balance"] == -4


def test_legacy_database_records_are_exposed_with_double_loss_false(monkeypatch):
    legacy_match = {key: value for key, value in base_match().items() if key != "double_loss"}
    legacy_result = {
        "pk": "RESULT",
        "sk": legacy_match["pair_key"],
        "type": "RESULT",
        "pair_key": legacy_match["pair_key"],
    }
    monkeypatch.setattr(
        app,
        "scan_type",
        lambda item_type: [dict(legacy_match)] if item_type == "MATCH" else [dict(legacy_result)],
    )

    assert app.get_matches()[0]["double_loss"] is False
    assert app.get_results()[0]["double_loss"] is False
