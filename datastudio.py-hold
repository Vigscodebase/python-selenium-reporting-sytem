import schedule
import time
import logging
from core.service.s3_service import S3Service
from core.service.dsr_service import DSRService
from core.scraper.download_report import ReportDownloader
from core.service.email_service import EmailService
from datetime import date
import sys, os
import multiprocessing
from multiprocessing import Process
# from dotenv import load_dotenv
import os
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("utils")
# Load environment variables from .env file
# load_dotenv()
BUCKET_NAME = 'clickmatix-report'
LOCAL_PATH="/root/data/"

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
        log.info("Inside process_record")
        if not record:
            log.error("Invalid record provided.")
            return response

        domain = record.get('domain')
        report_day = record.get('report_day')
        report_type = record.get('report_type')
        client_info = {}

        log.info(f"Processing record for domain: {domain}, report type: {report_type}")
        status = self.dsr_service.check_eligibility(report_day)
        log.info(status)
        log.info(report_type)

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
            # log.info(f"Eligibility criteria was not met for domain: {domain}")

        response[f"{record['domain']}_{record['report_type']}"] = client_info
        return response

    def download_report(self, record, domain, report_day, report_type):
        max_tries = 3
        base_backoff_seconds = 30
        download_status = False
        # for _ in range(max_tries):
        for attempt in range(1, max_tries + 1):
            # SYSTEM DESIGN: Circuit Breaker Pattern
            if self.downloader.consecutive_failures >= 3:
                log.error("🔌 CIRCUIT BREAKER TRIPPED: 3 consecutive crashes detected.")
                log.error("Server is likely thrashing swap memory. Pausing execution for 15 minutes to allow OS to recover...")
                time.sleep(15 * 60)
                # Reset breaker state to 'Half-Open' to try again
                self.downloader.consecutive_failures = 0
                
            log.info(f"Attempt {attempt}/{max_tries} to download report for {domain}")
            
            # Download report now returns True/False
            success = self.downloader.download_report(
                record['url'], record['domain'], record['report_day'], record['report_type'],
                record['client_name'], record['client_email'], record['am_email'], record['bcc_email']
            )
                
            folder_path = os.path.join(LOCAL_PATH, domain, report_day, report_type)
            # log.info(f"Checking for file in: {folder_path}")
            if success:
                download_status = True
                # Extra safety check to ensure PDF exists before renaming
                if os.path.exists(folder_path) and any(f.endswith('.pdf') for f in os.listdir(folder_path)):
                    self.sanitize_filename(folder_path, domain, report_day, report_type)
                time.sleep(2)
                break
            else:
                self.downloader.consecutive_failures += 1
                    
                # SYSTEM DESIGN: Retry with Exponential Backoff Pattern
                if attempt < max_tries:
                    # Exponential Backoff: Wait 30s, then 60s
                    sleep_time = base_backoff_seconds * (2 ** (attempt - 1))
                    log.warning(f"Download failed for {domain}. Backing off for {sleep_time} seconds before retrying...")
                    time.sleep(sleep_time)
                else:
                    log.error(f"Failed to download report for {domain} after {max_tries} attempts.")
                
        return download_status

    def send_summary_email(self, records, response):
        # log.info(f"Recorde =  {records}")
        if records:
            s3_url = f"https://s3.amazonaws.com/{BUCKET_NAME}/cm-report/{records['domain']}/{records['report_day']}/{records['report_type']}/{file_name}"
            subject, content = self.email_service.create_admin_email_content(response, s3_url)
            admin_emails = os.getenv('ADMIN_EMAIL', "").split(",")
            status = self.email_service.send_email(subject, content, admin_emails)
            # log.info(f"Summary email sent successfully {status}")
        else:
            log.info("Summary email not sent.")

def runner_schedule():
    # runner = Runner()
    # response = {}
    # records = runner.read_csv_file()
    # for record in records:
    #     response = runner.process_record(record, response)
    #     # runner.send_summary_email(record, response.copy())
    # log.info(">>> runner_schedule TRIGGERED <<<")
    try:
        runner = Runner()
        response = {}
        records = runner.read_csv_file()
        for record in records:
            response = runner.process_record(record, response)
        log.info(">>> runner_schedule COMPLETED <<<")
    except Exception as e:
        log.error(f"runner_schedule FAILED: {e}", exc_info=True)

# def job():
#     print("I'm working...")

if __name__ == '__main__':
    # log.info("Running runner...")

    # Scheduling logic moved outside of `__main__` for clarity
    if len(sys.argv) == 3:
        runner = Runner()
        domain = sys.argv[1]
        report_type = sys.argv[2]
        record = runner.get_record_from_domain(domain, report_type)
        runner.process_record(record, {})
        # log.info(f"Processing completed for domain: {domain}")
    else:
        # schedule.every(20).seconds.do(runner_schedule)
        # schedule.every().day.at("18:30").do(runner_schedule)
        # schedule.every().day.at("14:13").do(runner_schedule)
        schedule.every().day.at("09:00").do(runner_schedule)
        # schedule.every().day.at("15:00").do(runner_schedule)
        # schedule.every().day.at("05:00").do(runner_schedule)
        # schedule.every().day.at("07:00").do(runner_schedule)
        # schedule.every().day.at("08:00").do(runner_schedule)
        # schedule.every().day.at("10:00").do(runner_schedule)
        # schedule.every().day.at("20:40").do(runner_schedule)
        while True:
            # log.info("Scheduler loop is running...")
            schedule.run_pending()
            time.sleep(1)