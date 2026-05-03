# models/base.py
from dataclasses import dataclass, field
from typing import List, Optional, Union, Dict, Any
import logging

logger = logging.getLogger(__name__)

# --- Common Type Aliases (improve readability) ---
InstrumentName = str
AccountID = str
OrderID = str
TradeID = str
TransactionID = str
DateTime = str # OANDA typically uses RFC3339 string format
DecimalNumber = str # OANDA uses strings for precise decimal numbers
Integer = int # Standard integer
Boolean = bool

# --- Base Class (Optional - useful if common parsing logic is needed) ---
@dataclass
class OandaDataModel:
    """Base class for OANDA data models, potentially adding helper methods later."""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """
        Basic factory method to create an instance from a dictionary.
        Assumes dictionary keys match dataclass fields.
        More robust parsing might be needed for nested or complex types.
        """
        # Basic implementation - needs enhancement for nested types, type coercion etc.
        try:
            # This basic version relies on dataclass __init__ handling matching keys.
            # It won't automatically handle nested dataclasses or complex type conversions.
            # Consider libraries like 'dacite' or 'mashumaro' for more complex cases,
            # or implement custom __init__ or factory methods in specific models.
            field_names = {f.name for f in cls.__dataclass_fields__.values()}
            filtered_data = {k: v for k, v in data.items() if k in field_names}
            return cls(**filtered_data)
        except TypeError as e:
             logger.error(f"Error creating {cls.__name__} from dict: {e}. Data: {data}")
             # Depending on desired strictness, you might raise an error or return None/partial object
             raise ParseError(f"Failed to instantiate {cls.__name__} from dictionary: {e}") from e

    def to_dict(self) -> Dict[str, Any]:
         """Converts the dataclass instance to a dictionary."""
         from dataclasses import asdict
         return asdict(self)

# Example: Add more common types or base structures as needed.