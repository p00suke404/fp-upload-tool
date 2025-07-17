import csv
import boto3
import os
import json
#import openai
import csv
import io
from datetime import datetime
from collections import defaultdict
from openai import OpenAI

#openai.api_key = os.environ['OPENAI_API_KEY']
client = OpenAI(api_key=os.environ['OPENAI_API_KEY'])

# マネーフォワードMEのデフォルトカテゴリ
DEFAULT_MAIN_CATEGORIES = ["食費", "日用品", "趣味・娯楽", "交際費", "交通費", "衣服・美容", "健康・医療", "自動車", "教養・教育", "住まい", "水道・光熱費", "通信費", "保険", "税金", "現金・カード", "その他"]
DEFAULT_SUB_CATEGORIES = ["外食", "食料品", "コンビニ", "ドラッグストア", "本", "映画・音楽", "旅行", "交際", "電車", "ガソリン", "衣服", "美容院", "病院", "歯医者", "学費", "家賃", "電気代", "水道代", "スマホ", "インターネット", "生命保険", "住民税", "現金引き出し", "クレジットカード", "未分類"]

def classify_with_gpt(text):
    prompt = f"""
以下の内容に対して、もっとも適切な「大項目」と「中項目」をマネーフォワードMEのカテゴリから選んでください。

内容: {text}

【大項目候補】:
{", ".join(DEFAULT_MAIN_CATEGORIES)}

【中項目候補】:
{", ".join(DEFAULT_SUB_CATEGORIES)}

フォーマット:
大項目: <カテゴリ名>
中項目: <カテゴリ名>
"""
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        #content = response['choices'][0]['message']['content']
        content = response.choices[0].message.content.strip()

        main = sub = "未分類"
        for line in content.splitlines():
            if line.startswith("大項目:"):
                main = line.split(":", 1)[1].strip()
            elif line.startswith("中項目:"):
                sub = line.split(":", 1)[1].strip()
        return main, sub
    except Exception as e:
        print(f"分類エラー: {str(e)}")
        return "未分類", "未分類"

def parse_csv_from_s3(bucket, key):
    s3 = boto3.client('s3')
    response = s3.get_object(Bucket=bucket, Key=key)
    content = response['Body'].read().decode('utf-8').splitlines()
    return list(csv.DictReader(content))

def enrich_rows(rows):
    enriched = []
    for row in rows:
        main_cat = row.get("大項目", "未分類")
        sub_cat = row.get("中項目", "未分類")
        memo = row.get("内容", "")

        if main_cat == "未分類" or sub_cat == "未分類":
            guessed_main, guessed_sub = classify_with_gpt(memo)
            if main_cat == "未分類":
                row["大項目"] = guessed_main
            if sub_cat == "未分類":
                row["中項目"] = guessed_sub
        enriched.append(row)
    return enriched

def summarize_weekly(rows):
    summary = defaultdict(lambda: {'income': 0, 'expense': 0})
    for row in rows:
        date = datetime.strptime(row['日付'], '%Y/%m/%d')
        week_key = date.strftime('%Y-W%U')
        amount = float(row['金額（円）'])
        category = row['大項目']
        if category == '収入':
            summary[week_key]['income'] += amount
        else:
            summary[week_key]['expense'] += amount
    return format_summary(summary, 'week')

def summarize_monthly(rows):
    summary = defaultdict(lambda: {'income': 0, 'expense': 0})
    for row in rows:
        date = datetime.strptime(row['日付'], '%Y/%m/%d')
        month_key = date.strftime('%Y-%m')
        amount = float(row['金額（円）'])
        category = row['大項目']
        if category == '収入':
            summary[month_key]['income'] += amount
        else:
            summary[month_key]['expense'] += amount
    return format_summary(summary, 'month')

def summarize_by_category(rows):
    summary = defaultdict(float)
    for row in rows:
        category = row['中項目']
        amount = float(row['金額（円）'])
        summary[category] += amount
    return [{"category": cat, "total": amt} for cat, amt in sorted(summary.items())]

# 追加: 週 × 中項目ごとの合計
def summarize_category_weekly(rows):
    summary = defaultdict(lambda: defaultdict(float))  # week -> category -> amount
    for row in rows:
        date = datetime.strptime(row['日付'], '%Y/%m/%d')
        week_key = date.strftime('%Y-W%U')
        category = row['中項目']
        amount = float(row['金額（円）'])
        summary[week_key][category] += amount

    result = []
    for week, categories in sorted(summary.items()):
        for cat, amt in sorted(categories.items()):
            result.append({
                "week": week,
                "category": cat,
                "amount": amt
            })
    return result

# 追加: 月 × 中項目ごとの合計
def summarize_category_monthly(rows):
    summary = defaultdict(lambda: defaultdict(float))  # month -> category -> amount
    for row in rows:
        date = datetime.strptime(row['日付'], '%Y/%m/%d')
        month_key = date.strftime('%Y-%m')
        category = row['中項目']
        amount = float(row['金額（円）'])
        summary[month_key][category] += amount

    result = []
    for month, categories in sorted(summary.items()):
        for cat, amt in sorted(categories.items()):
            result.append({
                "month": month,
                "category": cat,
                "amount": amt
            })
    return result

def format_summary(summary_dict, period_key_name):
    result = []
    for key, data in sorted(summary_dict.items()):
        result.append({
            period_key_name: key,
            "income": data['income'],
            "expense": data['expense'],
            "net": data['income'] - data['expense']
        })
    return result

# TEST-CODE
def write_csv_to_s3(rows, bucket, key):
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    s3 = boto3.client('s3')
    s3.put_object(Bucket=bucket, Key=key, Body=output.getvalue().encode('utf-8'))
    print(f"[S3出力] 補完済CSVを保存しました → s3://{bucket}/{key}")

def lambda_handler(event, context):
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']

    rows = parse_csv_from_s3(bucket, key)
    enriched_rows = enrich_rows(rows)

    # S3に出力
#    output_key = f"outputs/enriched_{os.path.basename(key)}"
#    write_csv_to_s3(enriched_rows, bucket, output_key)

    result = {
        "weekly": summarize_weekly(enriched_rows),
        "monthly": summarize_monthly(enriched_rows),
        "category": summarize_by_category(enriched_rows),
        "category_weekly": summarize_category_weekly(enriched_rows),
        "category_monthly": summarize_category_monthly(enriched_rows)
    }

    return {
        "statusCode": 200,
        "body": json.dumps(result, ensure_ascii=False)
    }
