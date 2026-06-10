import os

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
    Select(form.find_element(By.NAME, "winner_id")).select_by_index(1)
    form.find_element(By.CSS_SELECTOR, 'button[type="submit"]').click()
    wait(driver).until(
        lambda browser: (
            (state := admin_state(browser))
            and any(
                match["match_id"] == match_id and match.get("is_finished")
                for match in state["matches"]
            )
        )
    )

    driver.get(f"{BASE_URL}/")
    wait(driver).until(EC.text_to_be_present_in_element((By.ID, "standings"), "Teste Alpha"))
    standings_text = driver.find_element(By.ID, "standings").text
    assert "Teste Beta" in standings_text
    assert "3" in standings_text
