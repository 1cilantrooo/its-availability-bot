from playwright.sync_api import sync_playwright

START_URL = "https://as.its-kenpo.or.jp/calendar_apply?s=PUVUUGtsMlg1SjNiblZHZGhOMlhsTldhMkpYWnpaU1oxSkhkOWtIZHcxV1o%3D"

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(START_URL)

        print("\n[手動] reCAPTCHAとログインを突破してください。")
        input("ログインが完了したら、このターミナルに戻って Enter を押してください。")

        context.storage_state(path="auth_state.json")
        print("auth_state.json を保存しました。")

        browser.close()