# /agent/agent_graph.py

import json
from typing import TypedDict, Annotated, Sequence, Literal
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage, HumanMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from datetime import datetime
import logging

# Import tools and the refined system prompt
from .tools import (check_leave_balance, submit_leave_request, get_company_holidays,
                    view_leave_history, answer_policy_question)
from services.excel_handler import get_employee_data
from .prompts import SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- State Definition ---
# The AgentState is the memory of our agent for a single user session.
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], lambda x, y: x + y]
    employee_id: str
    employee_name: str
    # This sub-dictionary holds the state for the multi-step leave request process.
    leave_request_details: dict

# --- LLM and Tools Configuration ---
# We use a powerful model like gpt-4o for its reasoning and function-calling capabilities.
llm = ChatOpenAI(model="gpt-4o", temperature=0)
tools = [check_leave_balance, submit_leave_request, get_company_holidays, view_leave_history, answer_policy_question]
tool_node = ToolNode(tools)

# --- Node Functions for the Graph ---

def initialize_state(state: AgentState) -> AgentState:
    """Initializes the state with employee name if it's not already present."""
    if not state.get("employee_name"):
        employee_info = get_employee_data(state["employee_id"])
        state["employee_name"] = employee_info.get('name', 'Employee') if employee_info else 'Employee'
    if "leave_request_details" not in state:
        state["leave_request_details"] = {}
    return state

def call_agent(state: AgentState):
    """The primary node that calls the LLM. It's used for general conversation and standard tool use."""
    logger.info(f"--- Calling Agent for Employee: {state['employee_id']} ---")
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="messages"),
    ])
    
    llm_with_tools = llm.bind_tools(tools)
    agent_runnable = prompt | llm_with_tools
    
    # Invoke the LLM with the current state, populating prompt variables
    response = agent_runnable.invoke({
        "messages": state["messages"],
        "employee_name": state["employee_name"],
        "employee_id": state["employee_id"],
    })
    
    return {"messages": [response]}

def process_leave_request(state: AgentState):
    """
    A specialized node to handle the multi-step process of gathering leave details.
    This node uses the LLM to ask clarifying questions until all required details are collected.
    """
    logger.info(f"--- Processing Leave Request for Employee: {state['employee_id']} ---")
    
    details = state.get("leave_request_details", {})
    
    # Define the JSON schema for the details we need to extract
    extraction_schema = {
        "title": "LeaveRequestDetails",
        "description": "Extracts the details of a leave request from the conversation.",
        "type": "object",
        "properties": {
            "leave_type": {"type": "string", "description": "The type of leave (e.g., 'Annual', 'Sick', 'Casual')."},
            "start_date": {"type": "string", "description": "The start date in YYYY-MM-DD format."},
            "end_date": {"type": "string", "description": "The end date in YYYY-MM-DD format."},
            "reason": {"type": "string", "description": "The reason for the leave, if provided."},
        },
    }

    # Create a specialized LLM for detail extraction
    extraction_llm = llm.with_structured_output(extraction_schema)

    leave_prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an expert at extracting leave request details from a conversation. Based on the history, extract the following fields. If a field is missing, its value must be null."),
        MessagesPlaceholder(variable_name="messages")
    ])

    runnable = leave_prompt | extraction_llm
    extracted_data = runnable.invoke({"messages": state['messages']})

    # Update the state with any newly extracted details
    for key, value in extracted_data.items():
        if value and not details.get(key):
            details[key] = value

    # Check if we have all the details needed to proceed
    required_for_confirmation = ["leave_type", "start_date", "end_date"]
    if all(details.get(key) for key in required_for_confirmation):
        # We have enough to ask for confirmation
        summary = (
            f"Thank you. Just to confirm, you are requesting **{details['leave_type']} Leave** "
            f"from **{details['start_date']}** to **{details['end_date']}**. Is this correct?"
        )
        message = AIMessage(content=summary)
    else:
        # We need more information, ask a clarifying question
        missing_fields = [field.replace("_", " ") for field in required_for_confirmation if not details.get(field)]
        question = f"I can help with that. To proceed, could you please provide the following: {', '.join(missing_fields)}?"
        message = AIMessage(content=question)
        
    return {"messages": [message], "leave_request_details": details}

# --- Conditional Edge Logic ---

def master_router(state: AgentState) -> Literal["process_leave_request", "call_agent", "__end__"]:
    """
    This is the main router. It analyzes the user's intent and the conversation state
    to decide which node to go to next.
    """
    logger.info(f"--- Master Router Evaluating State for Employee: {state['employee_id']} ---")
    last_message = state['messages'][-1]
    
    # If the agent's last message was a tool call, we should execute it.
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "call_agent" # The agent has decided to use a tool

    # Check the user's latest message to determine intent
    if isinstance(last_message, HumanMessage):
        user_intent_query = last_message.content.lower()
        # If user confirms details, proceed to submit
        if state.get("leave_request_details", {}).get("start_date") and any(word in user_intent_query for word in ["yes", "correct", "confirm", "proceed"]):
            details = state["leave_request_details"]
            # If reason is missing, ask for it, otherwise submit
            if not details.get("reason"):
                return "process_leave_request" # Will now ask for reason
            else:
                 # We have everything, so we call the agent to trigger the final tool call
                return "call_agent"

        # If user wants to start a leave request
        if any(word in user_intent_query for word in ["leave", "vacation", "sick", "time off"]):
             return "process_leave_request"

    # For any other case (general questions, checking balance, etc.), use the standard agent.
    return "call_agent"

# --- Graph Definition ---

def create_graph():
    """Builds the production-grade stateful agent graph."""
    workflow = StateGraph(AgentState)

    # Add nodes to the graph
    workflow.add_node("initialize", initialize_state)
    workflow.add_node("process_leave_request", process_leave_request)
    workflow.add_node("call_agent", call_agent)
    workflow.add_node("tools", tool_node)

    # Define the graph's flow
    workflow.set_entry_point("initialize")
    
    workflow.add_conditional_edges(
        "initialize",
        master_router,
        {
            "process_leave_request": "process_leave_request",
            "call_agent": "call_agent",
        }
    )
    
    workflow.add_conditional_edges(
        "call_agent",
        lambda state: "tools" if isinstance(state['messages'][-1], AIMessage) and state['messages'][-1].tool_calls else "__end__",
        {
            "tools": "tools",
            "__end__": "__end__"
        }
    )
    
    workflow.add_edge("tools", "call_agent") # After a tool is called, let the agent decide the next response.
    workflow.add_edge("process_leave_request", "__end__") # After asking a question, wait for user input.

    # Compile the graph into a runnable object
    return workflow.compile()

# Create a single, compiled instance of the graph to be used by the application
# This is thread-safe and can be called by multiple users concurrently.
leave_agent_graph = create_graph()
