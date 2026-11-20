"""pyvision-bot: OpenCV image automation for desktop and Android (ADB)."""

from .backends import ADBBackend, BaseBackend, DesktopBackend
from .bot import VisionBot
from .matcher import TemplateMatcher
from .models import MatchResult, ROI

__version__ = "0.1.0"

__all__ = [
    "ADBBackend",
    "BaseBackend",
    "DesktopBackend",
    "MatchResult",
    "ROI",
    "TemplateMatcher",
    "VisionBot",
    "__version__",
]
