from utils.logging import *

import boto3

class S3():
    def get_s3_client(self):
        return boto3.client('s3',aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
