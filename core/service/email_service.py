import smtplib
from email.mime.text import MIMEText
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
import logging
from datetime import date, timedelta
import boto3
from botocore.exceptions import NoCredentialsError
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("utils")

SENDER_NAME = "Clickmatix Report"
SERVER = "smtp.gmail.com"
PORT = "587"
SERVER = "smtp.gmail.com"
USERNAME = "reports@clickmatix.com.au"
PASSWORD = "fzpmxlcqzophyjki"

class EmailService:

    @staticmethod
    def get_date_range(today):
        this_month = today.strftime("%b'%y")
        last_month = (today.replace(day=1) - timedelta(days=1)).strftime("%b'%y")
        return f"{last_month} - {this_month}"

    def send_email(self, subject, content, email_to, ccs=[], bcc=[], file_name=None, attachment=None, s3_url=None):
        log.info(f"Variables for email: Subject={subject}, Content={content}, To={email_to}, CC={ccs}, BCC={bcc}, File={file_name}, Attachment={attachment}, S3 URL={s3_url}")

        sender_name = SENDER_NAME
        server = SERVER
        port = PORT
        username = USERNAME
        password = PASSWORD

        status = False

        try:
            message = MIMEMultipart()
            message.attach(MIMEText(content, "html"))

            # Handle attachment if provided
            if attachment and file_name:
                file_name = file_name.replace(" ", "")
                with open(attachment, "rb") as att:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(att.read())

                encoders.encode_base64(part)
                part.add_header("Content-Disposition", f"attachment; filename={file_name}")
                message.attach(part)

            # Add S3 URL link
            if s3_url:
                content += f'<p>Access the report here: <a href="{s3_url}">Download Report</a></p>'

            # Add recipients and subject
            message['From'] = sender_name
            message['To'] = ",".join(email_to)
            message['Subject'] = subject
            message['CC'] = ",".join(ccs)
            message['BCC'] = ",".join(bcc)

            # Connect to the SMTP server and send the email
            session = smtplib.SMTP(server, port)
            session.starttls()
            session.login(username, password)

            email_to_all = email_to + ccs + bcc
            session.sendmail(username, email_to_all, message.as_string())
            session.quit()

            log.info(f"Email successfully sent to = {email_to}")
            log.info(f"Email successfully sent to CC =  {ccs}")
            log.info(f"Email successfully sent to BCC =  {bcc}")
            status = True
        except Exception as e:
            log.error(f"Email could not be sent to {email_to}")
            log.error(e, exc_info=True)

        return status

    def create_client_email_content(self, domain, client_name, url, report_day, report_type, s3_url):
        date_range = self.get_date_range(date.today())
        subject = f"Monthly Campaign Progress Report for {domain} for {date_range}"

        if report_type == 'SEO':
            email_content = f''' 
                <p>Hello {client_name},</p>
                <p>Hope you are doing well.</p>
                <p>Here we are sharing the Campaign Performance report for the last (30 days) to give you an understanding of {domain}'s current performance.</p>

                <p>The report will help you to understand the following performance:</p>
                <ul>
                    <li>Organic users</li>
                    <li>Organic leads</li>
                    <li>Website performance in SERPs</li>
                    <li>Keywords ranking data</li>
                    <li>Google business profile performance</li>
                </ul>

                <p>Please check the report to review the campaign performance in the link below.</p>
                <p>Additionally, you can access the report directly here: <a href="{s3_url}">Download Report</a></p>
                <p>Kindly confirm receipt of these reports. I am available to discuss this monthly 
                report next week if you have any doubts or queries.</p>

                <p>Thanks</p>
            '''
        elif report_type == 'PPC':
            email_content = f''' 
                <p>Hello {client_name},</p>
                <p>Hope you are doing well.</p>
                <p>Please find below your Campaign Performance report for the last (30 days), to give you an understanding of {domain}'s current performance.</p>

                <p>The PPC report will help you to understand the following performance:</p>
                <ul>
                    <li>Clicks and Impressions</li>
                    <li>Conversion Data Overview</li>
                    <li>Cost/Conv Data (CPA)</li>
                    <li>Avg. CPC and CTR Data</li>
                    <li>Total Google Ads Budget Spent</li>
                </ul>

                <p>Please check the report to review the campaign performance in the link below.</p>
                <p>Additionally, you can access the report directly here: <a href="{s3_url}">Download Report</a></p>
                <p>Kindly confirm receipt of these reports. I am available to discuss this monthly 
                report next week if you have any doubts or queries.</p>

                <p>Thanks</p>
            '''
        return subject, email_content

    def create_admin_email_content(self, overall):
        report_date = date.today().strftime("%d-%m-%Y")
        subject = f"Clickmatix Report Delivery Summary for {report_date}"

        table = self.__generate_table(overall)

        email_content = f''' 
            <p>Hello Admin,</p>
            <p>Hope you are doing well.</p>
            <p>Here we are sharing the Campaign Performance report for the last (30 days) to give you an understanding of current performance.</p>

            <p>The report will help you to understand the following performance:</p>
            {table}

            <p>Thanks</p>
        '''
        return subject, email_content

    def __generate_table(self, overall):
        table_header = '''<table border="1">
                            <thead>
                                <tr>
                                    <td>Domain Name</td>
                                    <td>Process Status</td>
                                    <td>Message</td>
                                    <td>URL</td>
                                </tr>
                            </thead>
                            <tbody>'''

        body = ""
        for domain, details in overall.items():
            status = "<p style='color:green'>Sent</p>" if details["status"] else "<p style='color:red'>Failed</p>"
            url = details.get("url", "")

            body += f"<tr><td>{domain}</td><td>{status}</td><td>{details['message']}</td><td>{url}</td></tr>"

        table_footer = "</tbody></table>"

        return table_header + body + table_footer
