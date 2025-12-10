# /api/sso_auth.py
"""SSO Authentication Module - Validates Microsoft tokens and creates sessions"""

import os
import logging
import requests
from functools import wraps
from flask import request, jsonify
import jwt
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# JWT secret for internal token generation
SECRET_KEY = os.getenv("SECRET_KEY", "your-default-super-secret-key")

# Microsoft Graph API endpoint
GRAPH_API_ME_ENDPOINT = "https://graph.microsoft.com/v1.0/me"


def create_token(employee_id: str) -> str:
    """Creates a JWT token for the user."""
    payload = {
        'exp': datetime.utcnow() + timedelta(days=1),
        'iat': datetime.utcnow(),
        'sub': employee_id
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def token_required(f):
    """Decorator to protect endpoints with token authentication."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            # Expected format: "Bearer <token>"
            auth_header = request.headers['Authorization']
            if ' ' in auth_header:
                token = auth_header.split(" ")[1]
            else:
                token = auth_header

        if not token:
            return jsonify({'error': 'Token is missing!'}), 401

        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            current_user_id = data['sub']
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token has expired!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token is invalid!'}), 401

        return f(current_user_id, *args, **kwargs)

    return decorated


def verify_microsoft_token(access_token: str) -> dict:
    """
    Verify Microsoft access token by calling Graph API.
    Returns user info if valid, None if invalid.
    """
    try:
        logger.info("Verifying Microsoft token with Graph API...")
        
        # Call Microsoft Graph API to get user info
        headers = {'Authorization': f'Bearer {access_token}'}
        response = requests.get(GRAPH_API_ME_ENDPOINT, headers=headers, timeout=10)
        
        if response.status_code == 200:
            user_info = response.json()
            logger.info(f"✅ Token valid for user: {user_info.get('mail') or user_info.get('userPrincipalName')}")
            return user_info
        else:
            logger.warning(f"❌ Token validation failed: {response.status_code}")
            return None
            
    except Exception as e:
        logger.error(f"Error verifying Microsoft token: {e}", exc_info=True)
        return None


def find_employee_by_email(email: str):
    """Find employee in database by email."""
    from services import excel_handler
    
    if not email:
        return None
    
    # Try to find employee by email
    employee = excel_handler.get_employee_by_email(email)
    
    if employee:
        logger.info(f"Found employee: {employee.get('name')} ({employee.get('employee_id')})")
        return employee
    else:
        logger.warning(f"No employee found for email: {email}")
        return None
