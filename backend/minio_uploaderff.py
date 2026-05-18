import os
from minio import Minio

def upload_to_minio(file_path, table_name):
    # Connect to MinIO API
    client = Minio(
        "localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        secure=False
    )

    # TRINO VIP BUCKET (Matches your catalog name exactly)
    bucket_name = "datalake" 

    if not client.bucket_exists(bucket_name):
        client.make_bucket(bucket_name)

    # CRITICAL FIX: Enforce "data.csv" to prevent duplicate file querying
    # Structure: interviewdetails123/table_name/data.csv
    object_name = f"{table_name}/data.csv"

    print(f"Uploading to bucket {bucket_name} as {object_name}...")
    client.fput_object(bucket_name, object_name, file_path)

    # Return only the exact folder path Trino needs
    s3_folder_path = f"s3a://{bucket_name}/{table_name}/"
    
    return s3_folder_path