import os
import requests

def notify_line_api(message: str):
    """LINE Messaging APIでメッセージを送信"""
    access_token = os.getenv("LINE_ACCESS_TOKEN")
    if not access_token:
        print("❌ LINE_ACCESS_TOKEN が設定されていません")
        return

    url = "https://api.line.me/v2/bot/message/push"

    # 自分のユーザーID（LINE Developersの「基本情報」→「あなたのユーザーID」で確認できる）
    user_id = os.getenv("LINE_USER_ID")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {access_token}"
    }

    payload = {
        "to": user_id,
        "messages": [{"type": "text", "text": message}]
    }

    resp = requests.post(url, headers=headers, json=payload)
    if resp.status_code != 200:
        print(f"❌ LINE送信失敗: {resp.status_code}, {resp.text}")
    else:
        print("✅ LINE通知送信成功")