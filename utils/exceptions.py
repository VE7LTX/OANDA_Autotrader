# utils/exceptions.py

class OandaError(Exception):
    """Base exception for all OANDA SDK related errors."""
    pass

class ConfigError(OandaError):
    """Exception raised for errors in configuration loading or validation."""
    pass

class OandaApiError(OandaError):
    """Exception raised when the OANDA API returns an error."""
    def __init__(self, status_code: int, error_response: dict, message: str = "OANDA API Error"):
        self.status_code = status_code
        self.error_response = error_response # The JSON body from OANDA
        # Try to get a more specific message from the response
        self.detail = error_response.get('errorMessage', 'No specific error message provided by API.')
        super().__init__(f"{message} (Status {status_code}): {self.detail}")

class RequestError(OandaError):
     """Exception raised for issues during the HTTP request itself (e.g., network)."""
     pass

class StreamConnectionError(OandaError):
    """Exception raised for errors related to streaming connections."""
    pass

class RateLimitError(OandaApiError):
    """Specific exception for 429 Too Many Requests errors."""
    def __init__(self, status_code: int, error_response: dict):
         super().__init__(status_code, error_response, message="API Rate Limit Exceeded")

class ParseError(OandaError):
     """Exception raised when failing to parse API response into models."""
     pass