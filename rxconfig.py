"""Reflex configuration for KiteCobra."""

import os
import reflex as rx

# Get environment variables for production
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")

# Check if we're in production (Railway sets this)
IS_PRODUCTION = os.getenv("RAILWAY_ENVIRONMENT") == "production"

# For Railway deployment - use the known domain or env var
RAILWAY_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN", "kitecobra-production.up.railway.app")

# Build config based on environment
if IS_PRODUCTION:
    config = rx.Config(
        app_name="kitecobra",
        db_url="sqlite:///kitecobra.db",
        backend_host=BACKEND_HOST,
        api_url=f"https://{RAILWAY_DOMAIN}",
    )
else:
    # Local development - omit api_url to let Reflex auto-detect
    config = rx.Config(
        app_name="kitecobra",
        db_url="sqlite:///kitecobra.db",
        backend_host=BACKEND_HOST,
    )
