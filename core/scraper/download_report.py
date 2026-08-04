import logging
import time
import datetime
import os
import boto3
import smtplib
import shutil
import re
import socket
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


def check_internet_connection(timeout=5):
    """Checks if the VPS has active internet connectivity."""
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=timeout)
        return True
    except (OSError, socket.error):
        return False


def wait_for_internet(retry_delay=300):
    """If internet is disconnected, loops every 5 minutes until connection is restored."""
    while not check_internet_connection():
        log.warning("⚠️ Internet connection lost on VPS! Pausing for 5 minutes (300s) before retrying...")
        time.sleep(retry_delay)
    log.info("🌐 Internet connection verified.")


class ReportDownloader:
    def __init__(self):
        self.s3_client = boto3.client('s3', region_name=REGION)
        self.driver = None
        self.email_service = EmailService()
        self.processed_domains = set() 
        
        self.email_counter = 0
        self.delete_counter = 0
        self.SLEEP_SECONDS = 10 * 60  
        self.consecutive_failures = 0

    def setup_driver(self, domain, download_dir):
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)

        edge_options = EdgeOptions()
        edge_options.use_chromium = True
        
        edge_options.add_argument("--headless=new")
        edge_options.add_argument("--no-sandbox")
        edge_options.add_argument("--disable-gpu")
        edge_options.add_argument("--disable-dev-shm-usage") 
        edge_options.add_argument("--disable-software-rasterizer")
        edge_options.add_argument("--disable-extensions")
        edge_options.add_argument("--disable-infobars")
        edge_options.add_argument("--disable-browser-side-navigation")
        edge_options.add_argument("--js-flags=--max-old-space-size=512")
        edge_options.add_argument("--window-size=1920,1080")

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
        self.driver = webdriver.Edge(service=edge_service, options=edge_options)

    def wait_for_download(self, download_path, timeout=DOWNLOAD_TIMEOUT):
        log.info(f"Waiting for download in {download_path}...")
        start_time = time.time()

        if not os.path.exists(download_path):
            try:
                os.makedirs(download_path, exist_ok=True)
            except Exception as e:    
                log.error(f"Failed to create directory {download_path}: {e}")
                return None
        
        while time.time() - start_time < timeout:
            wait_for_internet() 
            files = [f for f in os.listdir(download_path) if f.endswith('.pdf') and not f.endswith('.crdownload')]
            if files:
                log.info(f"Download detected: {files[0]}")
                return os.path.join(download_path, files[0])
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
            log.info(f"WAIT SUCCESS → {label} (took {round(time.time() - start, 2)}s)")
            return element
        except TimeoutException:
            log.error(f"WAIT TIMEOUT → {label} after {timeout}s")
            raise
    
    def get_total_pages(self, timeout=30):
        page_info = WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, "//span[contains(text(), 'Page')]"))
        )
        text = page_info.text.strip()
        match = re.search(r'of\s+(\d+)', text)
        if not match:
            raise Exception(f"Unable to extract page count from text: {text}")
        return int(match.group(1))
        
    def get_current_page_number(self):
        """Extracts the current page number the browser is looking at."""
        try:
            page_info = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//span[contains(text(), 'Page')]"))
            )
            text = page_info.text.strip()      
            match = re.search(r'Page\s+(\d+)', text)
            if match:
                return int(match.group(1))
        except Exception:
            pass
        return 1
    
    def slow_scroll_page(self, pause=0.5):
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        current = 0
        viewport = self.driver.execute_script("return window.innerHeight")
        
        while current < last_height:
            self.driver.execute_script(f"window.scrollTo(0, {current});")
            time.sleep(pause)
            current += viewport
            last_height = self.driver.execute_script("return document.body.scrollHeight")    

    def slow_scroll_page_reverse(self, pause=0.5):
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        viewport = self.driver.execute_script("return window.innerHeight")
        current = last_height
        
        while current > 0:
            self.driver.execute_script(f"window.scrollTo(0, {current});")
            time.sleep(pause)
            current -= viewport

    def wait_for_page_charts_to_load(self, max_wait=45):
        """Scrolls page to trigger lazy load and waits for Looker Studio skeletons to clear."""
        # 1. Scroll down to trigger off-screen charts
        self.slow_scroll_page(pause=0.5)
        
        # 2. Dynamically wait for Looker Studio's specific grey skeleton placeholders to disappear
        start_time = time.time()
        
        # Advanced XPath: Catches Looker Studio's specific skeleton, placeholder, and busy states
        skeleton_xpath = (
            "//*["
            "contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'loading') or "
            "contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'spinner') or "
            "contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'skeleton') or "
            "contains(translate(@class, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'placeholder') or "
            "@aria-busy='true'"
            "]"
        )
        
        while time.time() - start_time < max_wait:
            try:
                loaders = self.driver.find_elements(By.XPATH, skeleton_xpath)
                
                # Filter to only count skeletons that are actually physically visible on the screen
                visible_loaders = [s for s in loaders if s.is_displayed()]
                
                if not visible_loaders:
                    log.info("Charts and skeletons fully rendered on current page.")
                    break
                else:
                    log.info(f"Waiting on {len(visible_loaders)} skeleton(s) to finish rendering...")
            except Exception:
                break
            time.sleep(2)
        
        # Buffer to allow the final SVG/Canvas to visually paint after the skeleton disappears
        time.sleep(5)
        
    def check_for_quota_errors(self):
        """Scans the rendered DOM for Looker Studio/GA4 API quota exhaustion messages."""
        error_keywords = [
            "Exhausted concurrent request",
            "Quota exceeded",
            "Too many tokens used",
            "too many requests in the last hour",
            "issued too many requests",
            "Data Set Configuration Error",
            "Quota Error",
            "Quota error",
        ]
        
        try:
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            for keyword in error_keywords:
                if keyword.lower() in page_text.lower():
                    log.warning(f"🚨 API Quota Hit! Detected keyword: '{keyword}'")
                    return True
            return False
        except Exception:
            return False
            
    def go_to_next_page(self, timeout=20):
        next_btn = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(@class, 'nextBtn') and not(contains(@class, 'fade'))]"))
        )
        self.driver.execute_script("arguments[0].click();", next_btn)
            
    def go_to_previous_page(self, timeout=20):
        prev_btn = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((By.XPATH, "//span[contains(@class, 'preBtn') and not(contains(@class, 'fade'))]"))
        )
        self.driver.execute_script("arguments[0].click();", prev_btn)

    def sleep_after_each(self, counter_name):
        counter_value = getattr(self, counter_name)
        sleep_minutes = int(self.SLEEP_SECONDS / 60)
        log.info(f"{counter_name} reached {counter_value}. Sleeping for {sleep_minutes} minutes...")
        time.sleep(self.SLEEP_SECONDS)

    def download_report(self, url, domain, report_day, report_type, client_name, client_email, am_email, bcc_email):
        try:
            wait_for_internet()

            today = datetime.date.today()
            current_month_year = f"{today.month:02d}-{today.year}"
            formatted_date = f"{int(report_day):02d}-{current_month_year}"
            download_dir = f"/root/data/{domain}/{formatted_date}/{report_type}"
            
            splited_client_email = client_email.split(',')
            splited_am_email = am_email.split(',')
            splited_bcc_email = bcc_email.split(',')
            
            unique_key = f"{domain}_{report_type}"
            if unique_key in self.processed_domains:
                return True

            self.setup_driver(domain, download_dir)
            
            log.info(f"Navigating to report URL for {domain}...")
            self.driver.get(url)
            WebDriverWait(self.driver, 30).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            log.info("Page loaded successfully.")
            
            total_pages = self.get_total_pages()
            log.info(f"Total pages detected: {total_pages}")
            
            # Forward Navigation with Quota Checking
            quota_retries = 0
            MAX_QUOTA_RETRIES = 3
            page = 1
            
            while page <= total_pages:
                wait_for_internet()
                log.info(f"Rendering page {page}/{total_pages}")
                
                self.wait_for_page_charts_to_load()
                
                # Check for API Quota Rate Limits
                if self.check_for_quota_errors():
                    if quota_retries >= MAX_QUOTA_RETRIES:
                        raise Exception("Max GA4 quota retries reached. Moving to next report to prevent hanging.")
                        
                    log.error(f"GA4 API Quota Exhausted! Pausing bot for 15 mins (Attempt {quota_retries + 1}/{MAX_QUOTA_RETRIES})...")
                    time.sleep(15 * 60) # Wait 15 minutes for tokens to refresh
                    quota_retries += 1
                    
                    log.info("Refreshing page to retry fetching data...")
                    self.driver.refresh()
                    time.sleep(15)
                    
                    # Fast-forward back to the correct page if refresh resetted Looker Studio to Page 1
                    current_page = self.get_current_page_number()
                    while current_page < page:
                        log.info(f"Fast-forwarding to catch up to page {page}...")
                        self.go_to_next_page()
                        time.sleep(3)
                        current_page = self.get_current_page_number()
                        
                    continue # Restart the rendering process for this exact same page
                
                # Reset quota retries if page loads perfectly
                quota_retries = 0 
                
                if page < total_pages:
                    self.go_to_next_page()
                    time.sleep(5)
                
                page += 1
                    
            # Backward Navigation & Verification
            log.info("Starting backward navigation and reverse scrolling...")
            for page in range(total_pages, 0, -1):
                wait_for_internet()
                log.info(f"Reverse rendering page {page}/{total_pages}")
                self.slow_scroll_page_reverse(pause=0.5)
                time.sleep(3)
                
                if page > 1:
                    self.go_to_previous_page()
                    time.sleep(5) 

            log.info("FULL BI-DIRECTIONAL RENDER COMPLETE")
            
            # Trigger Download Process
            dropdown_button = self.wait_clickable(
                "//button[contains(@aria-label, 'More options')]",
                60,
                "More options dropdown"
            )
            self.driver.execute_script("arguments[0].click();", dropdown_button)
            time.sleep(10)

            download_button = self.wait_clickable(
                "//button[contains(@class, 'share-dl-button')]",
                40,
                "Download report button"
            )
            self.driver.execute_script("arguments[0].click();", download_button)
            time.sleep(15)

            final_download_button = self.wait_clickable(
                "//button[contains(text(), 'Download')]",
                60,
                "Final download confirmation"
            )
            self.driver.execute_script("arguments[0].click();", final_download_button)

            downloaded_file = self.wait_for_download(f"/root/data/{domain}/{formatted_date}/{report_type}")
            
            if downloaded_file:
                log.info("Downloaded successfully in local directory.")
                wait_for_internet()
                
                s3_url = self.upload_to_s3(downloaded_file, domain, report_day, report_type)
                file_name = os.path.basename(downloaded_file)
                
                subject, content = self.email_service.create_client_email_content(domain, client_name, url, report_day, report_type, s3_url)
                self.email_service.send_email(subject, content, splited_client_email, ccs=splited_am_email, bcc=splited_bcc_email, file_name=file_name, attachment=downloaded_file)
                
                self.email_counter += 1
                self.sleep_after_each("email_counter")

                self.processed_domains.add(unique_key)
                
                try:
                    domain_folder_to_delete = f"/root/data/{domain}"
                    if os.path.exists(domain_folder_to_delete):
                        shutil.rmtree(domain_folder_to_delete)
                        log.info(f"Deleted domain folder: {domain_folder_to_delete}")
                except Exception as e: 
                    log.error(f"Error deleting domain folder: {e}")   
                    
                self.consecutive_failures = 0
                return True
            else:
                raise Exception("Download timed out or failed.")

        except Exception as e:
            log.error(f"Error during download for {domain}: {str(e)}", exc_info=True)
            return False
        finally:
            if self.driver:
                try:
                    self.driver.quit()
                except Exception as e:
                    log.error(f"Error closing WebDriver: {str(e)}")
                finally:
                    self.driver = None
            
            if hasattr(self, 'temp_user_data') and os.path.exists(self.temp_user_data):
                try:
                    shutil.rmtree(self.temp_user_data, ignore_errors=True)
                except Exception as e:
                    log.error(f"Failed to clear cache: {e}")

    def upload_to_s3(self, downloaded_file, domain, report_day, report_type):
        try:
            today = datetime.date.today()
            current_month_year = f"{today.month:02d}-{today.year}"
            formatted_date = f"{int(report_day):02d}-{current_month_year}"

            file_name = os.path.basename(downloaded_file)
            s3_path = f"cm-report/{domain}/{formatted_date}/{report_type}/{file_name}"

            self.s3_client.upload_file(downloaded_file, BUCKET_NAME, s3_path)
            return self.generate_s3_url(domain, formatted_date, report_type, file_name)
        except Exception as e:
            log.error(f"Upload failed: {str(e)}")
            raise e

    def generate_s3_url(self, domain, report_day, report_type, file_name):
        return f"https://s3.amazonaws.com/{BUCKET_NAME}/cm-report/{domain}/{report_day}/{report_type}/{file_name}"