import boto3
import os
from datetime import datetime, timedelta
from fpdf import FPDF
import json

def generate_pdf(summary_json, filepath="/tmp/report.pdf"):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt="家計レポート", ln=True, align="C")
    pdf.multi_cell(0, 10, txt=json.dumps(summary_json, ensure_ascii=False, indent=2))
    pdf.output(filepath)

def generate_presigned_url(bucket, key, expiration=3600):
    s3 = boto3.client("s3")
    return s3.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket, 'Key': key},
        ExpiresIn=expiration
    )

def notify_line(user_id, presigned_url):
    lambda_client = boto3.client("lambda")
    payload = {
        "userId": user_id,
        "message": f"📄 家計レポートのPDFができました！\nこちらからダウンロードできます👇\n{presigned_url}"
    }
    lambda_client.invoke(
        FunctionName="line_notifier",
        InvocationType="Event",
        Payload=json.dumps(payload).encode("utf-8")
    )

def lambda_handler(event, context):
    user_id = event["user_id"]
    summary_json = event["summary_json"]  # またはS3から読み取ってもOK
    bucket = os.environ["S3_BUCKET_NAME"]
    timestamp = datetime.utcnow().strftime("%Y-%m-%d-%H%M")
    key = f"reports/{user_id}/{timestamp}.pdf"

    # 1. PDF作成
    generate_pdf(summary_json, "/tmp/report.pdf")

    # 2. アップロード
    s3 = boto3.client("s3")
    s3.upload_file("/tmp/report.pdf", bucket, key)

    # 3. Presigned URL生成
    url = generate_presigned_url(bucket, key)

    # 4. LINE通知
    notify_line(user_id, url)

    return {
        "statusCode": 200,
        "body": json.dumps({"url": url})
    }