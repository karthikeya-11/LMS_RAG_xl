# Authentication (token generation/validation) 

import os
from functools import wraps
from flask import request, jsonify
import jwt
from datetime import datetime, timedelta

# In a real app, use a more secure, randomly generated secret key
SECRET_KEY = os.getenv("SECRET_KEY", "your-default-super-secret-key")

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
            token = request.headers['Authorization'].split(" ")[1]

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
