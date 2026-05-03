# accounts/handlers.py
import logging
from typing import List, Optional

# Use the shared api_client instance and models
from ..client import api_client
from ..models.account import Account, AccountSummary, Instrument, AccountID
from ..utils.decorators import track_latency, retry
from ..utils.exceptions import OandaApiError, ParseError, OandaError # Import exceptions
from ..config import settings # Access account_id if needed directly

logger = logging.getLogger(__name__)

class AccountHandler:
    """Handles interactions with OANDA Account endpoints."""

    def __init__(self, client=api_client):
        """
        Initializes the handler with an API client instance.

        Args:
            client: An instance of ApiClient (defaults to the shared instance).
        """
        if client is None:
             raise OandaError("ApiClient not available for AccountHandler. Check configuration.")
        self.client = client
        self.default_account_id = settings.account_id

    @retry() # Use default retry settings
    @track_latency
    def get_accounts(self) -> List[AccountSummary]:
        """
        Retrieves a list of accounts accessible by the API key.

        Endpoint: GET /v3/accounts

        Returns:
            A list of AccountSummary objects.

        Raises:
            OandaApiError: If the API returns an error.
            RequestError: If the HTTP request fails.
            ParseError: If the response cannot be parsed into models.
        """
        endpoint = "/v3/accounts"
        logger.info("Fetching list of accounts")
        try:
            response_data = self.client.get(endpoint)
            if 'accounts' not in response_data or not isinstance(response_data['accounts'], list):
                raise ParseError(f"Unexpected response structure for {endpoint}: 'accounts' key missing or not a list.")

            accounts = [AccountSummary.from_dict(acc_data) for acc_data in response_data['accounts']]
            logger.info(f"Successfully retrieved {len(accounts)} account(s)")
            return accounts
        except (OandaApiError, ParseError, OandaError) as e:
             logger.error(f"Failed to get accounts: {e}")
             raise # Re-raise the specific error
        except Exception as e:
             logger.exception(f"An unexpected error occurred in get_accounts: {e}")
             raise OandaError(f"Unexpected error in get_accounts: {e}") from e


    @retry()
    @track_latency
    def get_account_details(self, account_id: Optional[AccountID] = None) -> Account:
        """
        Retrieves the full details for a specific account.

        Endpoint: GET /v3/accounts/{accountID}

        Args:
            account_id: The ID of the account to retrieve. If None, uses the default from config.

        Returns:
            An Account object containing full details.

        Raises:
            OandaApiError, RequestError, ParseError, ValueError (if no account_id).
        """
        acc_id = account_id or self.default_account_id
        if not acc_id:
            raise ValueError("Account ID must be provided or set in configuration.")

        endpoint = f"/v3/accounts/{acc_id}"
        logger.info(f"Fetching details for account: {acc_id}")
        try:
            response_data = self.client.get(endpoint)
            if 'account' not in response_data or not isinstance(response_data['account'], dict):
                 raise ParseError(f"Unexpected response structure for {endpoint}: 'account' key missing or not a dict.")

            account_details = Account.from_dict(response_data['account'])
            logger.info(f"Successfully retrieved details for account: {acc_id}")
            return account_details
        except (OandaApiError, ParseError, OandaError) as e:
             logger.error(f"Failed to get account details for {acc_id}: {e}")
             raise
        except Exception as e:
             logger.exception(f"An unexpected error occurred in get_account_details: {e}")
             raise OandaError(f"Unexpected error in get_account_details: {e}") from e

    @retry()
    @track_latency
    def get_account_summary(self, account_id: Optional[AccountID] = None) -> AccountSummary:
        """
        Retrieves a summary for a specific account.

        Endpoint: GET /v3/accounts/{accountID}/summary

        Args:
            account_id: The ID of the account. Uses default if None.

        Returns:
            An AccountSummary object.
        """
        acc_id = account_id or self.default_account_id
        if not acc_id:
            raise ValueError("Account ID must be provided or set in configuration.")

        endpoint = f"/v3/accounts/{acc_id}/summary"
        logger.info(f"Fetching summary for account: {acc_id}")
        try:
            response_data = self.client.get(endpoint)
            # The summary endpoint structure might differ slightly (e.g., 'account' vs 'accountSummary')
            # Adjust key access based on actual API response observed
            summary_key = 'accountSummary' if 'accountSummary' in response_data else 'account'
            if summary_key not in response_data or not isinstance(response_data[summary_key], dict):
                 raise ParseError(f"Unexpected response structure for {endpoint}: '{summary_key}' key missing or not a dict.")

            account_summary = AccountSummary.from_dict(response_data[summary_key])
            # lastTransactionID might be in the top level, not inside the summary object itself
            if 'lastTransactionID' in response_data:
                 account_summary.lastTransactionID = response_data['lastTransactionID']

            logger.info(f"Successfully retrieved summary for account: {acc_id}")
            return account_summary
        except (OandaApiError, ParseError, OandaError) as e:
             logger.error(f"Failed to get account summary for {acc_id}: {e}")
             raise
        except Exception as e:
             logger.exception(f"An unexpected error occurred in get_account_summary: {e}")
             raise OandaError(f"Unexpected error in get_account_summary: {e}") from e

    @retry()
    @track_latency
    def get_instruments(self, account_id: Optional[AccountID] = None, instruments: Optional[List[InstrumentName]] = None) -> List[Instrument]:
        """
        Retrieves the list of tradeable instruments for an account.

        Endpoint: GET /v3/accounts/{accountID}/instruments

        Args:
            account_id: The ID of the account. Uses default if None.
            instruments: Optional list of instrument names to filter by.

        Returns:
            A list of Instrument objects.
        """
        acc_id = account_id or self.default_account_id
        if not acc_id:
            raise ValueError("Account ID must be provided or set in configuration.")

        endpoint = f"/v3/accounts/{acc_id}/instruments"
        params = {}
        if instruments:
            params['instruments'] = ",".join(instruments)

        logger.info(f"Fetching instruments for account: {acc_id}" + (f" (filtering by: {instruments})" if instruments else ""))
        try:
            response_data = self.client.get(endpoint, params=params)
            if 'instruments' not in response_data or not isinstance(response_data['instruments'], list):
                 raise ParseError(f"Unexpected response structure for {endpoint}: 'instruments' key missing or not a list.")

            instrument_list = [Instrument.from_dict(inst_data) for inst_data in response_data['instruments']]
            logger.info(f"Successfully retrieved {len(instrument_list)} instrument(s) for account: {acc_id}")
            return instrument_list
        except (OandaApiError, ParseError, OandaError) as e:
             logger.error(f"Failed to get instruments for {acc_id}: {e}")
             raise
        except Exception as e:
             logger.exception(f"An unexpected error occurred in get_instruments: {e}")
             raise OandaError(f"Unexpected error in get_instruments: {e}") from e

    # --- PATCH /v3/accounts/{accountID}/configuration ---
    @retry()
    @track_latency
    def configure_account(self, configuration: dict, account_id: Optional[AccountID] = None) -> dict:
         """
         Sets client-configurable portions of an account.

         Endpoint: PATCH /v3/accounts/{accountID}/configuration

         Args:
             configuration: A dict containing 'alias' and/or 'marginRate' to update.
             account_id: The ID of the account. Uses default if None.

         Returns:
             The raw response dictionary from the API upon success (usually contains the transaction details).
         """
         acc_id = account_id or self.default_account_id
         if not acc_id:
             raise ValueError("Account ID must be provided or set in configuration.")
         if not configuration or not isinstance(configuration, dict):
             raise ValueError("Configuration dictionary must be provided.")

         endpoint = f"/v3/accounts/{acc_id}/configuration"
         logger.info(f"Configuring account {acc_id} with: {configuration}")
         try:
             response_data = self.client.patch(endpoint, data=configuration)
             logger.info(f"Successfully configured account {acc_id}. Transaction ID: {response_data.get('clientConfigureTransaction', {}).get('id')}")
             return response_data # Return the transaction info
         except (OandaApiError, OandaError) as e:
             logger.error(f"Failed to configure account {acc_id}: {e}")
             raise
         except Exception as e:
             logger.exception(f"An unexpected error occurred in configure_account: {e}")
             raise OandaError(f"Unexpected error in configure_account: {e}") from e

    # Add get_account_changes (/v3/accounts/{accountID}/changes) later if needed


# --- Optional: Create an instance for easy import ---
# This follows the pattern of client.py, making it simple to use
# from oanda_sdk.accounts import account_handler
# summary = account_handler.get_account_summary()
if api_client:
     account_handler = AccountHandler(api_client)
else:
     account_handler = None
     logger.warning("AccountHandler could not be instantiated due to missing ApiClient.")