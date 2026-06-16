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


def finished_match(round_number, node_index, first, second, winner):
    return {
        "match_id": f"match-r{round_number}-{node_index}",
        "phase": "knockout",
        "bracket_id": "bracket-1",
        "bracket_node_id": f"R{round_number}M{node_index}",
        "player1_id": first,
        "player2_id": second,
        "winner_id": winner,
        "balls_p1": 7 if winner == first else 0,
        "balls_p2": 7 if winner == second else 0,
        "is_finished": True,
    }


def source_ids(view, round_number):
    return [
        tuple(node["source_node_ids"])
        for node in view["rounds"][round_number - 1]["nodes"]
    ]


def round_player_ids(view, round_number):
    return [
        (
            node["player1"]["player"]["player_id"],
            node["player2"]["player"]["player_id"],
        )
        for node in view["rounds"][round_number - 1]["nodes"]
    ]


def layout_order_ids(view, round_number):
    return [
        node["node_id"]
        for node in sorted(
            view["rounds"][round_number - 1]["nodes"],
            key=lambda item: item["layout_index"],
        )
    ]


def players_from_qualifiers(qualifiers):
    return [
        {
            "player_id": qualifier["player_id"],
            "name": qualifier["name"],
            "division": qualifier.get("division", 1),
            "chave": qualifier.get("chave", "A"),
        }
        for qualifier in qualifiers
    ]


def two_group_qualifiers():
    qualifiers = []
    seed = 1
    for rank in range(1, 9):
        for chave in ("A", "B"):
            qualifiers.append({
                "player_id": f"{chave}{rank}",
                "name": f"{chave} {rank}",
                "division": 1,
                "chave": chave,
                "group_rank": rank,
                "seed": seed,
            })
            seed += 1
    return qualifiers


def single_group_qualifiers(count):
    return [
        {
            "player_id": f"A{rank}",
            "name": f"A {rank}",
            "division": 1,
            "chave": "A",
            "group_rank": rank,
            "seed": rank,
        }
        for rank in range(1, count + 1)
    ]


def first_round_matches_from_slots(slots, winners):
    return [
        finished_match(
            1,
            index,
            slots[index * 2],
            slots[index * 2 + 1],
            winner,
        )
        for index, winner in enumerate(winners)
    ]


def test_two_groups_are_numbered_from_a1_vs_b8_through_a8_vs_b1():
    bracket_size, slots = app.bracket_slots_for_qualifiers(two_group_qualifiers())
    games = [tuple(slots[index:index + 2]) for index in range(0, len(slots), 2)]

    assert bracket_size == 16
    assert games == [
        ("A1", "B8"),
        ("A2", "B7"),
        ("A3", "B6"),
        ("A4", "B5"),
        ("A5", "B4"),
        ("A6", "B3"),
        ("A7", "B2"),
        ("A8", "B1"),
    ]


def test_single_group_example_pairs_game_a_against_d_and_b_against_c():
    qualifiers = single_group_qualifiers(8)
    bracket_size, slots = app.bracket_slots_for_qualifiers(qualifiers)
    bracket = {
        "bracket_id": "bracket-1",
        "division": 1,
        "participant_count": 8,
        "bracket_size": bracket_size,
        "slots": slots,
        "qualifiers": qualifiers,
    }
    view = app.build_bracket_view(
        bracket,
        players_from_qualifiers(qualifiers),
        first_round_matches_from_slots(slots, ["A1", "A2", "A3", "A4"]),
    )

    assert bracket_size == 8
    assert [tuple(slots[index:index + 2]) for index in range(0, len(slots), 2)] == [
        ("A1", "A8"),
        ("A2", "A7"),
        ("A3", "A6"),
        ("A4", "A5"),
    ]
    assert source_ids(view, 2) == [
        ("R1M0", "R1M3"),
        ("R1M1", "R1M2"),
    ]
    assert round_player_ids(view, 2) == [
        ("A1", "A4"),
        ("A2", "A3"),
    ]
    assert layout_order_ids(view, 1) == ["R1M0", "R1M3", "R1M1", "R1M2"]


def test_two_group_example_pairs_next_round_as_requested_and_lays_out_semifinals():
    qualifiers = two_group_qualifiers()
    bracket_size, slots = app.bracket_slots_for_qualifiers(qualifiers)
    bracket = {
        "bracket_id": "bracket-1",
        "division": 1,
        "participant_count": 16,
        "bracket_size": bracket_size,
        "slots": slots,
        "qualifiers": qualifiers,
    }
    first_round = first_round_matches_from_slots(
        slots,
        ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"],
    )
    quarterfinals = [
        finished_match(2, 0, "A1", "A4", "A1"),
        finished_match(2, 1, "A3", "A6", "A3"),
        finished_match(2, 2, "A5", "A8", "A5"),
        finished_match(2, 3, "A7", "A2", "A7"),
    ]
    view = app.build_bracket_view(
        bracket,
        players_from_qualifiers(qualifiers),
        first_round + quarterfinals,
    )

    assert [tuple(slots[index:index + 2]) for index in range(0, len(slots), 2)] == [
        ("A1", "B8"),
        ("A2", "B7"),
        ("A3", "B6"),
        ("A4", "B5"),
        ("A5", "B4"),
        ("A6", "B3"),
        ("A7", "B2"),
        ("A8", "B1"),
    ]
    assert source_ids(view, 2) == [
        ("R1M0", "R1M3"),
        ("R1M2", "R1M5"),
        ("R1M4", "R1M7"),
        ("R1M6", "R1M1"),
    ]
    assert round_player_ids(view, 2) == [
        ("A1", "A4"),
        ("A3", "A6"),
        ("A5", "A8"),
        ("A7", "A2"),
    ]
    assert source_ids(view, 3) == [
        ("R2M0", "R2M3"),
        ("R2M1", "R2M2"),
    ]
    assert round_player_ids(view, 3) == [
        ("A1", "A7"),
        ("A3", "A5"),
    ]
    assert layout_order_ids(view, 1) == [
        "R1M0",
        "R1M3",
        "R1M6",
        "R1M1",
        "R1M2",
        "R1M5",
        "R1M4",
        "R1M7",
    ]
    assert layout_order_ids(view, 2) == ["R2M0", "R2M3", "R2M1", "R2M2"]


def test_eight_initial_games_follow_requested_quarterfinal_and_semifinal_map():
    bracket = {
        "bracket_id": "bracket-1",
        "division": 1,
        "participant_count": 16,
        "bracket_size": 16,
        "slots": [f"player-{index}" for index in range(1, 17)],
    }
    first_round = [
        finished_match(
            1,
            index,
            f"player-{index * 2 + 1}",
            f"player-{index * 2 + 2}",
            f"player-{index * 2 + 1}",
        )
        for index in range(8)
    ]
    quarterfinals = [
        finished_match(2, 0, "player-1", "player-7", "player-1"),
        finished_match(2, 1, "player-5", "player-11", "player-5"),
        finished_match(2, 2, "player-9", "player-15", "player-9"),
        finished_match(2, 3, "player-13", "player-3", "player-13"),
    ]

    view = app.build_bracket_view(
        bracket,
        players(16),
        first_round + quarterfinals,
    )

    assert source_ids(view, 2) == [
        ("R1M0", "R1M3"),
        ("R1M2", "R1M5"),
        ("R1M4", "R1M7"),
        ("R1M6", "R1M1"),
    ]
    assert source_ids(view, 3) == [
        ("R2M0", "R2M3"),
        ("R2M1", "R2M2"),
    ]

    quarterfinal_players = [
        (
            node["player1"]["player"]["player_id"],
            node["player2"]["player"]["player_id"],
        )
        for node in view["rounds"][1]["nodes"]
    ]
    assert quarterfinal_players == [
        ("player-1", "player-7"),
        ("player-5", "player-11"),
        ("player-9", "player-15"),
        ("player-13", "player-3"),
    ]

    semifinal_players = [
        {
            node["player1"]["player"]["player_id"],
            node["player2"]["player"]["player_id"],
        }
        for node in view["rounds"][2]["nodes"]
    ]
    assert semifinal_players == [
        {"player-1", "player-13"},
        {"player-5", "player-9"},
    ]


def test_four_initial_games_follow_a_vs_d_and_b_vs_c():
    bracket = {
        "bracket_id": "bracket-1",
        "division": 1,
        "participant_count": 8,
        "bracket_size": 8,
        "slots": [f"player-{index}" for index in range(1, 9)],
    }

    view = app.build_bracket_view(bracket, players(8), [])

    assert source_ids(view, 2) == [
        ("R1M0", "R1M3"),
        ("R1M1", "R1M2"),
    ]


def test_source_heuristic_covers_every_game_once_for_supported_bracket_sizes():
    for source_count in (2, 4, 8, 16, 32):
        pairs = app.bracket_source_pairs(source_count)
        flattened = [source for pair in pairs for source in pair]

        assert len(pairs) == source_count // 2
        assert sorted(flattened) == list(range(source_count))


def test_single_group_keeps_first_and_second_seeds_on_opposite_semifinals():
    qualifiers = [
        {
            "player_id": f"A{rank}",
            "name": f"A {rank}",
            "division": 1,
            "chave": "A",
            "group_rank": rank,
            "seed": rank,
        }
        for rank in range(1, 17)
    ]
    bracket_size, slots = app.bracket_slots_for_qualifiers(qualifiers)
    bracket = {
        "bracket_size": bracket_size,
        "slots": slots,
        "qualifiers": qualifiers,
    }

    first_seed_descendants = app.knockout_descendant_node_ids(
        {"bracket_node_id": "R1M0"},
        bracket,
    )
    second_seed_descendants = app.knockout_descendant_node_ids(
        {"bracket_node_id": "R1M1"},
        bracket,
    )

    assert "R3M0" in first_seed_descendants
    assert "R3M1" in second_seed_descendants
    assert "R4M0" in first_seed_descendants & second_seed_descendants


def test_two_large_groups_keep_both_group_leaders_on_opposite_semifinals():
    qualifiers = []
    seed = 1
    for rank in range(1, 17):
        for chave in ("A", "B"):
            qualifiers.append({
                "player_id": f"{chave}{rank}",
                "name": f"{chave} {rank}",
                "division": 1,
                "chave": chave,
                "group_rank": rank,
                "seed": seed,
            })
            seed += 1
    bracket_size, slots = app.bracket_slots_for_qualifiers(qualifiers)
    bracket = {
        "bracket_size": bracket_size,
        "slots": slots,
        "qualifiers": qualifiers,
    }

    leader_a = app.knockout_descendant_node_ids(
        {"bracket_node_id": "R1M0"},
        bracket,
    )
    leader_b = app.knockout_descendant_node_ids(
        {"bracket_node_id": "R1M15"},
        bracket,
    )

    assert "R4M0" in leader_a
    assert "R4M1" in leader_b
    assert "R5M0" in leader_a & leader_b


def test_odd_number_of_qualifiers_keeps_byes_and_valid_connections():
    qualifiers = [
        {
            "player_id": f"player-{index}",
            "name": f"Jogador {index}",
            "division": 1,
            "chave": "A",
            "group_rank": index,
            "seed": index,
        }
        for index in range(1, 6)
    ]
    bracket_size, slots = app.bracket_slots_for_qualifiers(qualifiers)
    bracket = {
        "bracket_id": "bracket-1",
        "division": 1,
        "participant_count": 5,
        "bracket_size": bracket_size,
        "slots": slots,
        "qualifiers": qualifiers,
    }

    view = app.build_bracket_view(bracket, players(5), [])

    assert bracket_size == 8
    assert sum(1 for node in view["rounds"][0]["nodes"] if node["status"] == "bye") == 3
    assert source_ids(view, 2) == [
        ("R1M0", "R1M3"),
        ("R1M1", "R1M2"),
    ]


def test_descendant_lookup_uses_the_same_non_sequential_map():
    bracket = {"bracket_size": 16}

    assert app.knockout_descendant_node_ids(
        {"bracket_node_id": "R1M3"},
        bracket,
    ) == {"R2M0", "R3M0", "R4M0"}
    assert app.knockout_descendant_node_ids(
        {"bracket_node_id": "R1M6"},
        bracket,
    ) == {"R2M3", "R3M0", "R4M0"}


def test_existing_alternating_first_round_is_mapped_by_group_rank():
    qualifiers = two_group_qualifiers()
    bracket = {
        "bracket_id": "bracket-1",
        "division": 1,
        "participant_count": 16,
        "bracket_size": 16,
        "qualifiers": qualifiers,
        "slots": [
            "A1", "B8",
            "B1", "A8",
            "A2", "B7",
            "B2", "A7",
            "A3", "B6",
            "B3", "A6",
            "A4", "B5",
            "B4", "A5",
        ],
    }
    bracket_players = [
        {
            "player_id": qualifier["player_id"],
            "name": qualifier["name"],
            "division": 1,
            "chave": qualifier["chave"],
        }
        for qualifier in qualifiers
    ]

    view = app.build_bracket_view(bracket, bracket_players, [])

    assert source_ids(view, 2) == [
        ("R1M0", "R1M6"),
        ("R1M4", "R1M5"),
        ("R1M7", "R1M1"),
        ("R1M3", "R1M2"),
    ]


def test_pairing_maximizes_matches_between_different_groups():
    qualifiers = []
    for chave, count in (("A", 5), ("B", 3), ("C", 2)):
        qualifiers.extend({
            "player_id": f"{chave}-{rank}",
            "name": f"{chave} {rank}",
            "chave": chave,
            "group_rank": rank,
        } for rank in range(1, count + 1))
    qualifiers.sort(key=app.qualifier_sort_key)

    pairs = app.pair_qualifiers_cross_group(qualifiers)

    assert len(pairs) == 5
    assert all(first["chave"] != second["chave"] for first, second in pairs)
