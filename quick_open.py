from playwright.sync_api import sync_playwright
print("[TEST] start")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, channel="chrome", slow_mo=200)
    page = browser.new_page()
    page.goto("https://example.com", timeout=20000)
    page.wait_for_timeout(2000)
    browser.close()
print("[TEST] end")
