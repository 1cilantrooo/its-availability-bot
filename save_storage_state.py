from playwright.sync_api import sync_playwright

LOGIN_URL = "https://xxxxx.its-kenpo.or.jp/xxxx/login"  # ←ITSのログインURLに変えてね
STATE_FILE = "storage_state.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)  # 画面ありで立ち上げ
    context = browser.new_context()
    page = context.new_page()
    page.goto(LOGIN_URL)
    print(">>> ここで手動ログインしてください。ログイン後、施設予約検索ページまで進んだらEnter")
    input()
    context.storage_state(path=STATE_FILE)
    print(f">>> {STATE_FILE} を保存しました")
    browser.close()