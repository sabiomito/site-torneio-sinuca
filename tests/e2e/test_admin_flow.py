import os
import re
from urllib.parse import quote

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait


BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")


def wait(driver):
    return WebDriverWait(driver, 240)


def open_admin_and_login(driver):
    driver.get(f"{BASE_URL}/admin")
    wait(driver).until(EC.visibility_of_element_located((By.ID, "admin-password"))).send_keys(ADMIN_PASSWORD)
    driver.find_element(By.ID, "login-form").submit()
    wait(driver).until(EC.visibility_of_element_located((By.ID, "admin-panel")))


def clear_local_database(driver):
    script = """
    const done = arguments[0];
    const token = localStorage.getItem('sinuca_admin_token');
    fetch('/api/admin/clear-database?token=' + encodeURIComponent(token), {
      method: 'POST',
      body: JSON.stringify({confirm_text: 'LIMPAR'})
    }).then(r => r.json().then(data => done({ok: r.ok, data})))
      .catch(err => done({ok: false, data: {error: String(err)}}));
    """
    result = driver.execute_async_script(script)
    assert result["ok"], result["data"]
    driver.get(f"{BASE_URL}/admin")
    wait(driver).until(EC.visibility_of_element_located((By.ID, "admin-panel")))


def open_section(driver, name):
    section = driver.find_element(By.CSS_SELECTOR, f'[data-section="{name}"]')
    if "closed" in section.get_attribute("class").split():
        section.find_element(By.CSS_SELECTOR, ".collapse-title").click()
    return section


def set_input(driver, element_id, value):
    field = wait(driver).until(EC.presence_of_element_located((By.ID, element_id)))
    field.clear()
    field.send_keys(value)


def admin_state(driver):
    script = """
    const done = arguments[0];
    const token = localStorage.getItem('sinuca_admin_token');
    fetch('/api/admin/state?token=' + encodeURIComponent(token))
      .then(r => r.json().then(data => done({ok: r.ok, data})))
      .catch(err => done({ok: false, data: {error: String(err)}}));
    """
    result = driver.execute_async_script(script)
    return result["data"] if result["ok"] else None


def assert_visible_box(driver, element, *, min_width=1, min_height=1):
    assert element.is_displayed()
    rect = element.rect
    assert rect["width"] >= min_width
    assert rect["height"] >= min_height
    style = driver.execute_script(
        """
        const style = getComputedStyle(arguments[0]);
        return {
          display: style.display,
          visibility: style.visibility,
          opacity: style.opacity,
        };
        """,
        element,
    )
    assert style["display"] != "none"
    assert style["visibility"] == "visible"
    assert float(style["opacity"] or 1) > 0


def test_admin_flow_creates_round_and_public_score(driver):
    open_admin_and_login(driver)
    clear_local_database(driver)

    open_section(driver, "config")
    set_input(driver, "division-count", "1")
    set_input(driver, "duration-minutes", "30")
    driver.find_element(By.ID, "build-rules").click()
    driver.find_element(By.CSS_SELECTOR, ".rule-promotion").clear()
    driver.find_element(By.CSS_SELECTOR, ".rule-promotion").send_keys("1")
    driver.find_element(By.ID, "config-form").submit()
    wait(driver).until(
        lambda browser: (
            (state := admin_state(browser))
            and state["config"]["division_count"] == 1
            and state["config"]["duration_minutes"] == 30
            and state["config"]["rules"]["1"]["promotion_count"] == 1
        )
    )

    open_section(driver, "players")
    for name in ["Teste Alpha", "Teste Beta"]:
        set_input(driver, "player-name", name)
        Select(driver.find_element(By.ID, "player-division")).select_by_value("1")
        Select(driver.find_element(By.ID, "player-chave")).select_by_value("A")
        driver.find_element(By.ID, "player-form").submit()
        wait(driver).until(EC.text_to_be_present_in_element((By.ID, "players-list"), name))

    open_section(driver, "rounds")
    set_input(driver, "round-name", "Mesa local")
    set_input(driver, "round-date", "08062026")
    set_input(driver, "round-start-time", "09:00")
    driver.find_element(By.ID, "add-round-auto").click()
    wait(driver).until(EC.text_to_be_present_in_element((By.ID, "rounds-list"), "Mesa local"))

    open_section(driver, "matches")
    form = wait(driver).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".result-form")))
    match_id = form.get_attribute("data-match-id")
    Select(form.find_element(By.NAME, "winner_id")).select_by_value("__double_loss__")
    assert form.find_element(By.NAME, "balls_p1").get_attribute("disabled")
    assert form.find_element(By.NAME, "balls_p2").get_attribute("disabled")
    form.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
    finished_state = wait(driver).until(
        lambda browser: (
            (state := admin_state(browser))
            and next(
                (
                    match
                    for match in state["matches"]
                    if match["match_id"] == match_id
                    and match.get("is_finished")
                    and match.get("double_loss")
                    and match.get("balls_p1") == 0
                    and match.get("balls_p2") == 0
                ),
                None,
            )
            and state
        )
    )
    rows = {
        row["player_id"]: row
        for division in finished_state["standings"].values()
        for chave in division.values()
        for row in chave
    }
    assert all(
        rows[player["player_id"]]["played"] == 1
        and rows[player["player_id"]]["losses"] == 1
        and rows[player["player_id"]]["points"] == 0
        and rows[player["player_id"]]["balls_balance"] == 0
        for player in finished_state["players"]
    )

    Select(driver.find_element(By.ID, "admin-filter-status")).select_by_value("finished")
    wait(driver).until(lambda browser: len(browser.find_elements(By.CSS_SELECTOR, "#admin-matches .result-form")) == 1)
    finished_form = driver.find_element(By.CSS_SELECTOR, "#admin-matches .result-form")
    assert Select(finished_form.find_element(By.NAME, "winner_id")).first_selected_option.get_attribute("value") == "__double_loss__"
    assert "derrota para ambos" in finished_form.text.lower()
    Select(driver.find_element(By.ID, "admin-filter-status")).select_by_value("pending")
    wait(driver).until(lambda browser: len(browser.find_elements(By.CSS_SELECTOR, "#admin-matches .result-form")) == 0)

    driver.get(f"{BASE_URL}/")
    wait(driver).until(EC.text_to_be_present_in_element((By.ID, "standings"), "Teste Alpha"))
    assert "Selecione ao menos um filtro" in driver.find_element(By.ID, "matches").text
    assert not driver.find_elements(By.CSS_SELECTOR, "#matches .match-row")
    Select(driver.find_element(By.ID, "filter-status")).select_by_value("finished")
    wait(driver).until(lambda browser: len(browser.find_elements(By.CSS_SELECTOR, "#matches .match-row")) == 1)
    assert "0 x 0" in driver.find_element(By.ID, "matches").text
    assert "Derrota para ambos" in driver.find_element(By.ID, "matches").text
    public_html = driver.page_source
    assert 'class="match-row finished"' in public_html
    assert "Teste Alpha" in public_html
    assert "Teste Beta" in public_html
    assert re.search(r">\s*0</span>\s*x\s*<span[^>]*>\s*0\s*<", public_html)
    assert "Derrota para ambos" in public_html
    match_row = driver.find_element(By.CSS_SELECTOR, "#matches .match-row.finished")
    assert_visible_box(driver, match_row, min_width=250, min_height=30)
    assert_visible_box(driver, match_row.find_element(By.CSS_SELECTOR, ".pill"), min_width=40, min_height=12)
    assert_visible_box(driver, match_row.find_element(By.CSS_SELECTOR, ".score"), min_width=40, min_height=12)
    assert_visible_box(driver, match_row.find_element(By.CSS_SELECTOR, ".double-loss-note"), min_width=40, min_height=12)

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
    driver.find_element(By.ID, "print-filtered-matches").click()
    printed_html = wait(driver).until(lambda browser: browser.execute_script("return window.__printedHtml"))
    assert "<table>" in printed_html
    assert "Teste Alpha" in printed_html
    assert "Teste Beta" in printed_html
    assert "09:00" in printed_html
    assert "0 x 0 (derrota para ambos)" in printed_html

    printable_html = re.sub(r"<script>.*?</script>", "", printed_html, flags=re.DOTALL)
    original_window = driver.current_window_handle
    driver.switch_to.new_window("tab")
    try:
        driver.get("data:text/html;charset=utf-8," + quote(printable_html))
        print_page = wait(driver).until(EC.visibility_of_element_located((By.CSS_SELECTOR, ".print-page")))
        print_table = driver.find_element(By.CSS_SELECTOR, ".print-page table")
        result_cell = driver.find_element(By.CSS_SELECTOR, ".print-page .col-result")
        assert_visible_box(driver, print_page, min_width=300, min_height=400)
        assert_visible_box(driver, print_table, min_width=300, min_height=60)
        assert_visible_box(driver, result_cell, min_width=20, min_height=10)
        assert "0 x 0 (derrota para ambos)" in driver.find_element(By.TAG_NAME, "body").text
    finally:
        driver.close()
        driver.switch_to.window(original_window)

    standings_text = driver.find_element(By.ID, "standings").text
    assert "Teste Beta" in standings_text

    player = next(item for item in finished_state["players"] if item["name"] == "Teste Alpha")
    driver.get(f"{BASE_URL}{player['profile_url']}")
    wait(driver).until(EC.text_to_be_present_in_element((By.ID, "profile-root"), "Teste Alpha"))
    assert "Derrota · 0 x 0" in driver.find_element(By.ID, "profile-root").text

    driver.get(f"{BASE_URL}/player?id={player['player_id']}")
    wait(driver).until(EC.text_to_be_present_in_element((By.ID, "player-matches"), "Teste Beta"))
    assert "0 x 0" in driver.find_element(By.ID, "player-matches").text
    assert "Derrota para ambos" in driver.find_element(By.ID, "player-matches").text

    driver.get(f"{BASE_URL}/telao")
    wait(driver).until(EC.element_to_be_clickable((By.ID, "telao-radio-menu-button"))).click()
    wait(driver).until(EC.visibility_of_element_located((By.ID, "telao-radio-menu")))
    assert len(driver.find_elements(By.CSS_SELECTOR, "#telao-radio-menu [data-radio-id]")) == 14
    radio_menu_text = driver.find_element(By.ID, "telao-radio-menu").text.lower()
    assert "sertanejo clássico" in radio_menu_text
    assert "forró" in radio_menu_text
    assert "românticas e flashback" in radio_menu_text
    driver.execute_script(
        """
        const audio = document.getElementById('telao-radio-audio');
        audio.play = () => {
          Object.defineProperty(audio, 'paused', {value: false, configurable: true});
          audio.dispatchEvent(new Event('play'));
          return Promise.resolve();
        };
        """
    )
    driver.find_element(By.CSS_SELECTOR, '[data-radio-id="so-forro-antigas"]').click()
    assert "7132/stremig" in driver.find_element(By.ID, "telao-radio-audio").get_attribute("src")
    assert (
        driver.find_element(By.ID, "telao-radio-menu-button").get_attribute("title")
        == "Selecionar rádio · Só Forró das Antigas"
    )
