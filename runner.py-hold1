#!/usr/bin/env python3

from utils.logging import *
from core.service.s3_service import S3Service
from core.service.dsr_service import DSRService
from core.scraper.download_report import ReportDownloader
from core.service.email_service import EmailService
import time
from datetime import date
import sys, os
import multiprocessing
from multiprocessing import Process
import schedule
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

class Runner:
    def __init__(self):
        # Initialize services
        self.dsr_service = DSRService()
        self.downloader = ReportDownloader()
        self.email_service = EmailService()
        self.s3service = S3Service()

    @staticmethod
    def sanitize_filename(filepath, domain, report_day, report_type):
        all_files = os.listdir(filepath)
        index = 0
        today = date.today()
        year = int(today.year)
        month = int(today.month)
        for file in all_files:
            index += 1
            old_name = file
            domain = domain if domain else '_'
            report_date = f"{int(report_day):02d}-{month:02d}-{year}" if report_day else '_'
            report_type = report_type if report_type else '_'
            index_val = f'_{index}' if index > 1 else ''
            new_name = f"{domain}_{report_date}_{report_type}{index_val}.pdf"
            try:
                old = os.path.join(filepath, old_name)
                new = os.path.join(filepath, new_name)
                if old != new:
                    os.rename(old, new)
            except Exception as e:
                log.error(f"Error renaming file: {e}")

    def read_csv_file(self):
        return self.s3service.read_s3_csv_file()

    def get_record_from_domain(self, domain, report_type):
        records = self.s3service.read_s3_csv_file()
        for record in records:
            if record["domain"] == domain and record["report_type"] == report_type:
                return record
        return None

    def process_record(self, record, response):
        if not record:
            log.error("Invalid record provided.")
            return response

        domain = record.get('domain')
        report_day = record.get('report_day')
        report_type = record.get('report_type')
        client_info = {}

        log.info(f"Processing record for domain: {domain}, report type: {report_type}")
        status = self.dsr_service.check_eligibility(report_day)

        if status:
            download_status = self.download_report(record, domain, report_day, report_type)
            if download_status:
                upload_status, url, file_name = self.s3service.upload_file_s3(domain, report_day, report_type)
                if not upload_status:
                    log.error(f"Processing failed for URL: {record['url']}")
                    client_info["status"] = False
                    client_info["message"] = "Processing Failed for URL."
                else:
                    attachment = os.path.join(LOCAL_PATH, domain, report_day, report_type, file_name)
                    subject, content = self.email_service.create_client_email_content(domain, record['client_name'], url, report_day, report_type)
                    status = self.email_service.send_email(subject, content, record['client_email'].split(","))
                    self.s3service.remove_files()
                    client_info["status"] = True
                    client_info["message"] = "Processing Successful for URL."
                    client_info["url"] = url
                    if not status:
                        client_info["status"] = False
                        client_info["message"] = "An error occurred while sending an email"
            else:
                client_info["status"] = False
                client_info["message"] = f"An error occurred while downloading for domain: {domain}"
        else:
            client_info["status"] = False
            client_info["message"] = f"Eligibility criteria was not met for domain: {domain}"
            log.info(f"Eligibility criteria was not met for domain: {domain}")

        response[f"{record['domain']}_{record['report_type']}"] = client_info
        return response

    def download_report(self, record, domain, report_day, report_type):
        max_tries = 3
        download_status = False
        for _ in range(max_tries):
            self.downloader.download_report(
                record['url'], record['domain'], record['report_day'], record['report_type'],
                record['client_name'], record['client_email'], record['am_email']
            )
            folder_path = os.path.join(LOCAL_PATH, domain, report_day, report_type)
            log.info(f"Checking for file in: {folder_path}")
            if os.path.exists(folder_path):
                self.sanitize_filename(folder_path, domain, report_day, report_type)
                download_status = True
                time.sleep(2)
                break
            else:
                log.info("Download failed.. Retrying Again")
        return download_status

    def send_summary_email(self, records, response):
        if records:
            subject, content = self.email_service.create_admin_email_content(response, s3_url)
            admin_emails = os.getenv('ADMIN_EMAIL', "").split(",")
            status = self.email_service.send_email(subject, content, admin_emails)
            log.info(f"Summary email sent successfully {status}")
        else:
            log.info("Summary email not sent.")

def runner_schedule():
    runner = Runner()
    response = {}
    records = runner.read_csv_file()
    for record in records:
        response = runner.process_record(record, response)
    runner.send_summary_email(records, response.copy())

if __name__ == '__main__':
    log.info("Running runner...")

    # Scheduling logic moved outside of `__main__` for clarity
    if len(sys.argv) == 3:
        runner = Runner()
        domain = sys.argv[1]
        report_type = sys.argv[2]
        record = runner.get_record_from_domain(domain, report_type)
        runner.process_record(record, {})
        log.info(f"Processing completed for domain: {domain}")
    else:
        # schedule.every().day.at("00:01").do(runner_schedule)  # Runs at 00:01 UTC (11:01 AM AEDT)
        schedule.every(2).seconds.do(runner_schedule)
        #schedule.every(0.2).minutes.do(runner_schedule)
        while True:
            log.info("Scheduler loop is running...")
            schedule.run_pending()
            time.sleep(1)
