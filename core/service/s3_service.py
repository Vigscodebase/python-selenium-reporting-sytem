from utils.logging import *
from botocore.exceptions import ClientError

import csv, os, shutil
from datetime import date

from utils.s3 import S3
class S3Service():
    s3 = S3()
    
    def __init__(self):
        self.s3_client = self.s3.get_s3_client()
    
    def read_s3_csv_file(self):
        log.info("Reading CSV File: %s from S3 Bucket: %s " % (BUCKET_NAME,INPUT_FILE_PATH))
        obj = self.s3_client.get_object(Bucket=BUCKET_NAME, Key=INPUT_FILE_PATH) #2
        data = obj['Body'].read().decode('utf-8-sig').splitlines() #3
        records = csv.reader(data,delimiter=",") #4
        headers = next(records) #5
        csv_data = []
        header_count = len(headers)
        for record in records: #6
            if record[0].strip():
                tmp = {}
                for count in range(0,header_count):
                    tmp[headers[count]] = record[count]
                csv_data.append(tmp)
        return csv_data

    def upload_file_s3(self,domain,report_day,report_type):
        url = None
        file_name = None
        folder_path = LOCAL_PATH + domain + "/"+report_day+"/" + report_type + "/"
        log.debug("Checking for File in: %s " % (folder_path))
        is_folder_exist = os.path.exists(folder_path)
        if is_folder_exist:
            all_files = os.listdir(folder_path)
            if all_files:
                file = all_files[0]
                file_name = all_files[0].replace(" ","")
                file_path = folder_path + file_name
                today = date.today()
                year = int(today.year)
                month = int(today.month)
                report_date = "%s-%s-%s" % ('{:02d}'.format(int(report_day)),'{:02d}'.format(month),year)
                object_name = OUTPUT_PATH+domain + "/"+report_date+"/"+ report_type + "/" +file_name
                try:
                    log.info("Succesfully downloaded file %s" % file_path)
                    self.s3_client.upload_file(file_path, BUCKET_NAME, object_name)
                    url = "https://s3.amazonaws.com/%s/%s" % (BUCKET_NAME, object_name)

                    log.info("Succesfully Uploaded File to the bucket: %s as %s " % (BUCKET_NAME,object_name))
                    return True, url,file_name
                except ClientError as e:
                    log.error("Failed to Upload the file to bucket: %s" % BUCKET_NAME)
                    log.error(e)
        return False, url,file_name

    def remove_files(self):
        folder = LOCAL_PATH
        for filename in os.listdir(folder):
            file_path = os.path.join(folder, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                log.error('Failed to delete %s. Reason: %s' % (file_path, e))


