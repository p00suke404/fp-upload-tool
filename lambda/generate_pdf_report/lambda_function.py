import boto3
import os
from datetime import datetime
from fpdf import FPDF
import json

# PDF生成関数
def generate_pdf(summary_json, filepath="/tmp/report.pdf"):
    pdf = FPDF()
    pdf.add_page()

    # フォント設定（日本語表示のため ipaexg.ttf 必須）
    font_path = os.path.join(os.path.dirname(__file__), "ipaexg.ttf")
    pdf.add_font("IPAexGothic", "", font_path, uni=True)
    pdf.set_font("IPAexGothic", "", 14)

    # タイトル
    pdf.set_text_color(0, 70, 140)
    pdf.cell(0, 10, txt="家計レポート", ln=True, align="C")
    pdf.set_draw_color(0, 70, 140)
    pdf.set_line_width(0.8)
    pdf.line(10, 20, 200, 20)
    pdf.ln(10)

    # 日付
    now = datetime.now().strftime("%Y年%m月%d日 %H:%M")
    pdf.set_text_color(0)
    pdf.set_font("IPAexGothic", "", 10)
    pdf.cell(0, 10, txt=f"作成日: {now}", ln=True)
    pdf.ln(5)

    # 各セクション出力
    def render_section(title, data):
        pdf.set_font("IPAexGothic", "", 12)
        pdf.set_text_color(0, 0, 0)
        pdf.set_fill_color(220, 220, 220)
        pdf.cell(0, 10, title, ln=True, fill=True)
        pdf.set_font("IPAexGothic", "", 10)
        pdf.multi_cell(0, 8, txt=json.dumps(data, ensure_ascii=False, indent=2))
        pdf.ln(5)

    if 'month_summary' in summary_json:
        render_section("月次収支", summary_json["month_summary"])

    if 'week_summary' in summary_json:
        render_section("週次収支", summary_json["week_summary"])

    if 'monthly_by_category' in summary_json:
        render_section("月次カテゴリ別集計", summary_json["monthly_by_category"])

    if 'weekly_by_category' in summary_json:
        render_section("週次カテゴリ別集計", summary_json["weekly_by_category"])

    if 'unclassified_total' in summary_json:
        render_section("未分類合計", {"未分類合計": summary_json["unclassified_total"]})

    # PDF保存
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