import importlib
import os
import sys
from itertools import combinations
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")
os.environ.setdefault("AWS_DEFAULT_REGION", "sa-east-1")

app = importlib.import_module("app")


def players(count):
    return [
        {
            "player_id": f"player-{index}",
            "name": f"Jogador {index}",
            "division": 1,
            "chave": "A",
        }
        for index in range(1, count + 1)
    ]


def pair_key(first, second):
    return app.build_pair_key(1, "A", first["player_id"], second["player_id"])


def test_partial_automatic_round_skips_blocked_players_in_even_group():
    group = players(4)
    only_remaining = pair_key(group[2], group[3])
    used_pairs = {
        pair_key(first, second)
        for first, second in combinations(group, 2)
        if pair_key(first, second) != only_remaining
    }

    for seed in range(20):
        created = app.find_automatic_pairs(group, 1, "A", used_pairs, seed=seed)
        assert len(created) == 1
        assert pair_key(*created[0]) == only_remaining


def test_automatic_round_returns_largest_available_partial_matching():
    group = players(6)
    remaining = {
        pair_key(group[0], group[1]),
        pair_key(group[2], group[3]),
        pair_key(group[3], group[4]),
    }
    all_pairs = {
        pair_key(first, second)
        for first, second in combinations(group, 2)
    }
    created = app.find_automatic_pairs(group, 1, "A", all_pairs - remaining, seed=0)
    created_keys = {pair_key(first, second) for first, second in created}

    assert len(created) == 2
    assert created_keys <= remaining


def test_round_requirements_consider_player_conflicts_between_pending_matches():
    group = players(4)
    remaining = {
        pair_key(group[0], group[1]),
        pair_key(group[0], group[2]),
    }
    matches = [
        {"pair_key": pair_key(first, second)}
        for first, second in combinations(group, 2)
        if pair_key(first, second) not in remaining
    ]
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

    requirement = app.round_requirements(config, group, [], matches, [])[0]

    assert requirement["remaining_pairs"] == 2
    assert requirement["matches_per_round"] == 2
    assert requirement["missing_rounds"] == 2
