import logging
import time
import datetime
import os
import boto3
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from botocore.exceptions import NoCredentialsError
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.edge.options import Options as EdgeOptions
import datetime
import csv

# Import the EmailService class
from core.service.email_services import EmailService

# Set up logging configuration
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("utils")

# AWS S3 Configuration
BUCKET_NAME = 'clickmatix-report'
INPUT_FILE_PATH = 'Input/input_gds.csv'
REGION = 'us-east-1'
DOWNLOAD_TIMEOUT = 180

class ReportDownloader:
    def __init__(self):
        self.s3_client = boto3.client('s3', region_name=REGION)
        self.driver = None
        self.email_service = EmailService()
        self.processed_domains = set() 

    def setup_driver(self, domain):
        # Ensure the download directory exists for the given domain
        download_dir = f"/root/data/{domain}"
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
            log.info(f"Created directory: {download_dir}")

        edge_options = EdgeOptions()
        edge_options.add_argument("--headless")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("start-maximized")
        edge_options.add_argument("window-size=1920x1080")

        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "safebrowsing.disable_download_protection": False
        }
        edge_options.add_experimental_option("prefs", prefs)

        edge_service = EdgeService(executable_path="/usr/bin/msedgedriver", port=33455)
        self.driver = webdriver.Edge(service=edge_service, options=edge_options)
        self.driver.set_page_load_timeout(180)

    def wait_for_download(self, download_path, timeout=DOWNLOAD_TIMEOUT):
        log.info(f"Waiting for download in {download_path}...")  # Log the directory being watched
        start_time = time.time()
        
        # Ensure the directory exists
        if not os.path.exists(download_path):
            log.error(f"Directory {download_path} does not exist.")
            return None
        
        while time.time() - start_time < timeout:
            files = [f for f in os.listdir(download_path) if f.endswith('.pdf') and not f.endswith('.crdownload')]  # Check for completed downloads
            if files:
                log.info(f"Download detected: {files[0]}")
                return os.path.join(download_path, files[0])
            
            # Log the files currently in the directory (useful for debugging)
            log.info(f"Current files in {download_path}: {os.listdir(download_path)}")
            time.sleep(5)
        
        log.error("Download timed out.")
        return None

    def download_report(self, url, domain, report_day, report_type, client_name, client_email, am_email):
        log.info(f"Downloading report from {url} for domain: {domain}, report type: {report_type}")
        try:
            # Check if the domain has already been processed successfully
            if domain in self.processed_domains:
                log.info(f"Skipping domain {domain} as it has already been processed.")
                return

            self.setup_driver(domain)  # Set up driver with domain-specific folder
            self.driver.get(url)
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            log.info("Page loaded successfully.")
            time.sleep(120)

            # Interaction to download the report
            dropdown_button = WebDriverWait(self.driver, 60).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'More options')]"))
            )
            dropdown_button.click()
            log.info("Clicked dropdown button successfully.")
            time.sleep(120)

            download_button = WebDriverWait(self.driver, 20).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'share-dl-button')]"))
            )
            download_button.click()
            log.info("Clicked 'Download report' button successfully.")
            time.sleep(60)

            final_download_button = WebDriverWait(self.driver, 60).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Download')]"))
            )
            final_download_button.click()
            log.info("Clicked final 'Download' button successfully.")

            # Wait for download
            downloaded_file = self.wait_for_download(f"/root/data/{domain}")  # Wait for download in domain-specific folder
            if downloaded_file:
                # After successful download, upload to S3
                s3_url = self.upload_to_s3(downloaded_file, domain, report_day, report_type)

                # Send email after uploading
                subject, content = self.email_service.create_client_email_content(domain, client_name, url, report_day, report_type, s3_url)
                self.email_service.send_email(subject, content, [client_email], ccs=[am_email])

                # Mark the domain as processed
                self.processed_domains.add(domain)  # Add domain to processed list

        except Exception as e:
            log.error(f"Error during download: {str(e)}", exc_info=True)
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception as e:
                    log.error(f"Error closing WebDriver: {str(e)}")

    def upload_to_s3(self, downloaded_file, domain, report_day, report_type):
        try:
            # Get the current month and year
            today = datetime.date.today()
            current_month_year = f"{today.month:02d}-{today.year}"  # MM-YYYY

            # Construct formatted date using report_day from CSV
            formatted_date = f"{int(report_day):02d}-{current_month_year}"  # DD-MM-YYYY

            # Construct S3 path
            file_name = os.path.basename(downloaded_file)
            s3_path = f"cm-report/{domain}/{formatted_date}/{report_type}/{file_name}"

            # Upload the file to S3
            self.s3_client.upload_file(downloaded_file, BUCKET_NAME, s3_path)
            log.info(f"Uploaded {file_name} to s3://{BUCKET_NAME}/{s3_path}")

            # Generate the correct S3 URL
            s3_url = self.generate_s3_url(domain, formatted_date, report_type, file_name)
            log.info(f"Generated S3 URL: {s3_url}")

            os.remove(downloaded_file)  # Cleanup
            return s3_url
        except Exception as e:
            log.error(f"Upload failed: {str(e)}")

    def generate_s3_url(self, domain, report_day, report_type, file_name):
        # Generate the S3 URL in the format: https://s3.amazonaws.com/clickmatix-report/cm-report/{domain}/{report_day}/{report_type}/{file_name}
        s3_url = f"https://s3.amazonaws.com/{BUCKET_NAME}/cm-report/{domain}/{report_day}/{report_type}/{file_name}"
        return s3_url