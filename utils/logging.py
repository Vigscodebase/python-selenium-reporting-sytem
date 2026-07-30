# Logging for CSPM Application is configured with the help of following class

import logging
from utils.property_reader import PropertyReader

level = logging.INFO
logging.basicConfig(
                        level=level,
                        format="%(name)s %(asctime)s %(levelname)s %(message)s",
                        handlers=[
                            logging.FileHandler("/root/docker/datastudio/datastudioreport/logs/datastudioreport.log"),
                            logging.StreamHandler()
                        ]
        )
log = logging.getLogger(__name__)
log.setLevel(level)

log.debug("Reading Property File..")
try:
    config = PropertyReader().property_file_finder('/root/docker/datastudio/datastudioreport/config/aws.properties')
    AWS_ACCESS_KEY_ID = config.get("properties","AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = config.get("properties","AWS_SECRET_ACCESS_KEY")
    INPUT_FILE_PATH = config.get("properties","INPUT_FILE_PATH")
    OUTPUT_PATH = config.get("properties","OUTPUT_PATH")
    BUCKET_NAME = config.get("properties","BUCKET_NAME")
    LOCAL_PATH = config.get("properties","LOCAL_PATH")
    REGION = config.get("properties","REGION")
except Exception as e:
    print(e)

# Read SMTP Properties
try:
    config = PropertyReader().property_file_finder('/root/docker/datastudio/datastudioreport/config/smtp.properties')
    SERVER = config.get("properties","SERVER")
    PORT = config.get("properties","PORT")
    USERNAME = config.get("properties","USERNAME")
    PASSWORD = config.get("properties","PASSWORD")
    SENDER_NAME = config.get("properties","SENDER_NAME")
    BCC = config.get("properties","BCC")
    ADMIN_EMAIL = config.get("properties","ADMIN_EMAIL")
except Exception as e:
    print(e)
