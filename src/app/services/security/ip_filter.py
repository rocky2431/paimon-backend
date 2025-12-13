"""IP filtering service for whitelist/blacklist management."""

import ipaddress
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class IPFilterConfig(BaseModel):
    """IP filter configuration."""

    enabled: bool = Field(default=True, description="Enable IP filtering")
    mode: str = Field(default="whitelist", description="Mode: whitelist or blacklist")
    allow_private: bool = Field(default=True, description="Allow private IPs")
    allow_localhost: bool = Field(default=True, description="Allow localhost")


class IPEntry(BaseModel):
    """IP entry in whitelist/blacklist."""

    ip_or_range: str = Field(..., description="IP address or CIDR range")
    description: str = Field(default="", description="Description")
    added_at: datetime = Field(default_factory=datetime.now, description="When added")
    added_by: str = Field(default="system", description="Who added")
    expires_at: datetime | None = Field(None, description="Expiration time")


class IPFilter:
    """Service for IP-based access control."""

    def __init__(self, config: IPFilterConfig | None = None):
        """Initialize IP filter.

        Args:
            config: Filter configuration
        """
        self.config = config or IPFilterConfig()
        self._whitelist: list[IPEntry] = []
        self._blacklist: list[IPEntry] = []

    def _parse_ip(self, ip_str: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
        """Parse IP address string.

        Args:
            ip_str: IP address string

        Returns:
            IP address or None if invalid
        """
        try:
            return ipaddress.ip_address(ip_str)
        except ValueError:
            return None

    def _parse_network(self, network_str: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
        """Parse network CIDR string.

        Args:
            network_str: Network CIDR string

        Returns:
            Network or None if invalid
        """
        try:
            return ipaddress.ip_network(network_str, strict=False)
        except ValueError:
            return None

    def _is_ip_in_entry(self, ip_str: str, entry: IPEntry) -> bool:
        """Check if IP matches an entry.

        Args:
            ip_str: IP to check
            entry: Entry to check against

        Returns:
            True if matches
        """
        # Check expiration
        if entry.expires_at and entry.expires_at < datetime.now():
            return False

        ip = self._parse_ip(ip_str)
        if not ip:
            return False

        # Check if entry is a network
        if "/" in entry.ip_or_range:
            network = self._parse_network(entry.ip_or_range)
            if network:
                return ip in network

        # Check exact match
        entry_ip = self._parse_ip(entry.ip_or_range)
        if entry_ip:
            return ip == entry_ip

        return False

    def _is_private_ip(self, ip_str: str) -> bool:
        """Check if IP is private.

        Args:
            ip_str: IP address

        Returns:
            True if private
        """
        ip = self._parse_ip(ip_str)
        if not ip:
            return False
        return ip.is_private

    def _is_localhost(self, ip_str: str) -> bool:
        """Check if IP is localhost.

        Args:
            ip_str: IP address

        Returns:
            True if localhost
        """
        ip = self._parse_ip(ip_str)
        if not ip:
            return False
        return ip.is_loopback

    def is_allowed(self, ip: str) -> bool:
        """Check if IP is allowed.

        Args:
            ip: IP address to check

        Returns:
            True if allowed
        """
        if not self.config.enabled:
            return True

        # Allow localhost if configured
        if self.config.allow_localhost and self._is_localhost(ip):
            return True

        # Allow private IPs if configured
        if self.config.allow_private and self._is_private_ip(ip):
            return True

        # Check blacklist first
        for entry in self._blacklist:
            if self._is_ip_in_entry(ip, entry):
                return False

        # Check whitelist
        if self.config.mode == "whitelist":
            # In whitelist mode, IP must be in whitelist
            for entry in self._whitelist:
                if self._is_ip_in_entry(ip, entry):
                    return True
            # Not in whitelist
            return len(self._whitelist) == 0  # Allow all if whitelist is empty

        # In blacklist mode, allow if not blacklisted
        return True

    def is_blocked(self, ip: str) -> bool:
        """Check if IP is blocked.

        Args:
            ip: IP address

        Returns:
            True if blocked
        """
        return not self.is_allowed(ip)

    def add_to_whitelist(
        self,
        ip_or_range: str,
        description: str = "",
        added_by: str = "system",
        expires_at: datetime | None = None,
    ) -> bool:
        """Add IP or range to whitelist.

        Args:
            ip_or_range: IP address or CIDR range
            description: Description
            added_by: Who added it
            expires_at: Optional expiration

        Returns:
            True if added successfully
        """
        # Validate IP/range
        if "/" in ip_or_range:
            if not self._parse_network(ip_or_range):
                return False
        else:
            if not self._parse_ip(ip_or_range):
                return False

        entry = IPEntry(
            ip_or_range=ip_or_range,
            description=description,
            added_by=added_by,
            expires_at=expires_at,
        )
        self._whitelist.append(entry)
        return True

    def add_to_blacklist(
        self,
        ip_or_range: str,
        description: str = "",
        added_by: str = "system",
        expires_at: datetime | None = None,
    ) -> bool:
        """Add IP or range to blacklist.

        Args:
            ip_or_range: IP address or CIDR range
            description: Description
            added_by: Who added it
            expires_at: Optional expiration

        Returns:
            True if added successfully
        """
        # Validate IP/range
        if "/" in ip_or_range:
            if not self._parse_network(ip_or_range):
                return False
        else:
            if not self._parse_ip(ip_or_range):
                return False

        entry = IPEntry(
            ip_or_range=ip_or_range,
            description=description,
            added_by=added_by,
            expires_at=expires_at,
        )
        self._blacklist.append(entry)
        return True

    def remove_from_whitelist(self, ip_or_range: str) -> bool:
        """Remove from whitelist.

        Args:
            ip_or_range: IP or range to remove

        Returns:
            True if removed
        """
        original_len = len(self._whitelist)
        self._whitelist = [e for e in self._whitelist if e.ip_or_range != ip_or_range]
        return len(self._whitelist) < original_len

    def remove_from_blacklist(self, ip_or_range: str) -> bool:
        """Remove from blacklist.

        Args:
            ip_or_range: IP or range to remove

        Returns:
            True if removed
        """
        original_len = len(self._blacklist)
        self._blacklist = [e for e in self._blacklist if e.ip_or_range != ip_or_range]
        return len(self._blacklist) < original_len

    def get_whitelist(self) -> list[IPEntry]:
        """Get whitelist entries.

        Returns:
            Whitelist entries
        """
        # Filter out expired entries
        now = datetime.now()
        return [e for e in self._whitelist if not e.expires_at or e.expires_at > now]

    def get_blacklist(self) -> list[IPEntry]:
        """Get blacklist entries.

        Returns:
            Blacklist entries
        """
        # Filter out expired entries
        now = datetime.now()
        return [e for e in self._blacklist if not e.expires_at or e.expires_at > now]

    def clear_whitelist(self) -> int:
        """Clear whitelist.

        Returns:
            Number of entries cleared
        """
        count = len(self._whitelist)
        self._whitelist = []
        return count

    def clear_blacklist(self) -> int:
        """Clear blacklist.

        Returns:
            Number of entries cleared
        """
        count = len(self._blacklist)
        self._blacklist = []
        return count

    def update_config(self, config: IPFilterConfig) -> None:
        """Update configuration.

        Args:
            config: New configuration
        """
        self.config = config

    def get_stats(self) -> dict[str, Any]:
        """Get filter statistics.

        Returns:
            Statistics dict
        """
        return {
            "enabled": self.config.enabled,
            "mode": self.config.mode,
            "whitelist_count": len(self.get_whitelist()),
            "blacklist_count": len(self.get_blacklist()),
            "allow_private": self.config.allow_private,
            "allow_localhost": self.config.allow_localhost,
        }


# Singleton instance
_ip_filter: IPFilter | None = None


def get_ip_filter() -> IPFilter:
    """Get singleton IP filter instance.

    Returns:
        The IP filter
    """
    global _ip_filter
    if _ip_filter is None:
        _ip_filter = IPFilter()
    return _ip_filter
