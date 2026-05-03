# config.py
import os
import logging
from dotenv import load_dotenv

# --- Basic Logging Setup ---
# Consider a more robust logging config later (e.g., file output, rotation)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if not os.path.exists(dotenv_path):
    logger.warning(f".env file not found at {dotenv_path}. Using environment variables directly if set.")
load_dotenv(dotenv_path=dotenv_path)

class ConfigError(Exception):
    """Custom exception for configuration errors."""
    pass

class Config:
    """
    Handles loading and accessing OANDA API configuration settings.
    Dynamically selects credentials and URLs based on OANDA_ENV.
    """
    def __init__(self):
        self.environment = os.getenv('OANDA_ENV', 'demo').lower()
        logger.info(f"Initializing configuration for environment: {self.environment}")

        if self.environment == 'demo':
            self.api_key = os.getenv('FXPRACTICE_APIKEY')
            self.account_id = os.getenv('FXPRACTICE_ACCOUNT_ID')
            self.api_url = os.getenv('FXPRACTICE_API_URL')
            self.stream_url = os.getenv('FXPRACTICE_STREAM_URL')
        elif self.environment == 'live':
            self.api_key = os.getenv('FXTRADE_APIKEY')
            self.account_id = os.getenv('FXTRADE_ACCOUNT_ID')
            self.api_url = os.getenv('FXTRADE_API_URL')
            self.stream_url = os.getenv('FXTRADE_STREAM_URL')
        else:
            raise ConfigError(f"Invalid OANDA_ENV: '{self.environment}'. Must be 'demo' or 'live'.")

        # --- Validate Essential Settings ---
        if not self.api_key:
            raise ConfigError(f"API key not found for environment '{self.environment}'. Check your .env file or environment variables.")
        if not self.account_id:
            raise ConfigError(f"Account ID not found for environment '{self.environment}'. Check your .env file or environment variables.")
        if not self.api_url:
             raise ConfigError(f"API URL not found for environment '{self.environment}'.")
        if not self.stream_url:
             raise ConfigError(f"Stream URL not found for environment '{self.environment}'.")

        # --- Optional Settings ---
        self.datetime_format = os.getenv('DEFAULT_DATETIME_FORMAT', 'RFC3339').upper()
        if self.datetime_format not in ['RFC3339', 'UNIX']:
             logger.warning(f"Invalid DEFAULT_DATETIME_FORMAT: '{self.datetime_format}'. Using 'RFC3339'.")
             self.datetime_format = 'RFC3339'

        logger.debug(f"Config loaded: Account ID={self.account_id[:7]}..., API URL={self.api_url}") # Avoid logging full key

    def get_auth_headers(self) -> dict:
        """Returns the standard Authorization header."""
        return {'Authorization': f'Bearer {self.api_key}'}

    def get_content_headers(self) -> dict:
        """Returns standard Content-Type header for JSON POST/PUT requests."""
        return {'Content-Type': 'application/json'}

    def get_accept_datetime_format_headers(self) -> dict:
         """Returns the header to specify datetime format preference."""
         return {'Accept-Datetime-Format': self.datetime_format}

# --- Create a single instance for the application to use ---
try:
    settings = Config()
except ConfigError as e:
    logger.critical(f"Configuration Error: {e}")
    # In a real app, you might exit here or handle it differently
    settings = None # Or raise the exception