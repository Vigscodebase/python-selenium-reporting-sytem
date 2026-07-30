from utils.logging import *

import smtplib
from email.mime.text import MIMEText

class EmailUtil():
    def send_email(self,reciever_email,mail_content):
            # Reference: https://wpmailsmtp.com/gmail-less-secure-apps/#Option_2_Use_an_App_Password
            message = MIMEText(mail_content)
            message['From'] = USERNAME
            message['To'] = reciever_email
            message['Subject'] = 'Report Details'
            
            session = smtplib.SMTP(SERVER,PORT)
            session.starttls()
            session.login(USERNAME,PASSWORD)
            
            text = message.as_string()
            session.sendmail(USERNAME,reciever_email,text)
            session.quit()