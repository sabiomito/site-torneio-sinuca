import base64
import io
import re
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import pytest
from PIL import Image
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait
from urllib.error import HTTPError

from support import ADMIN_PASSWORD, BASE_URL, deterministic_color, get_bytes, jpeg_data


GROUPS = [
    {"division": 1, "chave": "A", "place": "Sala Verde"},
    {"division": 2, "chave": "A", "place": "Sala Azul"},
    {"division": 2, "chave": "B", "place": "Sala Dourada"},
]
PLAYERS_PER_GROUP = 16
MAIN_ROUNDS_PER_GROUP = 5


def progress(message):
    print(f"[E2E completo] {message}", flush=True)


def wait(driver, seconds=240):
    return WebDriverWait(driver, seconds)


def click(driver, element):
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'}); arguments[0].click();", element)


def set_input(driver, element_id, value):
    field = wait(driver).until(EC.presence_of_element_located((By.ID, element_id)))
    field.clear()
    field.send_keys(value)
    return field


def select_value(driver, element_id, value):
    select = wait(driver).until(EC.presence_of_element_located((By.ID, element_id)))
    Select(select).select_by_value(str(value))
    return select


def admin_state(driver):
    return driver.execute_script(
        "return typeof adminState !== 'undefined' ? adminState : null;"
    )


def wait_admin_state(driver, predicate, seconds=240):
    def state_when_ready(browser):
        state = admin_state(browser)
        return state if state and predicate(state) else False

    return WebDriverWait(driver, seconds).until(state_when_ready)


def open_admin(driver):
    driver.get(f"{BASE_URL}/admin")
    try:
        wait(driver, 20).until(EC.visibility_of_element_located((By.ID, "admin-panel")))
    except TimeoutException:
        password = wait(driver).until(EC.visibility_of_element_located((By.ID, "admin-password")))
        password.send_keys(ADMIN_PASSWORD)
        driver.find_element(By.ID, "login-form").submit()
        wait(driver).until(EC.visibility_of_element_located((By.ID, "admin-panel")))


def open_section(driver, name):
    section = wait(driver).until(EC.presence_of_element_located((By.CSS_SELECTOR, f'[data-section="{name}"]')))
    if "closed" in section.get_attribute("class").split():
        click(driver, section.find_element(By.CSS_SELECTOR, ".collapse-title"))
    return section


def clear_database_through_ui(driver):
    progress("Limpando somente o banco local pelo painel...")
    open_admin(driver)
    open_section(driver, "danger")
    click(driver, driver.find_element(By.ID, "clear-database"))
    wait(driver).until(EC.alert_is_present()).accept()
    prompt = wait(driver).until(EC.alert_is_present())
    prompt.send_keys("LIMPAR")
    prompt.accept()
    wait_admin_state(
        driver,
        lambda state: not state["players"]
        and not state["rounds"]
        and not state["matches"]
        and not state["sponsors"],
    )


def configure_tournament_through_ui(driver):
    progress("Configurando duas divisoes e tres chaves pelo formulario...")
    open_section(driver, "config")
    set_input(driver, "division-count", "2")
    set_input(driver, "duration-minutes", "30")
    click(driver, driver.find_element(By.ID, "build-rules"))
    wait(driver).until(
        lambda browser: len(browser.find_elements(By.CSS_SELECTOR, "#current-rules-fields .rule-card")) == 2
    )
    values = [(1, 4, 4), (2, 4, 4)]
    for card_index, (key_count, promotion, relegation) in enumerate(values, start=1):
        for selector, value in [
            (".rule-key-count", key_count),
            (".rule-promotion", promotion),
            (".rule-relegation", relegation),
        ]:
            field = driver.find_element(
                By.CSS_SELECTOR,
                f"#current-rules-fields .rule-card:nth-child({card_index}) {selector}",
            )
            field.clear()
            field.send_keys(str(value))
    driver.find_element(By.ID, "config-form").submit()
    wait_admin_state(
        driver,
        lambda state: state["config"]["division_count"] == 2
        and state["config"]["rules"]["1"]["key_count"] == 1
        and state["config"]["rules"]["2"]["key_count"] == 2,
    )


def player_name(group, index):
    return f"D{group['division']}{group['chave']}-Jogador-{index:02d}"


def image_path(tmp_path, identifier, width=400, height=400):
    path = tmp_path / f"{identifier}.jpg"
    if not path.exists():
        path.write_bytes(jpeg_data(identifier, width, height))
    return path.resolve()


def assert_saved_image(url, identifier, expected_size):
    raw = get_bytes(url)
    with Image.open(io.BytesIO(raw)) as image:
        assert image.size == expected_size
        actual = image.convert("RGB").getpixel((8, 8))
    expected = deterministic_color(identifier)
    assert all(abs(actual[index] - expected[index]) <= 18 for index in range(3))


def find_list_item(driver, container_id, text):
    xpath = (
        f'//*[@id="{container_id}"]'
        f'//*[contains(@class,"list-item")][.//strong[normalize-space()="{text}"]]'
    )
    return wait(driver).until(EC.presence_of_element_located((By.XPATH, xpath)))


def edit_player_through_ui(driver, player_id, name, phrase, photo_path):
    driver.get(f"{BASE_URL}/admin/jogador?id={quote(player_id)}")
    wait(driver).until(
        lambda browser: browser.find_element(By.ID, "edit-player-name").get_attribute("value") == name
    )
    set_input(driver, "edit-player-message", phrase)
    driver.find_element(By.ID, "player-photo-file").send_keys(str(photo_path))
    wait(driver).until(
        lambda browser: browser.find_element(By.ID, "player-photo-preview").get_attribute("src").startswith("data:image/")
    )
    driver.find_element(By.ID, "player-edit-form").submit()
    wait(driver).until(lambda browser: "/admin" in browser.current_url and "/jogador" not in browser.current_url)
    wait(driver).until(EC.visibility_of_element_located((By.ID, "admin-panel")))


def create_and_update_players_through_ui(driver, tmp_path):
    progress("Criando 48 jogadores e atualizando foto/frase duas vezes pela interface...")
    players_by_group = {}
    for group in GROUPS:
        key = (group["division"], group["chave"])
        players_by_group[key] = []
        for index in range(1, PLAYERS_PER_GROUP + 1):
            name = player_name(group, index)
            open_admin(driver)
            open_section(driver, "players")
            set_input(driver, "player-name", name)
            select_value(driver, "player-division", group["division"])
            select_value(driver, "player-chave", group["chave"])
            driver.find_element(By.ID, "player-form").submit()
            state = wait_admin_state(
                driver,
                lambda current: next((p for p in current["players"] if p["name"] == name), None),
            )
            created = next(player for player in state["players"] if player["name"] == name)
            player_id = created["player_id"]

            initial_id = f"initial-{name}"
            initial_phrase = f"Frase inicial {name}"
            edit_player_through_ui(
                driver,
                player_id,
                name,
                initial_phrase,
                image_path(tmp_path, initial_id),
            )
            first_state = wait_admin_state(
                driver,
                lambda current: any(player["player_id"] == player_id for player in current["players"]),
            )
            first_player = next(player for player in first_state["players"] if player["player_id"] == player_id)
            assert first_player["short_message"] == initial_phrase
            assert_saved_image(first_player["photo_url"], initial_id, (400, 400))
            initial_photo_url = first_player["photo_url"]

            updated_id = f"updated-{name}"
            updated_phrase = f"Frase atualizada {name}"
            edit_player_through_ui(
                driver,
                player_id,
                name,
                updated_phrase,
                image_path(tmp_path, updated_id),
            )
            updated_state = wait_admin_state(
                driver,
                lambda current: any(player["player_id"] == player_id for player in current["players"]),
            )
            updated = next(player for player in updated_state["players"] if player["player_id"] == player_id)
            assert updated["short_message"] == updated_phrase
            assert updated["photo_url"] != initial_photo_url
            assert_saved_image(updated["photo_url"], updated_id, (400, 400))
            with pytest.raises(HTTPError) as old_photo_error:
                get_bytes(initial_photo_url)
            assert old_photo_error.value.code == 404
            updated["expected_phrase"] = updated_phrase
            players_by_group[key].append(updated)
            progress(f"Jogador {len(sum(players_by_group.values(), []))}/48 concluido: {name}")
    return players_by_group


def create_sponsors_through_ui(driver, tmp_path):
    progress("Cadastrando um patrocinador para cada local pela interface...")
    sponsors = []
    for group in GROUPS:
        name = f"Patrocinador {group['place']}"
        open_admin(driver)
        open_section(driver, "sponsors")
        set_input(driver, "sponsor-name", name)
        driver.find_element(By.ID, "sponsor-form").submit()
        state = wait_admin_state(
            driver,
            lambda current: next((s for s in current["sponsors"] if s["name"] == name), None),
        )
        created = next(sponsor for sponsor in state["sponsors"] if sponsor["name"] == name)
        item = find_list_item(driver, "sponsors-list", name)
        click(driver, item.find_element(By.CSS_SELECTOR, 'a[href*="/admin/patrocinador"]'))
        wait(driver).until(
            lambda browser: browser.find_element(By.ID, "edit-sponsor-name").get_attribute("value") == name
        )

        square_id = f"square-{group['place']}"
        rect_id = f"rect-{group['place']}"
        driver.find_element(By.ID, "sponsor-square-file").send_keys(
            str(image_path(tmp_path, square_id, 400, 400))
        )
        driver.find_element(By.ID, "sponsor-rect-file").send_keys(
            str(image_path(tmp_path, rect_id, 1200, 400))
        )
        wait(driver).until(
            lambda browser: browser.find_element(By.ID, "sponsor-square-preview").get_attribute("src").startswith("data:image/")
            and browser.find_element(By.ID, "sponsor-rect-preview").get_attribute("src").startswith("data:image/")
        )
        driver.find_element(By.ID, "sponsor-edit-form").submit()
        wait(driver).until(lambda browser: "/admin" in browser.current_url and "/patrocinador" not in browser.current_url)
        wait(driver).until(EC.visibility_of_element_located((By.ID, "admin-panel")))
        updated = next(s for s in admin_state(driver)["sponsors"] if s["sponsor_id"] == created["sponsor_id"])
        assert_saved_image(updated["square_image_url"], square_id, (400, 400))
        assert_saved_image(updated["rect_image_url"], rect_id, (1200, 400))
        sponsors.append(updated)
    return sponsors


def set_round_form(driver, group, round_index, date_index=None):
    open_admin(driver)
    open_section(driver, "rounds")
    set_input(driver, "round-name", group["place"])
    select_value(driver, "round-division", group["division"])
    select_value(driver, "round-chave", group["chave"])
    date_value = date_index or round_index
    set_input(driver, "round-date", f"{date_value:02d}072026")
    set_input(driver, "round-start-time", "0900")


def create_auto_round_through_ui(driver, group, round_index, date_index=None, timeout=90):
    set_round_form(driver, group, round_index, date_index)
    before = admin_state(driver)
    before_round_ids = {item["round_id"] for item in before["rounds"]}
    click(driver, driver.find_element(By.ID, "add-round-auto"))
    try:
        state = wait_admin_state(
            driver,
            lambda current: len(current["rounds"]) > len(before_round_ids),
            seconds=timeout,
        )
    except TimeoutException:
        return None
    created_round = next(item for item in state["rounds"] if item["round_id"] not in before_round_ids)
    created_matches = [match for match in state["matches"] if match["round_id"] == created_round["round_id"]]
    return created_round, created_matches


def filter_admin_matches(driver, division, chave):
    open_admin(driver)
    open_section(driver, "matches")
    select_value(driver, "admin-filter-division", division)
    select_value(driver, "admin-filter-chave", chave)
    wait(driver).until(lambda browser: browser.find_elements(By.CSS_SELECTOR, "#admin-matches .result-form"))


def save_result_through_ui(driver, match_id, loser_balls):
    filter_admin_matches(
        driver,
        next(m["division"] for m in admin_state(driver)["matches"] if m["match_id"] == match_id),
        next(m["chave"] for m in admin_state(driver)["matches"] if m["match_id"] == match_id),
    )
    form = wait(driver).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, f'.result-form[data-match-id="{match_id}"]'))
    )
    winner = form.find_element(By.NAME, "winner_id")
    Select(winner).select_by_index(1)
    first_score = form.find_element(By.NAME, "balls_p1")
    second_score = form.find_element(By.NAME, "balls_p2")
    first_score.clear()
    first_score.send_keys("7")
    second_score.clear()
    second_score.send_keys(str(loser_balls))
    click(driver, form.find_element(By.CSS_SELECTOR, 'button[type="submit"]'))
    wait_admin_state(
        driver,
        lambda state: next(
            match for match in state["matches"] if match["match_id"] == match_id
        )["is_finished"],
    )


def unused_matching(player_ids, used_pairs, count):
    best = []

    def search(remaining, pairs):
        nonlocal best
        if len(pairs) > len(best):
            best = pairs[:]
        if len(pairs) == count:
            return True
        if len(remaining) < 2:
            return False
        first = remaining[0]
        for index, partner in enumerate(remaining[1:], start=1):
            pair_key = tuple(sorted((first, partner)))
            if pair_key in used_pairs:
                continue
            next_remaining = remaining[1:index] + remaining[index + 1 :]
            if search(next_remaining, pairs + [(first, partner)]):
                return True
        return search(remaining[1:], pairs)

    search(list(player_ids), [])
    assert len(best) == count
    return best


def create_manual_conflict_round_through_ui(driver, group, players):
    progress("Criando rodada manual com dois jogos ja finalizados...")
    state = admin_state(driver)
    first_round = next(
        item
        for item in state["rounds"]
        if item["division"] == 1 and item["chave"] == "A" and item["round_number"] == 1
    )
    first_matches = [match for match in state["matches"] if match["round_id"] == first_round["round_id"]]
    conflicts = [
        (first_matches[0]["player1_id"], first_matches[0]["player2_id"]),
        (first_matches[1]["player1_id"], first_matches[1]["player2_id"]),
    ]
    conflict_players = {player_id for pair in conflicts for player_id in pair}
    free_players = [player["player_id"] for player in players if player["player_id"] not in conflict_players]
    used_pairs = {
        tuple(sorted((match["player1_id"], match["player2_id"])))
        for match in state["matches"]
        if match["division"] == 1 and match["chave"] == "A"
    }
    valid_pairs = unused_matching(free_players, used_pairs, 6)
    pairs = conflicts + valid_pairs

    set_round_form(driver, group, 2)
    before_rounds = len(admin_state(driver)["rounds"])
    click(driver, driver.find_element(By.ID, "prepare-round-manual"))
    rows = wait(driver).until(
        lambda browser: browser.find_elements(By.CSS_SELECTOR, "#manual-round-editor .manual-game-row")
        if len(browser.find_elements(By.CSS_SELECTOR, "#manual-round-editor .manual-game-row")) == 8
        else False
    )
    for row, (left_id, right_id) in zip(rows, pairs):
        Select(row.find_element(By.CSS_SELECTOR, ".manual-left")).select_by_value(left_id)
        Select(row.find_element(By.CSS_SELECTOR, ".manual-right")).select_by_value(right_id)
    click(driver, driver.find_element(By.ID, "save-manual-round"))
    alert = wait(driver).until(EC.alert_is_present())
    alert_text = alert.text
    assert "ja aconteceram" in alert_text.lower() or "já aconteceram" in alert_text.lower()
    alert.accept()
    updated = wait_admin_state(driver, lambda current: len(current["rounds"]) == before_rounds + 1)
    manual_round = max(
        (item for item in updated["rounds"] if item["division"] == 1 and item["chave"] == "A"),
        key=lambda item: item["round_number"],
    )
    matches = [match for match in updated["matches"] if match["round_id"] == manual_round["round_id"]]
    assert manual_round["mode"] == "manual"
    assert len(matches) == 6


def create_rounds_through_ui(driver, players_by_group):
    progress("Criando cinco rodadas por chave pelos botoes do painel...")
    first_group = GROUPS[0]
    first_round = create_auto_round_through_ui(driver, first_group, 1)
    assert first_round and len(first_round[1]) == 8
    save_result_through_ui(driver, first_round[1][0]["match_id"], 2)
    save_result_through_ui(driver, first_round[1][1]["match_id"], 3)
    create_manual_conflict_round_through_ui(driver, first_group, players_by_group[(1, "A")])
    for round_index in range(3, MAIN_ROUNDS_PER_GROUP + 1):
        created = create_auto_round_through_ui(driver, first_group, round_index)
        assert created and len(created[1]) == 8

    for group in GROUPS[1:]:
        for round_index in range(1, MAIN_ROUNDS_PER_GROUP + 1):
            created = create_auto_round_through_ui(driver, group, round_index)
            assert created and len(created[1]) == 8

    state = admin_state(driver)
    for group in GROUPS:
        rounds = [
            item
            for item in state["rounds"]
            if item["division"] == group["division"] and item["chave"] == group["chave"]
        ]
        assert len(rounds) == MAIN_ROUNDS_PER_GROUP
        assert {item["place_name"] for item in rounds} == {group["place"]}


def exhaust_until_partial_round_through_ui(driver):
    progress("Criando rodadas pela interface ate aparecer uma rodada automatica parcial...")
    group = GROUPS[0]
    partial = None
    date_index = 6
    while date_index <= 31:
        created = create_auto_round_through_ui(
            driver,
            group,
            round_index=date_index,
            date_index=date_index,
            timeout=45,
        )
        if created is None:
            break
        _, matches = created
        if len(matches) < 8:
            partial = created
        date_index += 1
    assert partial is not None
    assert 1 <= len(partial[1]) < 8


def save_mid_tournament_results_through_ui(driver):
    progress("Cadastrando resultados em todas as chaves pela interface...")
    expected = defaultdict(lambda: {"played": 0, "wins": 0, "points": 0, "for": 0, "against": 0})
    state = admin_state(driver)
    already_finished = [match for match in state["matches"] if match["is_finished"]]
    selected = list(already_finished)
    for group in GROUPS:
        pending = [
            match
            for match in state["matches"]
            if match["division"] == group["division"]
            and match["chave"] == group["chave"]
            and not match["is_finished"]
        ]
        needed = 4 if group != GROUPS[0] else 2
        for index, match in enumerate(pending[:needed]):
            save_result_through_ui(driver, match["match_id"], index + 1)
            selected.append(next(m for m in admin_state(driver)["matches"] if m["match_id"] == match["match_id"]))

    for match in selected:
        first = expected[match["player1_id"]]
        second = expected[match["player2_id"]]
        first["played"] += 1
        second["played"] += 1
        first["for"] += match["balls_p1"]
        first["against"] += match["balls_p2"]
        second["for"] += match["balls_p2"]
        second["against"] += match["balls_p1"]
        winner = first if match["winner_id"] == match["player1_id"] else second
        winner["wins"] += 1
        winner["points"] += 3
    final_state = admin_state(driver)
    latest = max(
        (match for match in final_state["matches"] if match["is_finished"]),
        key=lambda match: match.get("result_saved_at") or "",
    )
    return expected, latest, final_state


def validate_standings(state, expected):
    rows = {}
    for division in state["standings"].values():
        for group_rows in division.values():
            for row in group_rows:
                rows[row["player_id"]] = row
    for player_id, totals in expected.items():
        row = rows[player_id]
        assert row["played"] == totals["played"]
        assert row["wins"] == totals["wins"]
        assert row["points"] == totals["points"]
        assert row["balls_for"] == totals["for"]
        assert row["balls_against"] == totals["against"]
        assert row["balls_balance"] == totals["for"] - totals["against"]


def wait_for_download(directory, suffix, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        files = [path for path in Path(directory).glob(f"*{suffix}") if not path.name.endswith(".crdownload")]
        if files:
            return max(files, key=lambda path: path.stat().st_mtime)
        time.sleep(0.25)
    raise AssertionError(f"Download {suffix} nao foi criado.")


def validate_public_filters_share_and_pdf(driver, state):
    progress("Validando placar, filtros, imagem de compartilhar e PDF...")
    driver.get(f"{BASE_URL}/")
    wait(driver).until(EC.text_to_be_present_in_element((By.ID, "standings"), "D1A-Jogador-01"))
    assert len(driver.find_elements(By.CSS_SELECTOR, ".standings-card")) == 2
    assert len(driver.find_elements(By.CSS_SELECTOR, ".chave-block")) == 3
    assert "Selecione ao menos um filtro" in driver.find_element(By.ID, "matches").text
    assert not driver.find_elements(By.CSS_SELECTOR, "#matches .match-row")

    sala_azul_id = next(place["place_id"] for place in state["places"] if place["name"] == "Sala Azul")
    select_value(driver, "filter-place", sala_azul_id)
    select_value(driver, "filter-division", 2)
    select_value(driver, "filter-chave", "A")
    select_value(driver, "filter-status", "finished")
    expected_matches = [
        match
        for match in state["matches"]
        if match["place_name"] == "Sala Azul"
        and match["division"] == 2
        and match["chave"] == "A"
        and match["is_finished"]
    ]
    wait(driver).until(
        lambda browser: browser.find_element(By.ID, "matches-count").text == f"{len(expected_matches)} partidas"
    )
    assert len(driver.find_elements(By.CSS_SELECTOR, "#matches .match-row")) == len(expected_matches)

    driver.execute_script(
        "Object.defineProperty(navigator, 'canShare', {value: () => false, configurable: true});"
    )
    share_button = driver.find_element(By.CSS_SELECTOR, '[data-share-division="1"]')
    click(driver, share_button)
    png_path = wait_for_download(driver.download_dir, ".png")
    with Image.open(png_path) as image:
        assert image.size == (1080, 1920)
        assert image.format == "PNG"

    driver.execute_script(
        """
        window.__printedHtml = '';
        window.open = () => ({
          document: {
            open() {},
            write(html) { window.__printedHtml = html; },
            close() {}
          }
        });
        """
    )
    click(driver, driver.find_element(By.ID, "print-filtered-matches"))
    printed_html = wait(driver).until(lambda browser: browser.execute_script("return window.__printedHtml"))
    assert "Sala Azul" in printed_html

    printable_html = re.sub(r"<script>.*?</script>", "", printed_html, flags=re.DOTALL)
    driver.switch_to.new_window("tab")
    driver.get("data:text/html;charset=utf-8," + quote(printable_html))
    pdf_result = driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
    pdf_bytes = base64.b64decode(pdf_result["data"])
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 10_000
    (Path(driver.download_dir) / "jogos-filtrados.pdf").write_bytes(pdf_bytes)
    driver.close()
    driver.switch_to.window(driver.window_handles[0])


def validate_player_profile(driver, player, state):
    progress("Validando perfil publico, jogos e proxima partida...")
    matches = [
        match
        for match in state["matches"]
        if match["player1_id"] == player["player_id"] or match["player2_id"] == player["player_id"]
    ]
    assert any(not match["is_finished"] for match in matches)
    driver.get(f"{BASE_URL}{player['profile_url']}")
    wait(driver).until(EC.text_to_be_present_in_element((By.ID, "profile-root"), player["name"]))
    root = driver.find_element(By.ID, "profile-root")
    assert player["expected_phrase"] in root.text
    assert "Próximo jogo" in root.text
    assert len(driver.find_elements(By.CSS_SELECTOR, "#profile-root .match-row")) == len(matches)
    assert driver.find_element(By.CSS_SELECTOR, ".profile-photo").get_attribute("src").endswith(player["photo_url"])
    profile_html = get_bytes(player["profile_url"]).decode("utf-8")
    expected_title = f"Perfil de {player['name']} do 2° Campeonato de Sinuca de Entre Folhas"
    assert f'<meta property="og:title" content="{expected_title}">' in profile_html
    assert f'{player["photo_url"]}"' in profile_html


def configure_telao_through_ui(driver):
    progress("Configurando tempos e filtro do telao pelo painel...")
    open_admin(driver)
    open_section(driver, "tv-config")
    set_input(driver, "tv-table-seconds", "8")
    set_input(driver, "tv-sponsor-seconds", "4")
    set_input(driver, "tv-match-seconds", "2")
    select_value(driver, "tv-filter-status", "finished")
    driver.find_element(By.ID, "tv-config-form").submit()
    return wait_admin_state(
        driver,
        lambda current: current["config"]["tv_config"]["table_seconds"] == 8
        and current["config"]["tv_config"]["sponsor_seconds"] == 4
        and current["config"]["tv_config"]["match_seconds"] == 2
        and current["config"]["tv_config"]["filters"]["status"] == "finished"
        and len(current["tv_matches"]) >= 2,
    )


def current_sponsor_shape(driver):
    classes = driver.find_element(By.ID, "telao-grid").get_attribute("class").split()
    if "rect-sponsors" in classes:
        return "rect"
    if "square-sponsors" in classes:
        return "square"
    return False


def validate_telao(driver, sponsors, matches, tv_config):
    table_seconds = tv_config["table_seconds"]
    sponsor_seconds = tv_config["sponsor_seconds"]
    match_seconds = tv_config["match_seconds"]
    progress(
        "Validando ciclo configurado do telao, radio, zoom, contagem regressiva e layout wide..."
    )
    assert len(matches) >= 2
    assert matches == sorted(
        matches,
        key=lambda item: (
            item.get("date") or "9999-99-99",
            item.get("time") or "99:99",
            item.get("place_name") or "",
            item.get("round_number", 999),
            item.get("match_id") or "",
        ),
    )

    driver.set_window_size(1920, 1080)
    driver.get(f"{BASE_URL}/telao")
    wait(driver).until(EC.text_to_be_present_in_element((By.ID, "telao-grid"), "D1A-Jogador"))
    wait(driver).until(lambda browser: len(browser.find_elements(By.CSS_SELECTOR, ".telao-card")) == 3)
    tables_started_at = time.monotonic()

    countdown_text = driver.find_element(By.ID, "telao-countdown").text
    assert countdown_text.startswith("Placar")
    first_countdown = int(re.search(r"(\d+)s", countdown_text).group(1))
    time.sleep(min(1.1, table_seconds / 2))
    second_countdown = int(re.search(r"(\d+)s", driver.find_element(By.ID, "telao-countdown").text).group(1))
    assert second_countdown < first_countdown

    click(driver, driver.find_element(By.ID, "telao-radio-menu-button"))
    wait(driver).until(EC.visibility_of_element_located((By.ID, "telao-radio-menu")))
    assert len(driver.find_elements(By.CSS_SELECTOR, "#telao-radio-menu [data-radio-id]")) == 3
    driver.execute_script(
        """
        const audio = document.getElementById('telao-radio-audio');
        audio.play = () => {
          Object.defineProperty(audio, 'paused', {value: false, configurable: true});
          audio.dispatchEvent(new Event('play'));
          return Promise.resolve();
        };
        audio.pause = () => {
          Object.defineProperty(audio, 'paused', {value: true, configurable: true});
          audio.dispatchEvent(new Event('pause'));
        };
        """
    )
    click(driver, driver.find_element(By.CSS_SELECTOR, '[data-radio-id="secret-agent"]'))
    assert "secretagent-128-mp3" in driver.find_element(By.ID, "telao-radio-audio").get_attribute("src")
    assert driver.find_element(By.ID, "telao-radio-toggle").get_attribute("title") == "Desligar rádio"
    click(driver, driver.find_element(By.ID, "telao-radio-toggle"))
    assert driver.find_element(By.ID, "telao-radio-toggle").get_attribute("title") == "Ligar rádio"

    initial_zoom = float(driver.execute_script("return Number(document.documentElement.style.zoom || 1)"))
    click(driver, driver.find_element(By.ID, "telao-zoom-in"))
    wait(driver).until(
        lambda browser: float(browser.execute_script("return Number(document.documentElement.style.zoom || 1)")) > initial_zoom
    )
    click(driver, driver.find_element(By.ID, "telao-zoom-out"))

    layout = driver.execute_script(
        """
        return {
          pageOverflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
          pageOverflowY: document.documentElement.scrollHeight > window.innerHeight + 1,
          cards: [...document.querySelectorAll('.telao-card')].map(card => {
            const rect = card.getBoundingClientRect();
            const table = card.querySelector('.telao-table-wrap');
            return {
              left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom,
              tableOverflowX: table.scrollWidth > table.clientWidth + 1,
              tableOverflowY: table.scrollHeight > table.clientHeight + 1
            };
          })
        };
        """
    )
    assert not layout["pageOverflowX"]
    assert not layout["pageOverflowY"]
    assert all(card["left"] >= 0 and card["right"] <= 1920 for card in layout["cards"])
    assert all(card["top"] >= 0 and card["bottom"] <= 1080 for card in layout["cards"])
    assert all(not card["tableOverflowX"] and not card["tableOverflowY"] for card in layout["cards"])

    first_sponsor_shape = wait(driver, table_seconds + 8).until(current_sponsor_shape)
    first_sponsor_elapsed = time.monotonic() - tables_started_at
    assert max(0, table_seconds - 2) <= first_sponsor_elapsed <= table_seconds + 8
    assert first_sponsor_shape == "rect"
    assert driver.find_element(By.ID, "telao-countdown").text.startswith("Patrocinadores")
    assert len(driver.find_elements(By.CSS_SELECTOR, ".sponsor-tv-card")) == len(sponsors)
    assert all(sponsor["name"] in driver.find_element(By.ID, "telao-grid").text for sponsor in sponsors)
    assert all(
        "/rect-" in image.get_attribute("src")
        for image in driver.find_elements(By.CSS_SELECTOR, ".sponsor-tv-card img")
    )

    sponsors_started_at = time.monotonic()
    wait(driver, sponsor_seconds + 8).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".latest-result-card")))
    sponsor_elapsed = time.monotonic() - sponsors_started_at
    assert max(0, sponsor_seconds - 2) <= sponsor_elapsed <= sponsor_seconds + 8
    first_result_text = driver.find_element(By.CSS_SELECTOR, ".latest-result-card").text
    assert driver.find_element(By.ID, "telao-countdown").text.startswith("Confrontos 1 de ")
    assert matches[0]["place_name"].lower() in first_result_text.lower()
    assert matches[0]["player1_name"] in first_result_text
    assert matches[0]["player2_name"] in first_result_text
    visual_proportions = driver.execute_script(
        """
        const card = document.querySelector('.latest-result-card');
        const images = [...card.querySelectorAll('.result-player img')];
        const names = [...card.querySelectorAll('.result-player h2')];
        const scores = [...card.querySelectorAll('.player-score')];
        const versus = card.querySelector('.big-versus');
        const center = card.querySelector('.result-center');
        const versusRect = versus.getBoundingClientRect();
        const centerRect = center.getBoundingClientRect();
        const versusSize = parseFloat(getComputedStyle(versus).fontSize);
        const scoreSize = parseFloat(getComputedStyle(scores[0]).fontSize);
        return {
          images: images.map((image, index) => {
            const imageRect = image.getBoundingClientRect();
            const nameRect = names[index].getBoundingClientRect();
            return {
              width: imageRect.width,
              height: imageRect.height,
              nameBelowPhoto: nameRect.top >= imageRect.bottom - 1
            };
          }),
          scoreSize,
          versusSize,
          leftScoreRight: scores[0].getBoundingClientRect().right,
          versusLeft: versusRect.left,
          versusRight: versusRect.right,
          rightScoreLeft: scores[1].getBoundingClientRect().left,
          center: {left: centerRect.left, right: centerRect.right},
          leftPhotoRight: images[0].getBoundingClientRect().right,
          rightPhotoLeft: images[1].getBoundingClientRect().left
        };
        """
    )
    assert all(abs(image["width"] - image["height"]) <= 2 for image in visual_proportions["images"])
    assert all(image["nameBelowPhoto"] for image in visual_proportions["images"])
    assert all(image["width"] > visual_proportions["versusSize"] * 3 for image in visual_proportions["images"])
    assert 1.15 <= visual_proportions["scoreSize"] / visual_proportions["versusSize"] <= 1.25
    assert visual_proportions["leftScoreRight"] <= visual_proportions["versusLeft"] + 1
    assert visual_proportions["rightScoreLeft"] >= visual_proportions["versusRight"] - 1
    assert visual_proportions["leftPhotoRight"] <= visual_proportions["center"]["left"] + 1
    assert visual_proportions["rightPhotoLeft"] >= visual_proportions["center"]["right"] - 1

    driver.set_window_size(1366, 480)
    wait(driver).until(lambda browser: browser.execute_script("return window.innerHeight") <= 480)
    responsive = driver.execute_script(
        """
        const card = document.querySelector('.latest-result-card').getBoundingClientRect();
        const center = document.querySelector('.result-center').getBoundingClientRect();
        const photos = [...document.querySelectorAll('.result-player img')].map(image => {
          const rect = image.getBoundingClientRect();
          return {left: rect.left, right: rect.right};
        });
        const elements = [...document.querySelectorAll(
          '.result-player img, .result-player h2, .result-player p, .player-score, .result-center'
        )].map(element => {
          const rect = element.getBoundingClientRect();
          return {left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom};
        });
        return {
          viewport: {width: window.innerWidth, height: window.innerHeight},
          pageOverflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
          pageOverflowY: document.documentElement.scrollHeight > window.innerHeight + 1,
          card: {left: card.left, top: card.top, right: card.right, bottom: card.bottom},
          center: {left: center.left, right: center.right},
          photos,
          elements
        };
        """
    )
    assert not responsive["pageOverflowX"]
    assert not responsive["pageOverflowY"]
    assert responsive["card"]["bottom"] <= responsive["viewport"]["height"] + 1
    assert responsive["photos"][0]["right"] <= responsive["center"]["left"] + 1
    assert responsive["photos"][1]["left"] >= responsive["center"]["right"] - 1
    assert all(
        item["left"] >= responsive["card"]["left"] - 1
        and item["right"] <= responsive["card"]["right"] + 1
        and item["top"] >= responsive["card"]["top"] - 1
        and item["bottom"] <= responsive["card"]["bottom"] + 1
        for item in responsive["elements"]
    )

    wait(driver, match_seconds + 8).until(
        lambda browser: browser.execute_script(
            "return currentMode === 'matches' && currentMatchIndex >= 1;"
        )
    )
    second_result_text = driver.find_element(By.CSS_SELECTOR, ".latest-result-card").text
    assert driver.find_element(By.ID, "telao-countdown").text.startswith("Confrontos 2 de ")
    assert matches[1]["player1_name"] in second_result_text
    assert matches[1]["player2_name"] in second_result_text

    driver.set_window_size(1920, 1080)
    wait(driver, len(matches) * match_seconds + 10).until(
        lambda browser: len(browser.find_elements(By.CSS_SELECTOR, ".telao-card")) == 3
    )
    second_tables_started_at = time.monotonic()
    second_sponsor_shape = wait(driver, table_seconds + 8).until(current_sponsor_shape)
    second_sponsor_elapsed = time.monotonic() - second_tables_started_at
    assert max(0, table_seconds - 2) <= second_sponsor_elapsed <= table_seconds + 8
    assert second_sponsor_shape == "square"
    assert all(
        "/square-" in image.get_attribute("src")
        for image in driver.find_elements(By.CSS_SELECTOR, ".sponsor-tv-card img")
    )

    pending = driver.execute_script(
        """
        const match = (telaoState.matches || []).find(item => !item.is_finished);
        if (!match) return null;
        renderMatch(match);
        return match;
        """
    )
    assert pending is not None
    assert driver.find_element(By.CSS_SELECTOR, ".result-pending-label").text.lower() == "pendente"
    assert pending["place_name"].lower() in driver.find_element(By.CSS_SELECTOR, ".result-kicker").text.lower()

    driver.execute_script(
        """
        const match = {
          ...telaoState.tv_matches[0],
          is_finished: true,
          double_loss: true,
          winner_id: '',
          balls_p1: 0,
          balls_p2: 0
        };
        renderMatch(match);
        """
    )
    assert driver.find_element(By.CSS_SELECTOR, ".result-double-loss-label").text.lower() == "derrota para ambos"
    assert [item.text for item in driver.find_elements(By.CSS_SELECTOR, ".result-scoreline .player-score")] == ["0", "0"]


@pytest.mark.full
def test_complete_tournament_entirely_through_ui(driver, tmp_path):
    open_admin(driver)
    clear_database_through_ui(driver)
    configure_tournament_through_ui(driver)
    players_by_group = create_and_update_players_through_ui(driver, tmp_path)
    sponsors = create_sponsors_through_ui(driver, tmp_path)
    create_rounds_through_ui(driver, players_by_group)
    exhaust_until_partial_round_through_ui(driver)
    expected, _latest_result, state = save_mid_tournament_results_through_ui(driver)
    state = configure_telao_through_ui(driver)
    validate_standings(state, expected)

    public_players = {player["player_id"]: player for player in state["players"]}
    configured_player = players_by_group[(2, "A")][0]
    profile_player = public_players[configured_player["player_id"]]
    profile_player["expected_phrase"] = configured_player["expected_phrase"]

    validate_public_filters_share_and_pdf(driver, state)
    validate_player_profile(driver, profile_player, state)
    validate_telao(driver, sponsors, state["tv_matches"], state["config"]["tv_config"])
