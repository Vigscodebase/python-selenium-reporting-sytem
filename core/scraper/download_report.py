import logging
import time
import datetime
import os
import boto3
import smtplib
import shutil
import re
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
import tempfile
from selenium.common.exceptions import TimeoutException

# Import the EmailService class
from core.service.email_service import EmailService

# Set up logging configuration
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("utils")

# AWS S3 Configuration
BUCKET_NAME = 'clickmatix-report'
INPUT_FILE_PATH = 'Input/test_input_gds.csv'
REGION = 'us-east-1'
DOWNLOAD_TIMEOUT = 720

class ReportDownloader:
    def __init__(self):
        self.s3_client = boto3.client('s3', region_name=REGION)
        self.driver = None
        self.email_service = EmailService()
        self.processed_domains = set() 
        
        # NEW: counters
        self.email_counter = 0
        self.delete_counter = 0
        self.SLEEP_SECONDS = 10 * 60  # 600 seconds (10 minutes)
        # SYSTEM DESIGN: Circuit Breaker State
        self.consecutive_failures = 0

    def setup_driver(self, domain, download_dir):
        # Ensure the download directory exists for the given domain
        # download_dir = f"/root/data/{domain}"

        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
            # log.info(f"Created directory: {download_dir}")

        # edge_options.add_argument("--disable-gpu")
        # edge_options.add_argument("start-maximized")
        # edge_options.add_argument("window-size=1920x1080")
        edge_options = EdgeOptions()
        edge_options.use_chromium = True
        # edge_options.add_argument("--start-maximized")
        # edge_options.add_argument("--no-sandbox")
        # edge_options.add_argument("--headless=new")
        edge_options.add_argument("--headless")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--disable-dev-shm-usage") # Critical for Swap/OOM
        edge_options.add_argument("--disable-software-rasterizer")
        edge_options.add_argument("--disable-extensions")
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-infobars")
        edge_options.add_argument("--disable-browser-side-navigation")
        edge_options.add_argument("--disable-features=VizDisplayCompositor")
        edge_options.add_argument("--js-flags=--max-old-space-size=512") # Restrict JS memory
        edge_options.add_argument("--window-size=1920,1080")
        # unique temp directory for each run
        self.temp_user_data = tempfile.mkdtemp()
        edge_options.add_argument(f"--user-data-dir={self.temp_user_data}")

        prefs = {
            "download.default_directory": download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "safebrowsing.disable_download_protection": False
        }
        edge_options.add_experimental_option("prefs", prefs)

        edge_service = EdgeService("/usr/bin/msedgedriver")
        # edge_service = EdgeService(executable_path="/usr/bin/msedgedriver", port=33455)
        # self.driver = webdriver.Edge(service=edge_service, options=edge_options)
        # self.driver.set_page_load_timeout(300)
#         self.driver = webdriver.Remote(
#     command_executor='http://127.0.0.1:9515',  # Your running msedgedriver port
#     options=edge_options
# )
        self.driver = webdriver.Edge(service=edge_service, options=edge_options)

    def wait_for_download(self, download_path, timeout=DOWNLOAD_TIMEOUT):
        log.info(f"Waiting for download in {download_path}...")  # Log the directory being watched
        start_time = time.time()

        # Ensure the directory exists
        if not os.path.exists(download_path):
            try:
                os.makedirs(download_path, exist_ok=True)
                log.info(f"Created directory: {download_path}")
            except Exception as e:    
                log.error(f"Failed to create directory {download_path}: {e}")
                return None
        
        while time.time() - start_time < timeout:
            files = [f for f in os.listdir(download_path) if f.endswith('.pdf') and not f.endswith('.crdownload')]  # Check for completed downloads
            # log.info(f"Files Loop : {files}")
            if files:
                log.info(f"Fecthed File inside Loop : {files}")
                log.info(f"Download detected: {files[0]}")
                log.info(f"Downloaded file path: {os.path.join(download_path, files[0])}")
                return os.path.join(download_path, files[0])
            
         # Log the files currently in the directory (useful for debugging)
        log.info(f"Current files in {download_path}: {os.listdir(download_path)}")
        time.sleep(5)
        
        log.error("Download timed out.")
        return None
    
    def wait_clickable(self, xpath, timeout, label):
        log.info(f"WAIT START → {label}")
        start = time.time()
        
        try:
            element = WebDriverWait(self.driver, timeout, poll_frequency=0.5).until(
                EC.element_to_be_clickable((By.XPATH, xpath))
            )
            log.info(
                f"WAIT SUCCESS → {label} (took {round(time.time() - start, 2)}s)"
            )
            return element
        
        except TimeoutException:
            log.error(
                f"WAIT TIMEOUT → {label} after {timeout}s"
            )
            
            # Debug snapshot
            log.error(f"URL: {self.driver.current_url}")
            log.error(f"TITLE: {self.driver.title}")
            
            raise
    
    def get_total_pages(self, timeout=30):
        page_info = WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located(
                (By.XPATH, "//span[contains(text(), 'Page')]")
            )
        )
        
        text = page_info.text.strip()      # "(Page 1 of 9)"
        match = re.search(r'of\s+(\d+)', text)
        
        if not match:
            raise Exception(f"Unable to extract page count from text: {text}")
        
        return int(match.group(1))
    
    def slow_scroll_page(self, pause=0.5):
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        current = 0
        viewport = self.driver.execute_script("return window.innerHeight")
        
        while current < last_height:
            self.driver.execute_script(f"window.scrollTo(0, {current});")
            time.sleep(pause)
            
            current += viewport
            last_height = self.driver.execute_script("return document.body.scrollHeight")    
            
    def go_to_next_page(self, timeout=20):
        next_btn = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//span[contains(@class, 'nextBtn') and not(contains(@class, 'fade'))]")
            )
        )
        self.driver.execute_script("arguments[0].click();", next_btn)
        
    def slow_scroll_page_reverse(self, pause=0.5):
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        viewport = self.driver.execute_script("return window.innerHeight")
        current = last_height
        
        while current > 0:
            self.driver.execute_script(f"window.scrollTo(0, {current});")
            time.sleep(pause)
            current -= viewport
            
    def go_to_previous_page(self, timeout=20):
        prev_btn = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable(
                (By.XPATH, "//span[contains(@class, 'preBtn') and not(contains(@class, 'fade'))]")
            )
        )
        self.driver.execute_script("arguments[0].click();", prev_btn)
    
    # def sleep_every_two(self, counter_name):
    #     counter_value = getattr(self, counter_name)
        
    #     if counter_value % 2 == 0:
    #         log.info(
    #             f"{counter_name} reached {counter_value}. "
    #             f"Sleeping for 20 minutes..."
    #         )
    #         time.sleep(self.SLEEP_SECONDS)
    
    def sleep_after_each(self, counter_name):
        counter_value = getattr(self, counter_name)
        sleep_minutes = int(self.SLEEP_SECONDS / 60)
        
        log.info(
            f"{counter_name} reached {counter_value}. "
            f"Sleeping for {sleep_minutes} minutes..."
            )
        time.sleep(self.SLEEP_SECONDS)

    def download_report(self, url, domain, report_day, report_type, client_name, client_email, am_email, bcc_email):
        # log.info(f"Downloading report from {url} for domain: {domain}, report type: {report_type}")
        
        try:
            # Get the current month and year
            today = datetime.date.today()
            current_month_year = f"{today.month:02d}-{today.year}"  # MM-YYYY
            # Construct formatted date using report_day from CSV
            formatted_date = f"{int(report_day):02d}-{current_month_year}"  # DD-MM-YYYY
            download_dir = f"/root/data/{domain}/{formatted_date}/{report_type}"
            # Spliting multiple emails of To, CC & BCC
            splited_client_email = client_email.split(',')
            splited_am_email = am_email.split(',')
            splited_bcc_email = bcc_email.split(',')
            # Check if this specific domain and report type has already been processed
            unique_key = f"{domain}_{report_type}"
            if unique_key in self.processed_domains:
                return True

            self.setup_driver(domain, download_dir)  # Set up driver with domain-specific folder
            self.driver.get(url)
            WebDriverWait(self.driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            log.info("Page loaded successfully.")
            time.sleep(60)
            
            total_pages = self.get_total_pages()
            log.info(f"Total pages detected: {total_pages}")
            
            for page in range(1, total_pages + 1):
                log.info(f"Rendering page {page}/{total_pages}")
                
                # Allow charts to start loading
                time.sleep(25)
                
                # Trigger lazy load
                self.slow_scroll_page(pause=0.7)
                time.sleep(5)
                self.slow_scroll_page(pause=0.7)
                
                # Buffer for last charts
                time.sleep(10)
                
                # Move to next page except last
                if page < total_pages:
                    self.go_to_next_page()
                    time.sleep(10)
                    
                time.sleep(1)
                    
            # 🔄 BACKWARD NAVIGATION (END → START)
            log.info("Starting backward navigation and reverse scrolling")
            
            for page in range(total_pages, 0, -1):
                log.info(f"Reverse rendering page {page}/{total_pages}")
                
                time.sleep(25)
                
                # Scroll UP (bottom → top)
                self.slow_scroll_page_reverse(pause=0.7)
                time.sleep(5)
                self.slow_scroll_page_reverse(pause=0.7)
                
                time.sleep(10)
                
                if page > 1:
                    self.go_to_previous_page()
                    time.sleep(10) 
                
                time.sleep(1)                  
                    
            # dropdown_button = WebDriverWait(self.driver, 40).until(
            #     EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, 'More options')]"))
            # )
            # dropdown_button.click()
            log.info("FULL BI-DIRECTIONAL RENDER COMPLETE")
            dropdown_button = self.wait_clickable(
                "//button[contains(@aria-label, 'More options')]",
                60,
                "More options dropdown"
            )
            self.driver.execute_script("arguments[0].click();", dropdown_button)
            log.info("Clicked dropdown button successfully.")
            time.sleep(40)

            # download_button = WebDriverWait(self.driver, 40).until(
            #     EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'share-dl-button')]"))
            # )
            download_button = self.wait_clickable(
                "//button[contains(@class, 'share-dl-button')]",
                40,
                "Download report button"
            )
            self.driver.execute_script("arguments[0].click();", download_button)
            # download_button.click()
            log.info("Clicked 'Download report' button successfully.")
            time.sleep(80)

            # final_download_button = WebDriverWait(self.driver, 60).until(
            #     EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Download')]"))
            # )
            final_download_button = self.wait_clickable(
                "//button[contains(text(), 'Download')]",
                60,
                "Final download confirmation"
            )
            self.driver.execute_script("arguments[0].click();", final_download_button)
            # final_download_button.click()
            log.info("Clicked final 'Download' button successfully.")
            time.sleep(60)

            # Get the current month and year
            today = datetime.date.today()
            current_month_year = f"{today.month:02d}-{today.year}"  # MM-YYYY
            # Construct formatted date using report_day from CSV
            formatted_date = f"{int(report_day):02d}-{current_month_year}"  # DD-MM-YYYY
            # Wait for download
            downloaded_file = self.wait_for_download(f"/root/data/{domain}/{formatted_date}/{report_type}")  # Wait for download in domain-specific folder
            if downloaded_file:
                log.info("Downloaded in '/root/data/'")
                # After successful download, upload to S3
                s3_url = self.upload_to_s3(downloaded_file, domain, report_day, report_type)
                file_name = os.path.basename(downloaded_file)
                # Send email after uploading
                subject, content = self.email_service.create_client_email_content(domain, client_name, url, report_day, report_type, s3_url)
                self.email_service.send_email(subject, content, splited_client_email, ccs=splited_am_email, bcc=splited_bcc_email, file_name=file_name, attachment=downloaded_file )
                
                # NEW: email throttling
                self.email_counter += 1
                log.info(f"Email sent count: {self.email_counter}")
                self.sleep_after_each("email_counter")

                # Mark the specific report as processed
                self.processed_domains.add(unique_key)  # Add unique key to processed list
                # self.driver.quit()
                # Delete domain folder after processing
                try:
                    domain_folder_to_delete = f"/root/data/{domain}"
                    if os.path.exists(domain_folder_to_delete):
                        shutil.rmtree(domain_folder_to_delete)
                        log.info(f"Deleted domain folder and all contents: {domain_folder_to_delete}")
                        
                        # NEW: delete throttling
                        # self.delete_counter += 1
                        # log.info(f"Folder delete count: {self.delete_counter}")
                        # self.sleep_every_two("delete_counter")
                        
                    else:
                        log.warning(f"Domain folder not found for deletion: {domain_folder_to_delete}")    
                except Exception as e: 
                    log.error(f"Error deleting domain folder {domain_folder_to_delete}: {e}")   
                    
                # Reset consecutive failures on success
                self.consecutive_failures = 0
                return True
            
            else:
                raise Exception("Download timed out or failed.")

        except Exception as e:
            log.error(f"Error during download for {domain}: {str(e)}", exc_info=True)
            return False # Explicitly return False so Runner knows it failed
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception as e:
                    log.error(f"Error closing WebDriver: {str(e)}")
                finally:
                    # THE FIX: Nullify the driver so skipped domains don't trigger Connection Refused
                    self.driver = None
            
            if hasattr(self, 'temp_user_data') and os.path.exists(self.temp_user_data):
                try:
                    shutil.rmtree(self.temp_user_data, ignore_errors=True)
                    log.info(f"Cleared temp browser cache: {self.temp_user_data}")
                except Exception as e:
                    log.error(f"Failed to clear cache: {e}")

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
            # log.info(f"Uploaded {file_name} to s3://{BUCKET_NAME}/{s3_path}")

            # Generate the correct S3 URL
            s3_url = self.generate_s3_url(domain, formatted_date, report_type, file_name)
            # log.info(f"Generated S3 URL: {s3_url}")
            
            # log.info(f"Downloaded file = {downloaded_file}")
            # os.remove(downloaded_file)  # Cleanup
            return s3_url
        except Exception as e:
            log.error(f"Upload failed: {str(e)}")

    def generate_s3_url(self, domain, report_day, report_type, file_name):
        # Generate the S3 URL in the format: https://s3.amazonaws.com/clickmatix-report/cm-report/{domain}/{report_day}/{report_type}/{file_name}
        s3_url = f"https://s3.amazonaws.com/{BUCKET_NAME}/cm-report/{domain}/{report_day}/{report_type}/{file_name}"
        return s3_url