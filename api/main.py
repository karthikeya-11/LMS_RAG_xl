# /api/main.py

import os
import sys
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Add project root to sys.path to allow for absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the NEW production-grade agent graph
from agent.agent_graph import leave_agent_graph
from services import excel_handler
from api.auth import create_token, token_required
from langchain_core.messages import HumanMessage
# Import helpers for serialization
from langchain_core.messages import messages_from_dict, messages_to_dict

# --- Initialization ---
load_dotenv()
app = Flask(__name__)
CORS(app)

# --- API Endpoints ---

@app.route("/")
def index():
    return "Tech.at.core - Leave Management System API is operational."

@app.route("/api/login", methods=["POST"])
def login():
    """Authenticates user and returns a token."""
    data = request.json
    employee_id = data.get("employee_id")
    password = data.get("password")
    
    if not excel_handler.verify_credentials(employee_id, password):
        return jsonify({"error": "Invalid credentials"}), 401
    
    token = create_token(employee_id)
    employee_info = excel_handler.get_employee_data(employee_id)
    employee_name = employee_info.get("name", "Employee") if employee_info else "Employee"
    
    return jsonify({
        "message": "Login successful", 
        "token": token,
        "employee_name": employee_name
    }), 200

@app.route("/api/chat", methods=["POST"])
@token_required
def chat(current_user_id):
    """
    Main endpoint for the LangGraph agent. It now manages the full conversation state
    with proper serialization.
    """
    data = request.json
    message_text = data.get("message")
    session_state = data.get("session_state") 

    if not message_text:
        return jsonify({"error": "Message text is required"}), 400

    # If state is coming from the client, deserialize it back into LangChain objects.
    if session_state:
        session_state['messages'] = messages_from_dict(session_state['messages'])
    # If no state is provided, initialize a new one.
    else:
        session_state = {
            "messages": [],
            "employee_id": current_user_id,
            "employee_name": None, # Will be initialized in the graph
            "leave_request_details": {}
        }

    # Add the new human message to the message history
    session_state["messages"].append(HumanMessage(content=message_text))

    try:
        # Invoke the graph with the current session state
        final_state = leave_agent_graph.invoke(session_state)
        
        # Serialize the full state to send back to the client for the next turn.
        serializable_state = final_state.copy()
        serializable_messages = messages_to_dict(final_state['messages'])
        serializable_state['messages'] = serializable_messages

        # **THE FIX**: Add a 'history' key to the response JSON.
        # The front-end is expecting this key to be an array of messages to render.
        return jsonify({
            "response": final_state['messages'][-1].content,
            "session_state": serializable_state,
            "history": serializable_messages, # This provides the direct history for rendering
            "success": True
        })
        
    except Exception as e:
        print(f"Error in /api/chat: {e}")
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
