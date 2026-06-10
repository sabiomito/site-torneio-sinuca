import pytest
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from support import BASE_URL
from test_full_tournament import validate_telao


@pytest.mark.telao_cycle
def test_real_telao_cycle_with_existing_local_data(driver):
    driver.get(f"{BASE_URL}/telao")
    state = WebDriverWait(driver, 30).until(
        lambda browser: browser.execute_script(
            """
            return typeof telaoState !== 'undefined'
              && telaoState
              && telaoState.sponsors.length
              && telaoState.latest_result
              ? telaoState
              : null;
            """
        )
    )
    assert len(driver.find_elements(By.CSS_SELECTOR, "#telao-grid")) == 1
    validate_telao(driver, state["sponsors"], state["latest_result"])
