import os
import json
import boto3
from openai import OpenAI
from datetime import datetime

client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

# FPコメント生成
def generate_fp_comment(summary_json):
    prompt = f"""
利用者は3人家族です。成人2名に0歳児が1名います。共働きですが、奥さんが育児休業中です。目的は月単位での家計の把握です。
あなたはベテランFP人呼んで「藤原のパー子」40歳。
以下の家計データ（収支の週次、月次、カテゴリ別の集計の月次、週次）をもとに、利用者に向けたFPコメントを
日本語で出力してください。
・収支バランス（黒字/赤字）
・支出傾向（カテゴリ別の比率など）
・改善ポイント（節約・見直しの提案など）
・先月と比較し特に大きな動きのあるカテゴリ
・カテゴリ毎の金額の前月比

データ：
{json.dumps(summary_json, ensure_ascii=False)}

出力形式：
FPコメント: <コメント本文>
"""
    try:
        response = client.chat.completions.create(
            #model="gpt-3.5-turbo",
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"コメント生成エラー: {e}"

# LINE通知関数をInvoke
def invoke_line_notifier(user_id, message):
    lambda_client = boto3.client("lambda")
    payload = {
        "userId": user_id,
        "message": message
    }
    lambda_client.invoke(
        FunctionName="line_notifier",
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8")
    )

def lambda_handler(event, context):
    try:
        print("[DEBUG] event:", event)
        user_id = event.get("user_id")
        if not user_id:
            raise ValueError("user_id が渡されていません。")

        # DynamoDBからjson_pathを取得
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(os.environ["DYNAMODB_TABLE_NAME"])
        response = table.get_item(Key={"userId": user_id})

        if "Item" not in response or "json_path" not in response["Item"]:
            raise ValueError("対象の JSON パスが見つかりません。")

        json_key = response["Item"]["json_path"]
        bucket = os.environ["S3_BUCKET_NAME"]

        print(f"[INFO] ユーザー: {user_id}, JSONキー: {json_key}")

        # S3からJSONファイル取得
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=json_key)
        content = obj["Body"].read().decode("utf-8")
        summary_json = json.loads(content)

        # FPコメント生成
        comment = generate_fp_comment(summary_json)

        # LINE通知
        invoke_line_notifier(user_id, comment)

        print("📝 FPコメント生成:", comment)

        return {
            "statusCode": 200,
            "body": json.dumps({"fp_comment": comment}, ensure_ascii=False)
        }

    except Exception as e:
        print("[ERROR]", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
