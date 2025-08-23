"""Exception handling and error code mapping for SwingTrading scanner."""

from concurrent.futures import TimeoutError as FuturesTimeoutError


class DataError(Exception):
    """Raised when data is insufficient or invalid."""
    pass


class ConfigError(Exception):
    """Raised when configuration is invalid."""
    pass


# Exit codes for CLI
EXIT_SUCCESS = 0           # Successful completion
EXIT_GENERAL_ERROR = 1     # Uncaught/unexpected exceptions
EXIT_CONFIG_ERROR = 2      # Configuration validation failures
EXIT_NETWORK_ERROR = 3     # Network/API/rate limit errors
EXIT_DATA_ERROR = 4        # Insufficient data errors


class ExceptionMapper:
    """Maps exceptions to appropriate exit codes."""
    
    @staticmethod
    def map_to_exit_code(e: Exception) -> int:
        """
        Map an exception to an exit code.
        
        Args:
            e: The exception to map
            
        Returns:
            Exit code (0-4)
        """
        # Import here to avoid circular dependencies
        try:
            from alpaca.common.exceptions import APIError as AlpacaAPIError
            from alpaca.data.exceptions import NoDataAvailable
        except ImportError:
            # If Alpaca not installed, treat as general error
            AlpacaAPIError = None
            NoDataAvailable = None
        
        # Configuration errors
        if isinstance(e, ConfigError):
            return EXIT_CONFIG_ERROR
        
        # Data errors
        elif isinstance(e, DataError):
            return EXIT_DATA_ERROR
        
        # Timeout from futures (per-ticker timeout)
        elif isinstance(e, FuturesTimeoutError):
            return EXIT_NETWORK_ERROR
        
        # Alpaca API errors
        elif AlpacaAPIError and isinstance(e, AlpacaAPIError):
            if hasattr(e, 'code'):
                error_code = e.code
                
                # 422 can mean bad request OR no data
                if error_code == 422:
                    error_msg = str(e).lower()
                    if 'no data' in error_msg or 'not found' in error_msg:
                        return EXIT_DATA_ERROR
                    else:
                        return EXIT_CONFIG_ERROR
                
                # Rate limiting and server errors
                elif error_code in [429, 503, 504, 408]:
                    return EXIT_NETWORK_ERROR
                
                # Authentication and permission errors
                elif error_code in [400, 401, 403]:
                    return EXIT_CONFIG_ERROR
                
                # Other server errors
                elif error_code >= 500:
                    return EXIT_NETWORK_ERROR
            
            # Default for Alpaca errors without code
            return EXIT_NETWORK_ERROR
        
        # Alpaca no data available
        elif NoDataAvailable and isinstance(e, NoDataAvailable):
            return EXIT_DATA_ERROR
        
        # Network errors
        elif isinstance(e, (ConnectionError, TimeoutError)):
            return EXIT_NETWORK_ERROR
        
        # Value errors (often configuration related)
        elif isinstance(e, ValueError):
            error_msg = str(e)
            
            # Specific error messages
            if 'Invalid feed' in error_msg:
                return EXIT_CONFIG_ERROR
            elif 'Unexpected response shape' in error_msg:
                return EXIT_DATA_ERROR
            else:
                return EXIT_CONFIG_ERROR
        
        # Key errors (often configuration related)
        elif isinstance(e, KeyError):
            return EXIT_CONFIG_ERROR
        
        # Default to general error
        return EXIT_GENERAL_ERROR