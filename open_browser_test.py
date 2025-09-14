from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, channel="chrome", slow_mo=300)
    page = browser.new_page()
    page.goto("https://example.com")
    input("✅ ブラウザが見えていればOK。Enterで閉じます：")
    browser.close()