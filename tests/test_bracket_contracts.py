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


def qualifier(chave, rank):
    return {
        "player_id": f"{chave}{rank}",
        "name": f"{chave} {rank}",
        "chave": chave,
        "group_rank": rank,
        "rank_status": "promotion",
        "points": 100 - rank,
        "balls_balance": rank,
        "balls_for": 10 - rank,
        "wins": 10 - rank,
    }


def standings_for_groups(*chaves):
    return {
        "1": {
            chave: [qualifier(chave, rank) for rank in range(1, 9)]
            for chave in chaves
        }
    }


def slot_pairs(bracket):
    slots = bracket["slots"]
    return [tuple(slots[index:index + 2]) for index in range(0, len(slots), 2)]


def knockout_result(bracket, node_id, player1_id, player2_id, winner_id):
    return {
        "phase": "knockout",
        "bracket_id": bracket["bracket_id"],
        "bracket_node_id": node_id,
        "is_finished": True,
        "player1_id": player1_id,
        "player2_id": player2_id,
        "winner_id": winner_id,
        "balls_p1": 7 if winner_id == player1_id else 0,
        "balls_p2": 7 if winner_id == player2_id else 0,
    }


def node_players(node):
    return (
        (node["player1"]["player"] or {}).get("player_id", ""),
        (node["player2"]["player"] or {}).get("player_id", ""),
    )


@pytest.mark.xfail(
    strict=True,
    reason="Known bracket bug: two-key seeding still alternates top seeds instead of mirroring A ranks against B ranks.",
)
def test_two_key_bracket_uses_requested_cross_group_order():
    bracket = app.build_bracket_spec(1, standings_for_groups("A", "B"))

    assert slot_pairs(bracket) == [
        ("A1", "B8"),
        ("A2", "B7"),
        ("A3", "B6"),
        ("A4", "B5"),
        ("A5", "B4"),
        ("A6", "B3"),
        ("A7", "B2"),
        ("A8", "B1"),
    ]


@pytest.mark.xfail(
    strict=True,
    reason="Known bracket bug: advancement links adjacent games instead of keeping the top seeds apart until later rounds.",
)
def test_single_key_winners_advance_to_balanced_semifinals():
    bracket = app.build_bracket_spec(1, standings_for_groups("A"))
    assert slot_pairs(bracket) == [
        ("A1", "A8"),
        ("A2", "A7"),
        ("A3", "A6"),
        ("A4", "A5"),
    ]
    matches = [
        knockout_result(bracket, "R1M0", "A1", "A8", "A1"),
        knockout_result(bracket, "R1M1", "A2", "A7", "A2"),
        knockout_result(bracket, "R1M2", "A3", "A6", "A3"),
        knockout_result(bracket, "R1M3", "A4", "A5", "A4"),
    ]

    view = app.build_bracket_view(bracket, [], matches, group_phase_complete=True)
    semifinals = view["rounds"][1]["nodes"]

    assert [node_players(node) for node in semifinals] == [
        ("A1", "A4"),
        ("A2", "A3"),
    ]
