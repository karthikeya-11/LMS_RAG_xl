# /api/main.py

import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Add project root to sys.path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent.agent_graph import leave_agent_graph
from services import excel_handler, policy_rag
from api.auth import create_token, token_required
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

# --- Initialization ---
load_dotenv()
app = Flask(__name__)
CORS(app)

# --- API Endpoints ---

@app.route("/")
def index():
    return "Leave Management System API is operational."

@app.route("/api/login", methods=["POST"])
def login():
    """Authenticates user and returns a token."""
    data = request.json
    employee_id = data.get("employee_id")
    password = data.get("password")
    
    if not excel_handler.verify_credentials(employee_id, password):
        return jsonify({"error": "Invalid credentials"}), 401
    
    token = create_token(employee_id)
    return jsonify({"message": "Login successful", "token": token}), 200

@app.route("/api/chat", methods=["POST"])
@token_required
def chat(current_user_id):
    """
    Main endpoint for the LangGraph agent, now with stateful conversation history.
    """
    data = request.json
    message_text = data.get("message")
    history_dicts = data.get("history", [])

    if not message_text:
        return jsonify({"error": "Message text is required"}), 400

    messages: list[BaseMessage] = []
    for msg_data in history_dicts:
        role = msg_data.get("role")
        if role == "user":
            messages.append(HumanMessage(content=msg_data["content"]))
        elif role == "assistant":
            messages.append(AIMessage(content=msg_data["content"]))
    
    messages.append(HumanMessage(content=message_text))

    try:
        result = leave_agent_graph.invoke({
            "messages": messages,
            "employee_id": current_user_id
        })

        response_message = result['messages'][-1]
        
        updated_history_dicts = []
        for msg in result['messages']:
            if isinstance(msg, HumanMessage):
                updated_history_dicts.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage) and msg.content:
                updated_history_dicts.append({"role": "assistant", "content": msg.content})
        
        final_response_text = response_message.content if isinstance(response_message, AIMessage) else ""
        
        return jsonify({
            "response": final_response_text,
            "history": updated_history_dicts
        })
    except Exception as e:
        print(f"Error in /api/chat: {e}")
        return jsonify({"error": "An internal server error occurred."}), 500

# --- Debugging & Direct Access Endpoints ---

@app.route("/api/check_policy", methods=["POST"])
@token_required
def check_policy_endpoint(current_user_id):
    data = request.json
    result = policy_rag.check_policy_compliance(data.get("leave_type"), data.get("num_days"), data.get("reason"))
    return jsonify(result)

@app.route("/api/check_balance", methods=["POST"])
@token_required
def check_balance_endpoint(current_user_id):
    """
    Checks the annual leave balance for the authenticated user.
    This endpoint now correctly handles a balance of 0.
    """
    balance = excel_handler.get_annual_leave_balance(current_user_id)
    
    # THE FIX: Check if balance is not None. 0 is a valid balance.
    if balance is not None:
        # Return a proper JSON object
        return jsonify({"annual_leave_balance": balance})
    
    return jsonify({"error": "User not found"}), 404


@app.route("/api/status/<request_id>", methods=["GET"])
@token_required
def get_status_endpoint(current_user_id, request_id):
    # This assumes a get_request_status function exists in your handler
    # We will mock a simple version of it for this example
    history = excel_handler.get_leave_history(current_user_id)
    status = next((item for item in history if item["request_id"] == request_id), None)
    
    if status:
        if status['employee_id'] != current_user_id:
            return jsonify({"error": "Unauthorized"}), 403
        return jsonify(status)
    return jsonify({"error": "Request ID not found"}), 404
    
@app.route("/api/update_leave", methods=["POST"])
@token_required
def update_leave_endpoint(current_user_id):
    return jsonify({"message": "Endpoint not fully implemented. Requires manager role validation."}), 501

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)

