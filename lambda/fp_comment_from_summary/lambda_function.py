import os
import json
import boto3
from openai import OpenAI
from datetime import datetime

# OpenAIクライアント初期化
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

# --- FPコメント生成関数 ---
def generate_fp_comment(summary_json):
    prompt_template = f"""
あなたは経験豊富で親しみやすいファイナンシャルプランナーです。

以下に、ある家庭の家計データを提供します。
この家庭は夫婦2人と乳児の3人家族で、収入は会社員1名による固定給です。

### 利用者の基本情報（参考）
- 家族構成：夫婦＋乳児（1歳未満）
- 職業：会社員（安定収入）
- 家計目標：毎月3〜5万円の貯金を目指している
- 支出に対して比較的敏感で、定期的に家計チェックをしている
- 今後は子育て費用や固定費の見直しを進めたいと考えている

### 家計データの内容について

このデータには以下の情報が含まれています：

1. `monthly`
  → 月ごとの収入・支出・差額（net）

2. `weekly`
  → 週ごとの収入・支出・差額（net）

3. `category_monthly`
  → 月ごとのカテゴリ別支出金額（例：食費、交際費など）

4. `category_weekly`
  → 週ごとのカテゴリ別支出金額

5. `unclassified_total`
  → 「未分類」に分類された支出の合計金額（何に使ったか不明）

### コメント出力の目的と要件

このデータを分析して、以下の要点に沿ったファイナンシャルコメントを生成してください：

#### 【重視ポイント】
- 月単位・週単位での収支バランスの変化
- 支出カテゴリ別で増減の目立つ項目への言及
- 「未分類」の金額が大きい場合は注意喚起
- 家計全体としての傾向・改善ポイント
- 目標（毎月3〜5万円の貯金）と比べてどうか

#### 【出力フォーマット】
---
【今月の家計のポイント】
・（一言で要点まとめ）

【先月との比較】
・収入や支出、特定のカテゴリでの増減傾向
・貯蓄目標との差や進捗

【先週との比較】
・短期的な支出の動き、増減傾向
・気になる支出や特徴的な動き

【FPからのひとことアドバイス】
・改善提案や継続への励まし、安心コメント
---

これらを日本語で、わかりやすく、やや親しみを込めた語り口で書いてください。
分析対象のデータは以下のJSONです：

{json.dumps(summary_json, ensure_ascii=False)}
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o",  # 推奨：精度重視
            messages=[{"role": "user", "content": prompt_template}]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[ERROR] コメント生成失敗: {e}")
        return f"コメント生成エラー: {e}"

# --- LINE通知関数の呼び出し ---
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

# --- Lambdaエントリポイント ---
def lambda_handler(event, context):
    try:
        print("[DEBUG] event:", json.dumps(event, indent=2, ensure_ascii=False))

        user_id = event.get("user_id")
        if not user_id:
            raise ValueError("user_id が渡されていません。")

        # DynamoDBからjson_path取得
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(os.environ["DYNAMODB_TABLE_NAME"])
        response = table.get_item(Key={"userId": user_id})

        if "Item" not in response or "json_path" not in response["Item"]:
            raise ValueError("対象の JSON パスが見つかりません。")

        json_key = response["Item"]["json_path"]
        bucket = os.environ["S3_BUCKET_NAME"]

        print(f"[INFO] ユーザーID: {user_id}")
        print(f"[INFO] JSONファイルキー: {json_key}")

        # S3からJSON取得
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=json_key)
        content = obj["Body"].read().decode("utf-8")
        summary_json = json.loads(content)

        # コメント生成
        comment = generate_fp_comment(summary_json)

        # LINE通知送信
        invoke_line_notifier(user_id, comment)

        print("📝 FPコメント生成完了:")
        print(comment)

        return {
            "statusCode": 200,
            "body": json.dumps({"fp_comment": comment}, ensure_ascii=False)
        }

    except Exception as e:
        print("[ERROR]", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}, ensure_ascii=False)
        }