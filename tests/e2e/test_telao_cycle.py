import json
from urllib.parse import urlencode
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from support import ADMIN_PASSWORD, BASE_URL


def post_json(path, payload, token=None):
    query = f"?{urlencode({'token': token})}" if token else ""
    request = Request(
        f"{BASE_URL}/api{path}{query}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise AssertionError(f"{path} returned HTTP {exc.code}: {body}") from exc


def seed_telao_cycle_data(tv_config_overrides=None):
    token = post_json("/admin/login", {"password": ADMIN_PASSWORD})["token"]
    post_json("/admin/clear-database", {"confirm_text": "LIMPAR"}, token)
    post_json(
        "/admin/config",
        {
            "division_count": 2,
            "duration_minutes": 30,
            "show_bracket_scoreboard": True,
            "show_bracket_tv": True,
            "rules": {
                "1": {"key_count": 2, "promotion_count": 2, "relegation_count": 0},
                "2": {"key_count": 1, "promotion_count": 2, "relegation_count": 0},
            },
        },
        token,
    )
    tv_config = {
        "table_seconds": 2,
        "bracket_seconds": 2,
        "sponsor_seconds": 2,
        "match_seconds": 2,
        "bracket_game_filter": "all",
        "filters": {"status": "finished"},
    }
    tv_config.update(tv_config_overrides or {})
    post_json(
        "/admin/tv-config",
        tv_config,
        token,
    )
    for division, chave, count in [(1, "A", 4), (1, "B", 2), (2, "A", 2)]:
        for index in range(1, count + 1):
            post_json(
                "/admin/player",
                {
                    "name": f"D{division}{chave}-Jogador-{index:02d}",
                    "division": division,
                    "chave": chave,
                    "short_message": "Fixture do ciclo do telao",
                },
                token,
            )
    round_data = post_json(
        "/admin/round-auto",
        {
            "name": "Mesa Telao",
            "division": 1,
            "chave": "A",
            "date": "2026-06-20",
            "start_time": "09:00",
        },
        token,
    )
    for index, match in enumerate(round_data["matches"]):
        winner_id = match["player1_id"] if index % 2 == 0 else match["player2_id"]
        post_json(
            "/admin/result",
            {
                "match_id": match["match_id"],
                "winner_id": winner_id,
                "balls_p1": 7 if winner_id == match["player1_id"] else 3,
                "balls_p2": 7 if winner_id == match["player2_id"] else 3,
            },
            token,
        )


def wait(driver, timeout=30):
    return WebDriverWait(driver, timeout)


@pytest.mark.telao_cycle
def test_real_telao_cycle_with_seeded_data(driver):
    seed_telao_cycle_data()
    driver.set_window_size(1920, 1080)
    driver.get(f"{BASE_URL}/telao")
    state = wait(driver).until(
        lambda browser: browser.execute_script(
            """
            return typeof telaoState !== 'undefined'
              && telaoState
              && telaoState.tv_matches.length > 1
              && Object.keys(telaoState.brackets || {}).length === 2
              ? telaoState
              : null;
            """
        )
    )
    assert len(driver.find_elements(By.CSS_SELECTOR, "#telao-grid")) == 1
    wait(driver).until(EC.text_to_be_present_in_element((By.ID, "telao-grid"), "D1A-Jogador"))
    wait(driver).until(lambda browser: len(browser.find_elements(By.CSS_SELECTOR, ".telao-card")) == 3)
    assert driver.find_element(By.ID, "telao-countdown").text.startswith("Placar")

    driver.find_element(By.ID, "telao-radio-menu-button").click()
    wait(driver).until(EC.visibility_of_element_located((By.ID, "telao-radio-menu")))
    assert len(driver.find_elements(By.CSS_SELECTOR, "#telao-radio-menu [data-radio-id]")) == 14
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
    driver.find_element(By.CSS_SELECTOR, '[data-radio-id="mgt-classicos-sertanejos"]').click()
    assert "/radio/8000/aac" in driver.find_element(By.ID, "telao-radio-audio").get_attribute("src")

    initial_zoom = float(driver.execute_script("return Number(document.documentElement.style.zoom || 1)"))
    driver.find_element(By.ID, "telao-zoom-in").click()
    wait(driver).until(
        lambda browser: float(browser.execute_script("return Number(document.documentElement.style.zoom || 1)")) > initial_zoom
    )
    driver.find_element(By.ID, "telao-zoom-out").click()

    wait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".telao-bracket-card")))
    assert driver.find_element(By.ID, "telao-countdown").text.startswith("Chaveamento")
    assert driver.find_elements(By.CSS_SELECTOR, ".telao-bracket-card .bracket-photo")

    wait(driver, 12).until(
        lambda browser: browser.execute_script("return currentMode === 'matches' && currentMatchIndex === 0;")
    )
    first_result_text = driver.find_element(By.CSS_SELECTOR, ".latest-result-card").text
    assert driver.find_element(By.ID, "telao-countdown").text.startswith("Confrontos 1 de ")
    assert state["tv_matches"][0]["player1_name"] in first_result_text
    assert state["tv_matches"][0]["player2_name"] in first_result_text

    wait(driver, 8).until(
        lambda browser: browser.execute_script("return currentMode === 'matches' && currentMatchIndex >= 1;")
    )
    second_result_text = driver.find_element(By.CSS_SELECTOR, ".latest-result-card").text
    assert driver.find_element(By.ID, "telao-countdown").text.startswith("Confrontos 2 de ")
    assert state["tv_matches"][1]["player1_name"] in second_result_text
    assert state["tv_matches"][1]["player2_name"] in second_result_text


@pytest.mark.telao_cycle
def test_telao_skips_zero_second_phases(driver):
    seed_telao_cycle_data({
        "table_seconds": 0,
        "bracket_seconds": 0,
        "sponsor_seconds": 0,
        "match_seconds": 2,
    })
    driver.get(f"{BASE_URL}/telao")
    state = wait(driver).until(
        lambda browser: browser.execute_script(
            """
            return typeof telaoState !== 'undefined'
              && telaoState
              && telaoState.config.tv_config.table_seconds === 0
              && telaoState.config.tv_config.bracket_seconds === 0
              && telaoState.config.tv_config.sponsor_seconds === 0
              && telaoState.tv_matches.length > 1
              ? telaoState
              : null;
            """
        )
    )
    wait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".latest-result-card")))

    assert driver.execute_script("return currentMode") == "matches"
    assert driver.find_element(By.ID, "telao-countdown").text.startswith("Confrontos 1 de ")
    assert not driver.find_elements(By.CSS_SELECTOR, ".telao-card")
    assert not driver.find_elements(By.CSS_SELECTOR, ".telao-bracket-card")
    result_text = driver.find_element(By.CSS_SELECTOR, ".latest-result-card").text
    assert state["tv_matches"][0]["player1_name"] in result_text
    assert state["tv_matches"][0]["player2_name"] in result_text
