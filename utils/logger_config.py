import os
import json
import logging
import logging.config

class JSONFormatter(logging.Formatter):
    """
    Custom formatter to convert log entries into structured JSON objects.
    Excellent for production log aggregators (ELK, Loki, Datadog).
    """
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func_name": record.funcName,
            "line_no": record.lineno
        }
        
        # Capture trace exception information if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)

def setup_logging():
    """
    Initializes standard logging. Uses structured JSON format if LOG_FORMAT=JSON
    is set in the environment variables, otherwise uses standard clean output.
    """
    log_format = os.getenv("LOG_FORMAT", "TEXT").upper()
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    # Ensure log level is valid
    level = getattr(logging, log_level, logging.INFO)
    
    # Configure handler
    handler = logging.StreamHandler()
    
    if log_format == "JSON":
        formatter = JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S")
    else:
        # User-friendly dev format
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] (%(module)s:%(lineno)d) - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        
    handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove existing handlers to avoid duplicates
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)
        
    root_logger.addHandler(handler)
    
    # Disable propagation or high-volume noise from third-party libraries if needed
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

# Initialize logging when module is imported
setup_logging()
logger = logging.getLogger("app")
logger.info("Structured logging has been configured successfully.")
