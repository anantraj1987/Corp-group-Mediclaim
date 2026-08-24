import sys
import logging
from rich.console import Console
from rich.logging import RichHandler
from config.settings import settings

console = Console()

def setup_logger(name: str = "IncidentAgent") -> logging.Logger:
    """Configures and returns a structured rich logger instance."""
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
        
        handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            markup=True,
            show_time=True,
            show_path=False
        )
        
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger

logger = setup_logger()
