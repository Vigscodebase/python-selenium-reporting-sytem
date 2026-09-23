from utils.logging import *
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.service import Service as ChromeService
import time
import logging as log
from time import sleep
import os
import shutil

class ReportDownloader():

    def download_report(self, url, domain, report_day, report_type):
        log.info("Downloading Report for Domain: %s; url=%s" % (domain + "_" + report_type, url))
        status = False
        try:
            timeout = 180  # Increased timeout for waiting elements (3 minutes)
            max_retries = 3  # Max retries to handle flaky elements

            path = LOCAL_PATH + domain + "/" + str(report_day) + "/" + report_type
            options = Options()
            options.add_argument("start-maximized")
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-gpu')  # Necessary for headless mode
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            prefs = {'download.default_directory': path,
                     'download.prompt_for_download': False,
                     'download.directory_upgrade': True,
                     'safebrowsing.enabled': False,
                     'safebrowsing.disable_download_protection': True}
            options.add_experimental_option("prefs", prefs)

            options.binary_location = "/usr/bin/google-chrome"
            driver_path = "/usr/local/bin/chromedriver"
            chrome_service = ChromeService(executable_path=driver_path)

            # Initialize the webdriver
            driver = webdriver.Chrome(service=chrome_service, options=options)
            driver.command_executor._commands["send_command"] = ("POST", '/session/$sessionId/chromium/send_command')
            params = {'cmd': 'Page.setDownloadBehavior', 'params': {'behavior': 'allow', 'downloadPath': path}}
            driver.execute("send_command", params)

            # Navigate to the page
            driver.get(url)
            WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CLASS_NAME, "top-page-navigation")))  # Wait until the pagination loads

            # Get Pagination information and iterate through pages
            pagination = driver.find_element(By.CLASS_NAME, "top-page-navigation")
            page_info = pagination.find_element(By.XPATH, "div/div/span[2]/span[2]").text
            total_pages = int(page_info.replace(")", "").split(" ")[-1])

            next_button = pagination.find_element(By.XPATH, "div/div/span[3]")

            for i in range(max_retries):
                try:
                    log.info(f"Attempt {i+1} of {max_retries} to click next")
                    next_button.click()  # Click next to go to the next page
                    WebDriverWait(driver, timeout).until(EC.staleness_of(next_button))  # Wait for the page to load completely
                    time.sleep(2)
                    break  # Exit loop after successful click
                except TimeoutException as e:
                    log.error(f"Timeout occurred when clicking next button (Attempt {i+1})")
                    if i == max_retries - 1:
                        raise  # Raise after max retries

            # Retry logic for waiting and clicking the share button
            for attempt in range(max_retries):
                try:
                    log.info(f"Attempt {attempt + 1} of {max_retries} to click share button")
                    button = WebDriverWait(driver, timeout).until(
                        EC.element_to_be_clickable((By.XPATH, "/html/body/app-bootstrap/ng2-bootstrap/lego-router-outlet/reporting-view-manager/ng2-reporting-view/div/div[1]/app-header/div/div/md-toolbar/div/product-tools-header/div/reporting-product-tools-header/share-button/split-button/button-group/div/button[2]"))
                    )
                    button.click()
                    break
                except TimeoutException as e:
                    if attempt == max_retries - 1:
                        log.error("Timeout occurred after max retries while waiting for the button.")
                        raise
                    log.warning(f"Attempt {attempt + 1} failed: Timeout waiting for button. Retrying...")
                    sleep(3)  # Wait for a few seconds before retrying

            WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CLASS_NAME, "cdk-overlay-container")))

            # Get the download button and click it
            item = driver.find_element(By.CLASS_NAME, "cdk-overlay-container")
            download_button = item.find_element(By.XPATH, "div/div/button[3]")
            download_button.click()

            # Wait until the dialog and click the download button
            dialog = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.TAG_NAME, "md-dialog")))
            download = dialog.find_element(By.XPATH, "md-dialog-actions/button[2]")
            download.click()

            # Wait until the download is complete (or adjust based on file size)
            time.sleep(100)  # Optionally, adjust for file download time

            # Fetch the downloaded file name
            downloaded_file = self.get_downloaded_file(path)

            # Check if the file was downloaded successfully
            if downloaded_file:
                log.info(f"File downloaded successfully: {downloaded_file}")
                status = True
            else:
                log.error("File download failed: No file found in the download folder.")
                status = False

            log.debug("Processing completed for file download from url: %s " % (url))

        except Exception as e:
            log.error(f"Error while downloading file from {url}: {str(e)}")
            log.exception(f"Exception: {e}")
            status = False
        return status

    def get_downloaded_file(self, download_path):
        """
        Returns the name of the latest downloaded file.
        It assumes the downloaded file is the latest file in the directory.
        """
        try:
            # List all files in the directory and sort by creation time
            files = os.listdir(download_path)
            files = [os.path.join(download_path, file) for file in files if os.path.isfile(os.path.join(download_path, file))]
            files.sort(key=os.path.getctime, reverse=True)

            if files:
                return files[0]  # Return the most recently downloaded file
            else:
                return None
        except Exception as e:
            log.error(f"Error while checking downloaded files: {str(e)}")
            return None

if __name__ == '__main__':
    rd = ReportDownloader()
    url = "placeholder"  # Example URL
    domain = "placeholder"
    report_day = "placeholder"
    report_type = "placeholder"
    LOCAL_PATH = "placeholder"
    rd.download_report(url, domain, report_day, report_type)
