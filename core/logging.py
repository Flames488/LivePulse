
import logging, json
import structlog
logging.basicConfig(level=logging.INFO)
structlog.configure(processors=[structlog.processors.JSONRenderer()])
logger=structlog.get_logger()
