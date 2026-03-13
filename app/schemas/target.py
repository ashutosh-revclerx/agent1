import ipaddress
import re
from typing import Optional, Dict
from pydantic import BaseModel, field_validator

# ── Reserved labels ────────────────────────────────────────────────────────────
# These are always set by the system in _regenerate_targets_file().
# Users must never be allowed to set them — doing so would let one tenant
# poison another tenant's metrics or spoof system metadata.

RESERVED_LABELS = {"user_id", "job", "name", "__address__", "__scheme__"}

# ── SSRF blocklist ─────────────────────────────────────────────────────────────
# Private, loopback, link-local, and cloud metadata ranges that should never
# be scraped by user-supplied targets.

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("10.0.0.0/8"),        # private class A
    ipaddress.ip_network("172.16.0.0/12"),     # private class B
    ipaddress.ip_network("192.168.0.0/16"),    # private class C
    ipaddress.ip_network("169.254.0.0/16"),    # link-local / AWS metadata
    ipaddress.ip_network("100.64.0.0/10"),     # shared address space
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]

# Blocked hostnames regardless of resolution
_BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",   # AWS/GCP/Azure metadata IP (also caught by network block)
}

# ── Hostname regex ─────────────────────────────────────────────────────────────
# RFC 1123 hostnames: letters, digits, hyphens, dots.  No underscores, no
# path components, no scheme, no query strings.
_HOSTNAME_RE = re.compile(
    r'^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)*'
    r'[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$'
)

# ── Label key regex ────────────────────────────────────────────────────────────
_LABEL_KEY_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

MAX_LABEL_KEYS = 10
MAX_LABEL_KEY_LEN = 64
MAX_LABEL_VALUE_LEN = 256


def _is_ip_blocked(host: str) -> bool:
    """Return True if host resolves to a blocked network range."""
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _BLOCKED_NETWORKS)
    except ValueError:
        # Not a bare IP — hostname; we can only check the static blocklist
        return False


class Target(BaseModel):
    name: str = "My Server"
    endpoint: str   # "host:port" — validated below
    labels: Optional[Dict[str, str]] = None
    enabled: bool = True

    @field_validator("endpoint")
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        if not v or not isinstance(v, str):
            raise ValueError("Endpoint must be a non-empty string")

        # Reject anything that looks like a URL scheme
        if "://" in v:
            raise ValueError(
                "Endpoint must be host:port only — no scheme (http://, file://, etc.)"
            )

        # Reject path traversal, query strings, fragments
        for forbidden in ("/", "?", "#", "@"):
            if forbidden in v:
                raise ValueError(
                    f"Endpoint must be host:port only — "
                    f"'{forbidden}' is not allowed"
                )

        if ":" not in v:
            raise ValueError(
                "Endpoint must include port (e.g., 192.168.1.5:9100 or myhost.example.com:9100)"
            )

        host, port_str = v.rsplit(":", 1)

        # ── Port ──────────────────────────────────────────────────────────────
        try:
            port = int(port_str)
        except ValueError:
            raise ValueError(f"Invalid port number: {port_str!r}")
        if not (1 <= port <= 65535):
            raise ValueError("Port must be between 1 and 65535")

        # ── Host: empty check ─────────────────────────────────────────────────
        if not host:
            raise ValueError("Host cannot be empty")

        # ── Host: blocked hostname list ───────────────────────────────────────
        if host.lower() in _BLOCKED_HOSTNAMES:
            raise ValueError(
                f"Endpoint host {host!r} is not permitted as a scrape target"
            )

        # ── Host: try to parse as IP first ────────────────────────────────────
        try:
            # Strip IPv6 brackets if present: [::1]
            bare = host.strip("[]")
            if _is_ip_blocked(bare):
                raise ValueError(
                    f"Endpoint {host!r} resolves to a private/internal address "
                    "and cannot be used as a scrape target"
                )
        except ValueError as e:
            # Re-raise our own ValueError; ignore ipaddress parse errors
            if "private/internal" in str(e) or "not permitted" in str(e):
                raise
            # Not an IP — validate as hostname
            if not _HOSTNAME_RE.match(host):
                raise ValueError(
                    f"Invalid hostname {host!r}. "
                    "Only alphanumeric characters, hyphens, and dots are allowed."
                )

        return v

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, v: Optional[Dict[str, str]]) -> Optional[Dict[str, str]]:
        if v is None:
            return v

        if len(v) > MAX_LABEL_KEYS:
            raise ValueError(f"labels may contain at most {MAX_LABEL_KEYS} keys")

        for key, value in v.items():
            # Reserved label check
            if key in RESERVED_LABELS or key.startswith("__"):
                raise ValueError(
                    f"Label key {key!r} is reserved and cannot be set by the user"
                )

            # Key format
            if not _LABEL_KEY_RE.match(key):
                raise ValueError(
                    f"Label key {key!r} is invalid. "
                    "Keys must start with a letter or underscore and contain only "
                    "alphanumeric characters and underscores."
                )
            if len(key) > MAX_LABEL_KEY_LEN:
                raise ValueError(
                    f"Label key {key!r} exceeds {MAX_LABEL_KEY_LEN} characters"
                )

            # Value
            if not isinstance(value, str):
                raise ValueError(f"Label value for {key!r} must be a string")
            if len(value) > MAX_LABEL_VALUE_LEN:
                raise ValueError(
                    f"Label value for {key!r} exceeds {MAX_LABEL_VALUE_LEN} characters"
                )

        return v