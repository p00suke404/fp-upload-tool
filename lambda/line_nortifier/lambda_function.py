import os
import json
import requests

# LINEチャネルアクセストークン（環境変数で管理）
LINE_CHANNEL_TOKEN = os.environ.get("LINE_CHANNEL_TOKEN")
LINE_API_URL = "https://api.line.me/v2/bot/message/push"

def lambda_handler(event, context):
    # イベントから userId と message を受け取る
    user_id = event.get("userId")
    message = event.get("message")

    if not user_id or not message:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "userIdとmessageが必要です"})
        }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_TOKEN}"
    }

    body = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message
            }
        ]
    }

    try:
        response = requests.post(LINE_API_URL, headers=headers, json=body)
        response.raise_for_status()
        return {
            "statusCode": 200,
            "body": json.dumps({"result": "Message sent!"})
        }
    except requests.exceptions.RequestException as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
