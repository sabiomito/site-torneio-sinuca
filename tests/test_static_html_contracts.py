from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def read_page(name):
    return (FRONTEND / name).read_text(encoding="utf-8")


def read_js(name):
    return (FRONTEND / "js" / name).read_text(encoding="utf-8")


def assert_contains_all(html, snippets):
    missing = [snippet for snippet in snippets if snippet not in html]
    assert not missing


def test_admin_page_keeps_all_user_flow_sections_and_forms():
    html = read_page("admin.html")

    assert_contains_all(
        html,
        [
            'id="login-form"',
            'id="admin-password"',
            'id="admin-panel"',
            'data-section="config"',
            'data-section="players"',
            'data-section="rounds"',
            'data-section="knockout"',
            'data-section="matches"',
            'data-section="sponsors"',
            'data-section="tv-config"',
            'data-section="danger"',
            'id="config-form"',
            'id="player-form"',
            'id="round-form"',
            'id="manual-round-editor"',
            'id="knockout-round-form"',
            'id="admin-matches"',
            'id="sponsor-form"',
            'id="tv-config-form"',
            'id="clear-database"',
        ],
    )


def test_admin_page_keeps_filter_and_print_controls_used_by_e2e_flows():
    html = read_page("admin.html")

    assert_contains_all(
        html,
        [
            'id="admin-filter-date"',
            'id="admin-filter-round"',
            'id="admin-filter-place"',
            'id="admin-filter-player"',
            'id="admin-filter-division"',
            'id="admin-filter-chave"',
            'id="admin-filter-status"',
            'id="admin-clear-filters"',
            'id="admin-print-filtered-matches"',
        ],
    )


def test_tv_config_accepts_zero_second_durations_in_admin_and_cycle():
    admin_html = read_page("admin.html")
    admin_js = read_js("admin.js")
    telao_js = read_js("telao.js")

    assert_contains_all(
        admin_html,
        [
            'id="tv-table-seconds" min="0"',
            'id="tv-bracket-seconds" min="0"',
            'id="tv-sponsor-seconds" min="0"',
            'id="tv-match-seconds" min="0"',
        ],
    )
    assert_contains_all(
        admin_js,
        [
            "tv.table_seconds ?? 60",
            "tv.bracket_seconds ?? 60",
            "tv.sponsor_seconds ?? 30",
            "tv.match_seconds ?? 5",
        ],
    )
    assert_contains_all(
        telao_js,
        [
            "function tvSeconds(value, fallback)",
            "return Number.isFinite(seconds) ? Math.max(0, seconds) : fallback;",
            "function hasTablePhase()",
            "function renderNoActiveCycle()",
        ],
    )


def test_public_scoreboard_page_keeps_filterable_matches_contract():
    html = read_page("index.html")

    assert_contains_all(
        html,
        [
            'id="standings"',
            'id="filter-date"',
            'id="filter-place"',
            'id="filter-player"',
            'id="filter-division"',
            'id="filter-chave"',
            'id="filter-status"',
            'id="clear-filters"',
            'id="print-filtered-matches"',
            'id="matches-count"',
            'id="matches"',
            'src="/js/api.js"',
            'src="/js/bracket.js"',
            'src="/js/public.js"',
        ],
    )


def test_telao_and_player_pages_keep_public_entrypoints():
    telao = read_page("telao.html")
    player = read_page("player.html")

    assert_contains_all(
        telao,
        [
            'id="telao-zoom-out"',
            'id="telao-zoom-in"',
            'id="telao-radio-menu-button"',
            'id="telao-radio-menu"',
            'id="telao-radio-toggle"',
            'id="telao-countdown"',
            'id="telao-grid"',
            'id="telao-radio-audio"',
            'src="/js/bracket.js"',
            'src="/js/telao.js"',
        ],
    )
    assert_contains_all(
        player,
        [
            'id="player-title"',
            'id="player-subtitle"',
            'id="player-matches"',
            'src="/js/player.js"',
        ],
    )
