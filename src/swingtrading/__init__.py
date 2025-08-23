"""SwingTrading Scanner - Production-ready market scanner for swing trading opportunities."""

__version__ = "1.0.0"

import logging

# Set default logging to WARNING for library
# Application code can override this
logging.getLogger(__name__).addHandler(logging.NullHandler())