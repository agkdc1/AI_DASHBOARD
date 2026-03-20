"""Abstract base class for marketplace providers."""

from __future__ import annotations

import abc
import logging
from typing import Callable

from schema import UnifiedOrder


class BaseProvider(abc.ABC):
    """Base class every marketplace provider must inherit from.

    Parameters
    ----------
    get_setting:
        Callable that retrieves a plugin setting by key.
        Decoupled from InvenTree so providers are unit-testable.
    logger:
        Python logger instance.
    """

    PLATFORM: str = ""  # Override in subclass

    def __init__(
        self,
        get_setting: Callable[[str], str],
        logger: logging.Logger | None = None,
        set_setting: Callable[[str, str], None] | None = None,
    ) -> None:
        self.get_setting = get_setting
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.set_setting = set_setting or (lambda _k, _v: None)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abc.abstractmethod
    def authenticate(self) -> None:
        """Refresh tokens / build auth headers."""

    @abc.abstractmethod
    def fetch_orders(self) -> list[UnifiedOrder]:
        """Return orders in *marked* (ready-to-ship) status."""

    @abc.abstractmethod
    def push_tracking(self, order_id: str, tracking_number: str) -> bool:
        """Push a tracking number back to the platform.

        Returns True on success.
        """

    @abc.abstractmethod
    def get_inventory(self, sku: str) -> int | None:
        """Return current stock level for *sku* on the platform."""

    @abc.abstractmethod
    def update_inventory(self, sku: str, qty: int) -> bool:
        """Set stock level for *sku* on the platform.

        Returns True on success.
        """

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """Return True when all required credentials are present."""
        return False
