"""Supabase client helper - centralised factory for the Supabase client."""

import os
from typing import Optional

from supabase import Client, create_client

_client: Optional[Client] = None


def get_supabase_client() -> Client:
    """Return a shared Supabase client instance.

    The client is created lazily on first call and reused afterwards.
    Connection parameters are read from environment variables:
        - SUPABASE_URL
        - SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY)

    Returns:
        A ``supabase.Client`` instance.

    Raises:
        ValueError: If required environment variables are missing.
    """
    global _client
    if _client is not None:
        return _client

    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY", "")

    if not url or not key:
        raise ValueError(
            "SUPABASE_URL and SUPABASE_KEY (or SUPABASE_SERVICE_ROLE_KEY) "
            "must be set as environment variables."
        )

    _client = create_client(url, key)
    return _client
