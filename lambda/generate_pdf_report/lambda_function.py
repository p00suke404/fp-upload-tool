import boto3
import os
from datetime import datetime
from fpdf import FPDF
import json

#class JapanesePDF(FPDF):
#    def __init__(self):
#        super().__init__()
#        self.add_font('IPAexGothic', '', 'ipaexg.ttf', uni=True)
#        self.set_font('IPAexGothic', size=12)

def generate_pdf(summary_json, filepath="/tmp/report.pdf"):
    pdf = FPDF()
    pdf.add_page()

    # --- フォントの追加（ipaexg.ttf を利用） ---
    font_path = os.path.join(os.path.dirname(__file__), "ipaexg.ttf")
    pdf.add_font("IPAexGothic", "", font_path, uni=True)
    pdf.set_font("IPAexGothic", size=12)

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
    try:
        user_id = event.get("user_id")
        if not user_id:
            raise ValueError("user_id が指定されていません")

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

        # ファイル名
        timestamp = datetime.utcnow().strftime("%Y-%m-%d-%H%M")
        key = f"reports/{user_id}/{timestamp}.pdf"
        local_path = "/tmp/report.pdf"

        # PDF生成・保存
        generate_pdf(summary_json, local_path)

        # S3にアップロード
        s3.upload_file(local_path, bucket, key)

        # Presigned URL生成
        url = generate_presigned_url(bucket, key)

        # LINE通知
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