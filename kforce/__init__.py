import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)
BOTO_LOGGER_NAME = 'botocore'
logging.getLogger(BOTO_LOGGER_NAME).setLevel(logging.CRITICAL)  # boto logging is annony and too verbose


def init_logger(debug=False):
    if debug is True:
        logger.setLevel(logging.DEBUG)
        logging.getLogger(BOTO_LOGGER_NAME).setLevel(logging.DEBUG)
