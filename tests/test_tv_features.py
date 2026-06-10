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


def match(index, *, finished=False, division=1, chave="A", place="place-1"):
    return {
        "match_id": f"match-{index:02d}",
        "date": f"2026-06-{(index % 28) + 1:02d}",
        "time": f"{8 + (index % 10):02d}:00",
        "place_id": place,
        "division": division,
        "chave": chave,
        "round_id": f"round-{index % 3}",
        "player1_id": "player-1",
        "player2_id": f"player-{index + 2}",
        "is_finished": finished,
        "result_saved_at": f"2026-06-01T10:{index:02d}:00Z" if finished else "",
    }


def test_tv_config_defaults_and_limits():
    assert app.normalize_tv_config() == {
        "table_seconds": 60,
        "sponsor_seconds": 30,
        "match_seconds": 5,
        "filters": {
            "date": "",
            "round": "",
            "place": "",
            "player": "",
            "division": "",
            "chave": "",
            "status": "",
        },
    }
    normalized = app.normalize_tv_config({
        "table_seconds": 0,
        "sponsor_seconds": 99999,
        "match_seconds": 8,
        "filters": {"status": "invalid"},
    })
    assert normalized["table_seconds"] == 1
    assert normalized["sponsor_seconds"] == 3600
    assert normalized["match_seconds"] == 8
    assert normalized["filters"]["status"] == ""


def test_match_filters_support_finished_pending_and_combination():
    matches = [
        match(1, finished=True, division=1, chave="A", place="green"),
        match(2, finished=False, division=1, chave="A", place="green"),
        match(3, finished=True, division=2, chave="B", place="blue"),
    ]
    finished = app.filtered_matches(matches, {"status": "finished"})
    pending = app.filtered_matches(matches, {"status": "pending"})
    combined = app.filtered_matches(matches, {
        "status": "finished",
        "division": "2",
        "chave": "b",
        "place": "blue",
    })
    assert [item["match_id"] for item in finished] == ["match-01", "match-03"]
    assert [item["match_id"] for item in pending] == ["match-02"]
    assert [item["match_id"] for item in combined] == ["match-03"]


def test_default_tv_cycle_uses_latest_20_results_then_orders_by_match_date():
    matches = [match(index, finished=True) for index in range(25)]
    matches.extend([match(30, finished=False), match(31, finished=False)])
    selected = app.tv_cycle_matches(matches, app.normalize_tv_config())
    assert len(selected) == 20
    assert {item["match_id"] for item in selected} == {
        f"match-{index:02d}" for index in range(5, 25)
    }
    assert selected == sorted(
        selected,
        key=lambda item: (
            item["date"],
            item["time"],
            item.get("place_name", ""),
            item.get("round_number", 999),
            item["match_id"],
        ),
    )


def test_configured_tv_cycle_uses_filters_instead_of_latest_result_fallback():
    matches = [
        match(1, finished=True, division=1),
        match(2, finished=False, division=2),
        match(3, finished=False, division=2),
    ]
    config = app.normalize_tv_config({
        "filters": {"division": "2", "status": "pending"},
    })
    selected = app.tv_cycle_matches(matches, config)
    assert [item["match_id"] for item in selected] == ["match-02", "match-03"]


def test_profile_html_uses_player_title_and_configured_photo(monkeypatch):
    monkeypatch.setattr(app, "get_players", lambda: [{
        "player_id": "player-1",
        "name": "João da Silva",
        "photo_url": "/media/players/player-1/photo-version.jpg",
        "short_message": "Minha frase.",
        "division": 1,
        "chave": "A",
    }])
    event = {
        "headers": {
            "x-site-host": "example.cloudfront.net",
            "x-forwarded-proto": "https",
        }
    }
    html = app.profile_html(event, "joao-da-silva")
    expected_title = "Perfil de João da Silva do 2° Campeonato de Sinuca de Entre Folhas"
    assert f'<meta property="og:title" content="{expected_title}">' in html
    assert 'content="https://example.cloudfront.net/media/players/player-1/photo-version.jpg"' in html
    assert 'content="https://example.cloudfront.net/perfil/joao-da-silva"' in html


def test_public_state_can_omit_all_match_payloads(monkeypatch):
    config = {
        "division_count": 1,
        "duration_minutes": 30,
        "rules": {"1": {"key_count": 1, "promotion_count": 0, "relegation_count": 0}},
        "tv_config": app.normalize_tv_config(),
    }
    monkeypatch.setattr(app, "get_config", lambda: config)
    monkeypatch.setattr(app, "get_players", lambda: [])
    monkeypatch.setattr(app, "get_rounds", lambda: [])
    monkeypatch.setattr(app, "get_matches", lambda: [match(1, finished=True)])
    monkeypatch.setattr(app, "get_results", lambda: [{"type": "RESULT"}])
    monkeypatch.setattr(app, "get_sponsors", lambda: [])
    state = app.public_state(include_matches=False)
    assert state["matches"] == []
    assert state["results"] == []
    assert state["latest_result"] is None
    assert state["tv_matches"] == []
