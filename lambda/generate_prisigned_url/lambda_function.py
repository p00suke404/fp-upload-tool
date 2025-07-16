import json
import boto3
import os
import uuid

def lambda_handler(event, context):
    s3 = boto3.client('s3')
    
    bucket_name = os.environ['BUCKET_NAME']
    unique_id = str(uuid.uuid4())[:8]
    object_key = f"uploads/moneyforward_{unique_id}.csv"
    
    presigned_url = s3.generate_presigned_url(
        'put_object',
        Params={'Bucket': bucket_name, 'Key': object_key, 'ContentType': 'text/csv'},
        ExpiresIn=3600
    )
    
    return {
        "statusCode": 200,
        "headers": {
            "Access-Control-Allow-Origin": "*"
        },
        "body": json.dumps({
            "upload_url": presigned_url,
            "filename": object_key
        })
    }
