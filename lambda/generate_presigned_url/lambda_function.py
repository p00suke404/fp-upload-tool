import json
import boto3
import os
import uuid
from datetime import datetime

def notify_user_upload_url(user_id):
    lambda_client = boto3.client('lambda')
    upload_page_url = f"https://{os.environ['API_GATEWAY_DOMAIN']}/prod/upload?user_id={user_id}"
    payload = {
        "userId": user_id,
        "message": f"🧾 CSVファイルはこちらからアップロードしてください！\n\n{upload_page_url}"
    }
    lambda_client.invoke(
        FunctionName="line_notifier",
        InvocationType="Event",  # 非同期
        Payload=json.dumps(payload).encode("utf-8")
    )



dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['DYNAMODB_TABLE_NAME'])

def save_user_csv_path(user_id, csv_key):
    table.put_item(
        Item={
            'userId': user_id,
            'csv_path': csv_key,
            'created_at': datetime.utcnow().isoformat() + "Z"
        }
    )

def lambda_handler(event, context):
    try:
        print("[DEBUG] event:", json.dumps(event))

        # LINE Webhook形式の判定
        #is_line_webhook = "body" in event and event["body"] and "events" in json.loads(event["body"])
        user_id = event.get("queryStringParameters", {}).get("user_id")
        is_from_line_webhook = event.get("is_from_webhook", False) is True
        print(is_from_line_webhook)
        print(user_id)
        if is_from_line_webhook:
            # LINEのWebhookイベントからuserIdを取得
            #body = json.loads(event["body"])
            #user_id = body["events"][0]["source"]["userId"]
            print(f"[INFO] LINE webhook からの user_id: {user_id}")

            # LINEにアップロードページURLを通知
            notify_user_upload_url(user_id)

            return {
                "statusCode": 200,
                "body": json.dumps({"message": "LINE通知を送信しました"})
            }

        # Webhookでなければブラウザアクセス（署名付きURL & HTMLフォームを返す）
        s3 = boto3.client('s3')
        bucket_name = os.environ['BUCKET_NAME']
        unique_id = str(uuid.uuid4())[:8]
        object_key = f"uploads/moneyforward_{unique_id}.csv"

        presigned_url = s3.generate_presigned_post(
            Bucket=bucket_name,
            Key=object_key,
            Fields={"Content-Type": "text/csv"},
            Conditions=[{"Content-Type": "text/csv"}],
            ExpiresIn=3600
        )

        # LINEユーザIDとCSVファイルパスをDynamoDBに登録
        save_user_csv_path(user_id, object_key)

        html_fields = "\n".join(
            [f'<input type="hidden" name="{k}" value="{v}">' for k, v in presigned_url['fields'].items()]
        )
        
        html_body = f"""
        <!DOCTYPE html>
        <html lang="ja">
        <head>
            <meta charset="UTF-8">
            <title>CSVアップロード</title>
            <style>
                body {{
                    font-family: 'Segoe UI', sans-serif;
                    background-color: #f4f4f4;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    justify-content: center;
                    height: 100vh;
                    margin: 0;
                }}
                .container {{
                    background-color: #fff;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                    text-align: center;
                }}
                h2 {{
                    color: #333;
                    margin-bottom: 20px;
                }}
                input[type="file"] {{
                    margin-bottom: 20px;
                }}
                button {{
                    background-color: #28a745;
                    color: white;
                    padding: 10px 20px;
                    border: none;
                    border-radius: 5px;
                    font-size: 16px;
                    cursor: pointer;
                }}
                button:hover {{
                    background-color: #218838;
                }}
                .success-message {{
                    display: none;
                    margin-top: 20px;
                    color: #155724;
                    background-color: #d4edda;
                    padding: 15px;
                    border-radius: 5px;
                    border: 1px solid #c3e6cb;
                }}
                iframe {{
                    display: none;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h2>📄 CSVファイルをアップロードしてください</h2>
                <form id="upload-form" action="{presigned_url['url']}" method="post" enctype="multipart/form-data" target="hidden-frame" onsubmit="handleSubmit()">
                    {html_fields}
                    <input type="file" name="file" accept=".csv" required />
                    <br><br>
                    <button type="submit">アップロード</button>
                </form>
                <div class="success-message" id="success-message">
                    ✅ アップロードが完了しました。<br>この画面は閉じていただいて構いません。
                </div>
                <iframe name="hidden-frame" onload="handleUploadComplete()"></iframe>
            </div>
        
            <script>
                let isSubmitting = false;
        
                function handleSubmit() {{
                    isSubmitting = true;
                }}
        
                function handleUploadComplete() {{
                    if (isSubmitting) {{
                        document.getElementById('upload-form').style.display = 'none';
                        document.getElementById('success-message').style.display = 'block';
                        isSubmitting = false;
                    }}
                }}
            </script>
        </body>
        </html>
        """



        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/html"
            },
            "body": html_body
        }

    except Exception as e:
        print("[ERROR]", str(e))
        return {
            "statusCode": 400,
            "body": json.dumps({"error": f"userIdの取得に失敗しました: {e}"})
        }
