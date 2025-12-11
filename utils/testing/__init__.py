# Testing subpackage - Page interaction testing utilities
from .interactions import InteractionTester
from .overlays import OverlayDismisser, dismiss_overlays_before_screenshot

__all__ = [
    "InteractionTester",
    "OverlayDismisser",
    "dismiss_overlays_before_screenshot",
]
