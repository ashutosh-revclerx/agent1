import os
import firebase_admin
from firebase_admin import credentials, auth
from app.core.logging import logger

def initialize_firebase():
    """Initialize Firebase Admin SDK"""
    try:
        # Check if already initialized
        firebase_admin.get_app()
        return
    except ValueError:
        pass

    project_id = os.getenv("FIREBASE_PROJECT_ID")
    key_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH")

    if not project_id:
        logger.warning("[Firebase] FIREBASE_PROJECT_ID not set, skipping initialization")
        return

    try:
        if key_path and os.path.exists(key_path):
            cred = credentials.Certificate(key_path)
            firebase_admin.initialize_app(cred)
            logger.info(f"[Firebase] Initialized with service account from {key_path}")
        else:
            # Fallback to default credentials (useful for GCP environments)
            firebase_admin.initialize_app()
            logger.info("[Firebase] Initialized with default credentials")
    except Exception as e:
        logger.error(f"[Firebase] Initialization failed: {e}")

def verify_firebase_token(id_token: str):
    """Verify Firebase ID token and return decoded claims"""
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token
    except Exception as e:
        logger.error(f"[Firebase] Token verification failed: {e}")
        return None
