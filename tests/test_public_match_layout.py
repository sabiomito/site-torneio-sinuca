import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def render_matches_html():
    if not shutil.which("node"):
        pytest.skip("Node.js nao disponivel para validar o HTML do frontend.")
    script = r"""
const fs = require('fs');
const vm = require('vm');

const code = fs.readFileSync('frontend/js/api.js', 'utf8');
const context = {
  window: {APP_CONFIG: {API_BASE_URL: '/api'}},
  localStorage: {getItem: () => '', setItem: () => {}, removeItem: () => {}},
  location: {origin: 'http://localhost'},
  URL,
};
vm.createContext(context);
vm.runInContext(code, context);
vm.runInContext(`
  const container = {innerHTML: ''};
  renderMatches(container, [{
    match_id: 'match-1',
    division: 1,
    chave: 'A',
    round_number: 12,
    date: '2026-06-15',
    time: '08:30',
    place_name: 'Roberinho',
    player1_id: 'player-1',
    player1_name: 'Roberinho',
    player2_id: 'player-2',
    player2_name: 'Tigrao',
    winner_id: 'player-1',
    balls_p1: 7,
    balls_p2: 5,
    is_finished: true,
    double_loss: false,
  }]);
  globalThis.__html = container.innerHTML;
`, context);
console.log(JSON.stringify(context.__html));
"""
    result = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_filtered_matches_use_separate_visual_clusters_and_player_cards():
    html = render_matches_html()

    assert html.count("match-info-cluster") == 2
    assert html.count("match-info-chip") == 6
    assert "match-info-stage" in html
    assert "match-info-schedule" in html
    assert "match-scoreline" in html
    assert "match-player-card-win" in html
    assert "match-player-card-loss" in html
    assert '<span class="match-score-number">7</span>' in html
    assert '<span class="match-score-versus">x</span>' in html
    assert '<span class="match-score-number">5</span>' in html
    assert "match-group" not in html

    assert html.index("match-info-stage") < html.index("match-info-schedule") < html.index("match-scoreline")
    assert html.index("Chave A") < html.index("Rodada 12")
    assert (
        html.index("match-player-card-win")
        < html.index('<span class="match-score-number">7</span>')
        < html.index('<span class="match-score-versus">x</span>')
        < html.index('<span class="match-score-number">5</span>')
        < html.index("match-player-card-loss")
    )
