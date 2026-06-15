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


CONFIG = {
    "division_count": 1,
    "rules": {
        "1": {
            "key_count": 1,
            "promotion_count": 0,
            "relegation_count": 0,
        }
    },
}


def player(player_id):
    return {
        "player_id": player_id,
        "name": player_id,
        "division": 1,
        "chave": "A",
    }


def match(first, second, winner, loser_balls=0):
    return {
        "pair_key": app.build_pair_key(1, "A", first, second),
        "division": 1,
        "chave": "A",
        "player1_id": first,
        "player1_name": first,
        "player2_id": second,
        "player2_name": second,
        "winner_id": winner,
        "balls_p1": 7 if winner == first else loser_balls,
        "balls_p2": 7 if winner == second else loser_balls,
        "is_finished": True,
        "double_loss": False,
    }


def row(player_id, balance=0):
    return {
        "player_id": player_id,
        "name": player_id,
        "division": 1,
        "chave": "A",
        "points": 3,
        "wins": 1,
        "balls_for": 7,
        "balls_against": 7 - balance,
        "balls_balance": balance,
    }


def result_map(matches):
    return {item["pair_key"]: item for item in matches}


def test_two_player_tie_uses_direct_result_before_ball_balance():
    rows = [row("A", -8), row("B", 12)]
    direct = match("A", "B", "A", loser_balls=6)

    ordered, detail = app.resolve_points_tie(
        rows,
        result_map([direct]),
        1,
        "A",
        True,
        "signature",
        {},
    )

    assert [item["player_id"] for item in ordered] == ["A", "B"]
    assert detail["resolution"] == "direct"


def test_three_player_transitive_direct_results_define_all_positions():
    rows = [row("A"), row("B"), row("C")]
    matches = [
        match("A", "B", "A"),
        match("A", "C", "A"),
        match("B", "C", "B"),
    ]

    ordered, detail = app.resolve_points_tie(
        rows,
        result_map(matches),
        1,
        "A",
        True,
        "signature",
        {},
    )

    assert [item["player_id"] for item in ordered] == ["A", "B", "C"]
    assert detail["resolution"] == "direct"


def test_circular_direct_results_fall_back_to_ball_balance():
    rows = [row("A", 4), row("B", -2), row("C", 1)]
    matches = [
        match("A", "B", "A"),
        match("B", "C", "B"),
        match("C", "A", "C"),
    ]

    ordered, detail = app.resolve_points_tie(
        rows,
        result_map(matches),
        1,
        "A",
        True,
        "signature",
        {},
    )

    assert [item["player_id"] for item in ordered] == ["A", "C", "B"]
    assert detail["resolution"] == "balls_balance"


def circular_matches(loser_balls=0):
    return [
        match("A", "B", "A", loser_balls),
        match("B", "C", "B", 0),
        match("C", "A", "C", 0),
    ]


def test_equal_circular_tie_requires_manual_order_and_applies_current_decision():
    players = [player("A"), player("B"), player("C")]
    matches = circular_matches()
    first = app.calculate_standings_details(players, matches, [], CONFIG)
    tiebreak = first["tiebreaks"][0]
    manual = tiebreak["manual_groups"][0]

    assert tiebreak["resolution"] == "manual_required"
    assert manual["status"] == "required"
    assert len(manual["players"]) == 3
    assert all(
        row["rank_status"] == "tiebreak_pending"
        for row in first["standings"]["1"]["A"]
    )

    decision = {
        "tiebreak_id": manual["decision_id"],
        "ordered_player_ids": ["C", "A", "B"],
        "context_signature": manual["context_signature"],
    }
    resolved = app.calculate_standings_details(
        players,
        matches,
        [],
        CONFIG,
        [decision],
    )

    assert [row["player_id"] for row in resolved["standings"]["1"]["A"]] == ["C", "A", "B"]
    assert resolved["tiebreaks"][0]["resolution"] == "manual"
    assert all(
        row["rank_status"] != "tiebreak_pending"
        for row in resolved["standings"]["1"]["A"]
    )


def test_result_change_invalidates_saved_manual_order_immediately():
    players = [player("A"), player("B"), player("C")]
    original = app.calculate_standings_details(
        players,
        circular_matches(),
        [],
        CONFIG,
    )
    manual = original["tiebreaks"][0]["manual_groups"][0]
    decision = {
        "tiebreak_id": manual["decision_id"],
        "ordered_player_ids": ["C", "A", "B"],
        "context_signature": manual["context_signature"],
    }

    changed = app.calculate_standings_details(
        players,
        circular_matches(loser_balls=1),
        [],
        CONFIG,
        [decision],
    )

    assert [row["player_id"] for row in changed["standings"]["1"]["A"]] == ["B", "C", "A"]
    assert changed["tiebreaks"][0]["resolution"] == "balls_balance"


def test_calculated_standings_use_direct_result_even_when_loser_has_better_balance():
    players = [player("A"), player("B"), player("C"), player("D")]
    matches = [
        match("A", "B", "A", loser_balls=6),
        match("C", "A", "C"),
        match("B", "D", "B"),
        match("C", "D", "C"),
    ]

    standings = app.calculate_standings(players, matches, [], CONFIG)["1"]["A"]

    assert [item["player_id"] for item in standings] == ["C", "A", "B", "D"]
    assert next(item for item in standings if item["player_id"] == "B")["balls_balance"] > next(
        item for item in standings if item["player_id"] == "A"
    )["balls_balance"]


def test_save_tiebreak_decision_persists_complete_order(monkeypatch):
    players = [player("A"), player("B"), player("C")]
    matches = circular_matches()
    saved = []
    details = app.calculate_standings_details(players, matches, [], CONFIG)
    manual = details["tiebreaks"][0]["manual_groups"][0]

    monkeypatch.setattr(app, "get_players", lambda: players)
    monkeypatch.setattr(app, "get_matches", lambda: matches)
    monkeypatch.setattr(app, "get_results", lambda: [])
    monkeypatch.setattr(app, "get_config", lambda: CONFIG)
    monkeypatch.setattr(app, "get_tiebreak_decisions", lambda: [])
    monkeypatch.setattr(app, "put_item", lambda item: saved.append(dict(item)))

    result = app.save_tiebreak_decision({
        "decision_id": manual["decision_id"],
        "ordered_player_ids": ["B", "C", "A"],
    })

    assert result["ordered_player_ids"] == ["B", "C", "A"]
    assert result["context_signature"] == manual["context_signature"]
    assert saved[0]["type"] == "TIEBREAK"


def test_pending_manual_tiebreak_blocks_bracket_creation():
    config = {
        **CONFIG,
        "rules": {
            "1": {
                "key_count": 1,
                "promotion_count": 2,
                "relegation_count": 0,
            }
        },
    }
    details = app.calculate_standings_details(
        [player("A"), player("B"), player("C")],
        circular_matches(),
        [],
        config,
    )

    try:
        app.build_bracket_spec(1, details["standings"])
    except ValueError as exc:
        assert "desempates pendentes" in str(exc)
    else:
        raise AssertionError("O chaveamento não deveria ser criado com desempate pendente.")
