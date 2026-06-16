import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def render_bracket_html():
    if not shutil.which("node"):
        pytest.skip("Node.js nao disponivel para validar o HTML do bracket.")
    script = r"""
const fs = require('fs');
const vm = require('vm');

const code = fs.readFileSync('frontend/js/bracket.js', 'utf8');
const context = {
  window: {
    innerHeight: 800,
    innerWidth: 1280,
    addEventListener: () => {},
  },
  escapeHtml: value => String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;'),
  divisionName: number => `${number} Divisao`,
};
vm.createContext(context);
vm.runInContext(code, context);
vm.runInContext(`
  const participant = (id, state = 'pending') => ({
    player: {player_id: id, name: id, photo_url: '', profile_url: ''},
    state,
  });
  const node = (round, nodeIndex, layoutIndex, sources = [], states = ['pending', 'pending']) => ({
    node_id: 'R' + round + 'M' + nodeIndex,
    round_number: round,
    node_index: nodeIndex,
    layout_index: layoutIndex,
    status: 'pending',
    source_node_ids: sources,
    player1: participant('P' + round + '-' + nodeIndex + '-1', states[0]),
    player2: participant('P' + round + '-' + nodeIndex + '-2', states[1]),
    match: null,
  });
  const bracket = {
    division: 1,
    participant_count: 16,
    total_rounds: 4,
    rounds: [
      {round_number: 1, name: 'Oitavas', nodes: [
        node(1, 0, 0, [], ['winner', 'loser']),
        node(1, 1, 3),
        node(1, 2, 4),
        node(1, 3, 1),
      ]},
      {round_number: 2, name: 'Quartas', nodes: [
        node(2, 0, 0, ['R1M0', 'R1M3']),
        node(2, 3, 1, ['R1M6', 'R1M1']),
      ]},
      {round_number: 3, name: 'Semifinal', nodes: [
        node(3, 0, 0, ['R2M0', 'R2M3']),
      ]},
      {round_number: 4, name: 'Final', nodes: [
        node(4, 0, 0, ['R3M0', 'R3M1']),
      ]},
    ],
  };
  globalThis.__html = renderKnockoutBracket(bracket);
  globalThis.__advancePath = bracketAdvancePath(
    {x: 10, y: 100},
    {centerX: 40, bottom: 20},
  );
  const fakeTargetNode = {
    getAttribute: name => ({
      'data-source-node-1': 'R1M0',
      'data-source-node-2': 'R1M3',
    })[name] || '',
  };
  globalThis.__sourceNodeOne = bracketSourceNodeId(fakeTargetNode, 1);
  globalThis.__targetSide = bracketTargetSide(fakeTargetNode, 'R1M3');
  const fakeMatchNode = (nodeStatus, slotStates) => ({
    dataset: {nodeStatus},
    querySelectorAll: () => slotStates.map(slotState => ({dataset: {slotState}})),
  });
  globalThis.__definedPendingColor = bracketAdvanceLineColor(
    fakeMatchNode('pending', ['pending', 'pending']),
  );
  globalThis.__waitingPendingColor = bracketAdvanceLineColor(
    fakeMatchNode('pending', ['pending', 'unknown']),
  );
`, context);
console.log(JSON.stringify({
  html: context.__html,
  advancePath: context.__advancePath,
  sourceNodeOne: context.__sourceNodeOne,
  targetSide: context.__targetSide,
  definedPendingColor: context.__definedPendingColor,
  waitingPendingColor: context.__waitingPendingColor,
}));
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def match_tag(html, node_id):
    match = re.search(
        rf'<div class="[^"]*bracket-match[^"]*"[^>]*data-bracket-node="{node_id}"[^>]*>',
        html,
        re.DOTALL,
    )
    assert match, f"Node {node_id} nao renderizado"
    return match.group(0)


def test_bracket_rendering_uses_layout_index_for_grid_position():
    html = render_bracket_html()["html"]

    first_round_tag = match_tag(html, "R1M3")
    second_round_tag = match_tag(html, "R2M3")

    assert 'data-layout-index="1"' in first_round_tag
    assert "grid-column:2 / span 1" in first_round_tag
    assert 'data-layout-index="1"' in second_round_tag
    assert "grid-column:3 / span 2" in second_round_tag


def test_bracket_rendering_orders_nodes_by_layout_index_for_single_row_grid():
    html = render_bracket_html()["html"]

    assert (
        html.index('data-bracket-node="R1M0"')
        < html.index('data-bracket-node="R1M3"')
        < html.index('data-bracket-node="R1M1"')
        < html.index('data-bracket-node="R1M2"')
    )
    assert html.index('data-bracket-node="R2M0"') < html.index('data-bracket-node="R2M3"')


def test_bracket_rendering_includes_internal_match_connector_with_player_states():
    html = render_bracket_html()["html"]

    assert "bracket-match-connector" in html
    assert "bracket-match-connector-winner" in html
    assert "bracket-match-connector-loser" in html


def test_bracket_rendering_includes_advance_line_layer_inside_match():
    html = render_bracket_html()["html"]
    first_match = html[
        html.index('data-bracket-node="R1M0"'):
        html.index('data-bracket-node="R1M3"')
    ]

    assert "bracket-match-advance-lines" in first_match
    assert "bracket-advance-lines" not in html


def test_bracket_advance_path_starts_at_match_center_and_ends_at_target_photo():
    payload = render_bracket_html()

    assert payload["advancePath"].startswith("M 10 100 ")
    assert payload["advancePath"].endswith("V 20")
    assert "H 40" in payload["advancePath"]


def test_bracket_source_node_attributes_are_read_from_dom_attributes():
    payload = render_bracket_html()

    assert payload["sourceNodeOne"] == "R1M0"
    assert payload["targetSide"] == 2


def test_bracket_pending_advance_line_is_gray_until_both_competitors_are_defined():
    payload = render_bracket_html()

    assert payload["definedPendingColor"] == "#ffd166"
    assert payload["waitingPendingColor"] == "#7f8fa3"
