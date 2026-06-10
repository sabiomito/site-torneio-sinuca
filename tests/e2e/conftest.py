import os
from pathlib import Path
from urllib.parse import urlparse

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options


BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8000").rstrip("/")


def assert_local_url():
    host = urlparse(BASE_URL).hostname
    if host not in {"localhost", "127.0.0.1", "::1"}:
        pytest.exit("E2E abortado: APP_BASE_URL precisa apontar para localhost.")


@pytest.fixture()
def driver(request, tmp_path):
    assert_local_url()
    options = Options()
    if os.environ.get("SELENIUM_HEADLESS", "1") != "0":
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    download_dir = tmp_path / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    options.add_experimental_option(
        "prefs",
        {
            "download.default_directory": str(download_dir.resolve()),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        },
    )
    browser = webdriver.Chrome(options=options)
    browser.download_dir = download_dir
    request.node._driver = browser
    yield browser
    browser.quit()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call" and report.failed:
        browser = getattr(item, "_driver", None)
        if browser:
            out_dir = Path("tests/e2e/screenshots")
            out_dir.mkdir(parents=True, exist_ok=True)
            browser.save_screenshot(str(out_dir / f"{item.name}.png"))
