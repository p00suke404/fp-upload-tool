import boto3
import os
from datetime import datetime
from fpdf import FPDF
import json

# PDF生成関数
def generate_pdf(summary_json, filepath="/tmp/report.pdf"):
    from fpdf import FPDF
    from datetime import datetime

    pdf = FPDF()
    pdf.add_page()
    font_path = os.path.join(os.path.dirname(__file__), "ipaexg.ttf")
    pdf.add_font("IPAexGothic", "", font_path, uni=True)
    pdf.add_font("IPAexGothic", "B", font_path, uni=True)  # 太字用としても追加
    pdf.set_font("IPAexGothic", size=12)

    # タイトル
    pdf.set_font("IPAexGothic", "B", 16)
    pdf.cell(0, 10, "家計レポート", ln=True, align="C")
    pdf.set_font("IPAexGothic", "", 12)
    pdf.cell(0, 10, f"作成日: {datetime.utcnow().strftime('%Y年%m月%d日 %H:%M')}", ln=True)

    pdf.ln(5)

    # 未分類合計
    if "unclassified_total" in summary_json:
        unclassified = summary_json["unclassified_total"]
        pdf.set_font("IPAexGothic", "B", 14)
        pdf.cell(0, 10, "未分類合計", ln=True)
        pdf.set_font("IPAexGothic", "", 12)
        pdf.cell(0, 10, f"カテゴリ: {unclassified['category']} / 合計: {unclassified['total']}円", ln=True)
        pdf.ln(5)

    # 月次収支
    if "monthly" in summary_json:
        pdf.set_font("IPAexGothic", "B", 14)
        pdf.cell(0, 10, "月次収支", ln=True)
        pdf.set_font("IPAexGothic", "", 12)
        for item in summary_json["monthly"]:
            pdf.cell(0, 10, f"{item['month']}: 収入 {item['income']}円 / 支出 {item['expense']}円 / 収支 {item['net']}円", ln=True)
        pdf.ln(5)

    # カテゴリ別月次
    if "category_monthly" in summary_json:
        pdf.set_font("IPAexGothic", "B", 14)
        pdf.cell(0, 10, "月別カテゴリ集計", ln=True)
        pdf.set_font("IPAexGothic", "", 12)
        current_month = None
        for item in summary_json["category_monthly"]:
            if current_month != item["month"]:
                pdf.ln(3)
                pdf.cell(0, 10, f"■ {item['month']}", ln=True)
                current_month = item["month"]
            pdf.cell(0, 10, f"{item['category']}: {item['amount']}円", ln=True)

    pdf.output(filepath)
 
# 署名付きURL生成
def generate_presigned_url(bucket, key, expiration=3600):
    s3 = boto3.client("s3")
    return s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=expiration
    )

# LINE通知関数をinvoke
def notify_line(user_id, presigned_url):
    lambda_client = boto3.client("lambda")
    payload = {
        "userId": user_id,
        "message": f"家計レポートのPDFができました！\nこちらからダウンロードできます\n{presigned_url}"
    }
    lambda_client.invoke(
        FunctionName="line_notifier",
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8")
    )

# Lambdaハンドラ
def lambda_handler(event, context):
    try:
        user_id = event.get("user_id")
        if not user_id:
            raise ValueError("user_id が指定されていません")

        filepath = "/tmp/report.pdf"
        if os.path.exists(filepath):
            os.remove(filepath)

        # JSONパスをDynamoDBから取得
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(os.environ["DYNAMODB_TABLE_NAME"])
        response = table.get_item(Key={"userId": user_id})

        if "Item" not in response or "json_path" not in response["Item"]:
            raise ValueError("DynamoDB に json_path が存在しません")

        json_key = response["Item"]["json_path"]
        bucket = os.environ["S3_BUCKET_NAME"]

        # S3からsummary_jsonを取得
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=bucket, Key=json_key)
        content = obj["Body"].read().decode("utf-8")
        summary_json = json.loads(content)

        # ファイル名とローカル保存先
        timestamp = datetime.utcnow().strftime("%Y-%m-%d-%H%M")
        key = f"reports/{user_id}/{timestamp}.pdf"
        local_path = filepath

        # PDF生成とアップロード
        generate_pdf(summary_json, local_path)
        s3.upload_file(local_path, bucket, key)

        # Presigned URL生成
        url = generate_presigned_url(bucket, key)

        # LINE通知送信
        notify_line(user_id, url)

        return {
            "statusCode": 200,
            "body": json.dumps({"url": url})
        }

    except Exception as e:
        print("[ERROR]", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }