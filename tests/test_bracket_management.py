import importlib
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "sa-east-1")

app = importlib.import_module("app")


def player(player_id, name=None, division=1, chave="A"):
    return {
        "player_id": player_id,
        "name": name or player_id,
        "division": division,
        "chave": chave,
        "photo_url": "",
    }


def division_bracket():
    qualifiers = [
        {
            "player_id": f"p{index}",
            "name": f"Jogador {index}",
            "division": 1,
            "chave": "A",
            "group_rank": index,
            "seed": index,
        }
        for index in range(1, 5)
    ]
    return {
        "pk": "BRACKET",
        "sk": "DIVISION#1",
        "type": "BRACKET",
        "bracket_id": "bracket_division_1",
        "bracket_kind": "division",
        "division": 1,
        "participant_count": 4,
        "bracket_size": 4,
        "qualifiers": qualifiers,
        "slots": ["p1", "p4", "p2", "p3"],
        "created_at": "2026-01-01T00:00:00Z",
    }


def custom_bracket():
    return {
        "pk": "BRACKET",
        "sk": "CUSTOM#bracket_custom_1",
        "type": "BRACKET",
        "bracket_id": "bracket_custom_1",
        "bracket_kind": "custom",
        "division": 1001,
        "display_name": "Repescagem",
        "manual_override": True,
        "participant_count": 3,
        "bracket_size": 4,
        "qualifiers": [
            {"player_id": "p1", "name": "Ana", "division": 1, "chave": "A", "seed": 1},
            {"player_id": "p2", "name": "Bia", "division": 1, "chave": "A", "seed": 2},
            {"player_id": "p3", "name": "Caio", "division": 1, "chave": "B", "seed": 3},
        ],
        "slots": ["p1", "", "p2", "p3"],
        "created_at": "2026-01-01T00:00:00Z",
    }


def base_config():
    return {
        "division_count": 1,
        "duration_minutes": 30,
        "rules": {"1": {"key_count": 1, "promotion_count": 4, "relegation_count": 0}},
    }


def test_save_bracket_is_blocked_when_knockout_round_exists(monkeypatch):
    bracket = division_bracket()
    monkeypatch.setattr(app, "get_brackets", lambda: [bracket])
    monkeypatch.setattr(app, "get_rounds", lambda: [{
        "phase": "knockout",
        "bracket_id": "bracket_division_1",
        "is_finished": False,
    }])
    monkeypatch.setattr(app, "get_matches", lambda: [])

    with pytest.raises(ValueError, match="rodada criada"):
        app.save_bracket_structure({
            "bracket_id": "bracket_division_1",
            "slots": ["p1", "p4", "p2", "p3"],
        })


def test_save_division_bracket_persists_manual_structure(monkeypatch):
    bracket = division_bracket()
    saved = {}
    players = [player(f"p{index}", f"Jogador {index}") for index in range(1, 5)]
    monkeypatch.setattr(app, "get_brackets", lambda: [bracket])
    monkeypatch.setattr(app, "get_rounds", lambda: [])
    monkeypatch.setattr(app, "get_matches", lambda: [])
    monkeypatch.setattr(app, "get_results", lambda: [])
    monkeypatch.setattr(app, "get_config", base_config)
    monkeypatch.setattr(app, "get_players", lambda: players)
    monkeypatch.setattr(app, "get_tiebreak_decisions", lambda: [])
    monkeypatch.setattr(app, "division_group_phase_complete", lambda *args: True)
    monkeypatch.setattr(app, "put_item", lambda item: saved.update(item))

    result = app.save_bracket_structure({
        "bracket_id": "bracket_division_1",
        "slots": ["p2", "p3", "p1", "p4"],
    })

    assert result["bracket"]["manual_override"] is True
    assert saved["slots"] == ["p2", "p3", "p1", "p4"]
    assert {item["player_id"] for item in saved["qualifiers"]} == {"p1", "p2", "p3", "p4"}


def test_delete_custom_bracket_is_blocked_when_round_exists(monkeypatch):
    bracket = custom_bracket()
    monkeypatch.setattr(app, "get_brackets", lambda: [bracket])
    monkeypatch.setattr(app, "get_rounds", lambda: [{
        "phase": "knockout",
        "bracket_id": "bracket_custom_1",
    }])
    monkeypatch.setattr(app, "get_matches", lambda: [])

    with pytest.raises(ValueError, match="rodada criada"):
        app.delete_custom_bracket({"bracket_id": "bracket_custom_1"})


def test_public_brackets_include_custom_bracket_with_display_name(monkeypatch):
    bracket = custom_bracket()
    players = [
        player("p1", "Ana"),
        player("p2", "Bia"),
        player("p3", "Caio", chave="B"),
    ]
    monkeypatch.setattr(app, "get_brackets", lambda: [bracket])

    views = app.build_public_brackets(
        base_config(),
        players,
        [],
        [],
        {"1": {}},
    )

    assert "bracket_custom_1" in views
    assert views["bracket_custom_1"]["display_name"] == "Repescagem"
    assert views["bracket_custom_1"]["bracket_kind"] == "custom"
    assert views["bracket_custom_1"]["rounds"][0]["nodes"][0]["player1"]["player"]["name"] == "Ana"


def test_create_knockout_rounds_uses_custom_bracket_and_display_name(monkeypatch):
    bracket = custom_bracket()
    players = [
        player("p1", "Ana"),
        player("p2", "Bia"),
        player("p3", "Caio", chave="B"),
    ]
    saved = []
    ids = iter(["round_custom", "match_custom"])
    monkeypatch.setattr(app, "get_config", base_config)
    monkeypatch.setattr(app, "get_brackets", lambda: [bracket])
    monkeypatch.setattr(app, "get_players", lambda: players)
    monkeypatch.setattr(app, "get_matches", lambda: [])
    monkeypatch.setattr(app, "get_results", lambda: [])
    monkeypatch.setattr(app, "get_tiebreak_decisions", lambda: [])
    monkeypatch.setattr(app, "put_item", lambda item: saved.append(dict(item)))
    monkeypatch.setattr(app, "make_id", lambda prefix: next(ids))

    result = app.create_knockout_rounds({
        "bracket_id": "bracket_custom_1",
        "name": "Bar Central",
        "date": "2026-06-20",
        "start_time": "09:00",
    })

    assert result["created"] == 1
    assert result["rounds"][0]["bracket_display_name"] == "Repescagem"
    assert result["rounds"][0]["division"] == 1001
    assert result["matches"][0]["bracket_display_name"] == "Repescagem"
    assert result["matches"][0]["player1_id"] == "p2"
    assert result["matches"][0]["player2_id"] == "p3"
