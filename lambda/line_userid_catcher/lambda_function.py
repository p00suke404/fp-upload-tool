import json
import boto3
import os

# 定数定義（対象メッセージなど）
UPLOAD_TRIGGER_TEXT = "家計ファイルをアップロードしたい"
FP_REQUEST_TEXT = "家計診断をお願いします"
LAMBDA_UPLOAD = "generatePresignedUrl"
LAMBDA_FP_COMMENT = "fp_comment_from_summary"

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE_NAME'])

def invoke_presign_url_function(user_id):
    lambda_client = boto3.client('lambda')
    payload = {
        "is_from_webhook": True,
        "queryStringParameters": {
            "user_id": user_id
        }
    }
    lambda_client.invoke(
        FunctionName=LAMBDA_UPLOAD,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8")
    )

def invoke_fp_comment_function(user_id):
    lambda_client = boto3.client('lambda')
    payload = {
            "user_id": user_id
    }
    lambda_client.invoke(
        FunctionName=LAMBDA_FP_COMMENT,
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8")
    )

def lambda_handler(event, context):
    try:
        print("[DEBUG] event:", event)
        body = json.loads(event.get("body", "{}"))
        events = body.get("events", [])

        for e in events:
            if e.get("type") != "message":
                print(f"[INFO] 対応しないイベントタイプ: {e.get('type')}")
                continue

            user_id = e.get("source", {}).get("userId")
            message_text = e.get("message", {}).get("text", "").strip()

            if not user_id:
                print("[WARN] userId が取得できませんでした")
                continue

            print(f"[INFO] ユーザーIDを取得: {user_id}")
            print(f"[INFO] 受信メッセージ: {message_text}")

            if message_text == UPLOAD_TRIGGER_TEXT:
                print("[INFO] アップロード要求検出 → Presign URL 発行")
                invoke_presign_url_function(user_id)

                # DynamoDB登録（重複チェック付き）
                response = table.get_item(Key={"userId": user_id})
                if "Item" in response:
                    print(f"[INFO] すでに登録済みの userId: {user_id}")
                else:
                    table.put_item(Item={"userId": user_id})
                    print(f"[INFO] 新規登録完了: {user_id}")

            elif message_text == FP_REQUEST_TEXT:
                print("[INFO] 家計診断要求を検出 → FPコメント関数をInvoke")
                invoke_fp_comment_function(user_id)

            else:
                print(f"[INFO] 未対応のメッセージ内容: {message_text}")

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "完了"})
        }

    except Exception as e:
        print("[ERROR]", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
