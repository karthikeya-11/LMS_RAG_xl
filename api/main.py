# /api/main.py

import os
import sys
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agent.agent_graph import get_graph_app
from services import excel_handler
from api.auth import create_token, token_required
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

# --- Initialization ---
load_dotenv()
app = Flask(__name__)
CORS(app)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger('werkzeug')
# Reduce default Flask logging to make custom logs more visible
log.setLevel(logging.WARNING) 

# In-memory storage for conversation histories.
# For production, replace this with a persistent store like Redis.
memory = MemorySaver()

# The graph is compiled here, *after* the checkpointer is attached.
# This is the correct way to implement conversation memory.
app_builder = get_graph_app()
leave_agent_graph = app_builder.compile(checkpointer=memory)

# --- API Endpoints ---

@app.route("/")
def index():
    return "tech.at.core - Leave Management System API is operational."

@app.route("/api/login", methods=["POST"])
def login():
    """Authenticates user and returns a token and user info."""
    data = request.json
    employee_id = data.get("employee_id")
    password = data.get("password")
    
    if not excel_handler.verify_credentials(employee_id, password):
        return jsonify({"error": "Invalid credentials"}), 401
    
    token = create_token(employee_id)
    employee_info = excel_handler.get_employee_data(employee_id)
    
    return jsonify({
        "message": "Login successful", 
        "token": token,
        "employee_name": employee_info.get("name", "Employee"),
        "employee_id": employee_id
    }), 200

@app.route("/api/chat", methods=["POST"])
@token_required
def chat(current_user_id):
    """Main endpoint for the LangGraph agent, with correct state management."""
    data = request.json
    message_text = data.get("message")
    
    if not message_text:
        return jsonify({"error": "Message text is required"}), 400

    # The 'configurable' dict provides a unique ID for the conversation thread.
    # The checkpointer uses this to save/load the correct history.
    config = {"configurable": {"thread_id": current_user_id}}
    
    # The input to the graph is the new user message.
    graph_input = {"messages": [HumanMessage(content=message_text)]}

    try:
        final_state = None
        # The stream method now works correctly with the compiled graph.
        for chunk in leave_agent_graph.stream(graph_input, config, stream_mode="values"):
            final_state = chunk
        
        # The final state contains the complete, updated message history.
        return jsonify({
            "full_history": [msg.dict() for msg in final_state['messages']],
            "success": True
        })
        
    except Exception as e:
        app.logger.error(f"Error in /api/chat for user {current_user_id}: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred.", "details": str(e)}), 500

if __name__ == "__main__":
    # Running with debug=True provides better error logs and auto-reloading.
    # It will also print the running URL to the console.
    print("Starting Flask server at http://127.0.0.1:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
