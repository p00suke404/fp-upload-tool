import os
import json
import boto3
#import requests
from openai import OpenAI

client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

def generate_fp_comment(summary_json):
    prompt = f"""
以下の家計データ（収支の週次、月次、カテゴリ別の集計）をもとに、利用者に向けた簡潔なFPコメントを日本語で出力してください。
・収支バランス（黒字/赤字）
・支出傾向（カテゴリ別の比率など）
・改善ポイント（節約・見直しの提案など）

データ：
{json.dumps(summary_json, ensure_ascii=False)}

出力形式：
FPコメント: <コメント本文>
"""

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content.strip()
        return content
    except Exception as e:
        return f"コメント生成エラー: {e}"

#def notify_line(message):
#    token = os.environ.get("LINE_TOKEN")
#    if not token:
#        print("LINE_TOKENが設定されていません")
#        return
#
#    try:
#        requests.post(
#            url='https://notify-api.line.me/api/notify',
#            headers={'Authorization': f'Bearer {token}'},
#            data={'message': message}
#        )
#        print("LINE通知を送信しました")
#    except Exception as e:
#        print(f"LINE通知エラー: {e}")

def lambda_handler(event, context):
    summary_json = event.get("summary")  # 前段から渡された集計データ（JSON）
    if not summary_json:
        return {"statusCode": 400, "body": "summaryが含まれていません"}

    comment = generate_fp_comment(summary_json)
    #notify_line(comment)

    return {
        "statusCode": 200,
        "body": json.dumps({"fp_comment": comment}, ensure_ascii=False)
    }
