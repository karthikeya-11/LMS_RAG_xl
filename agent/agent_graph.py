# /agent/agent_graph.py

from typing import TypedDict, Annotated, Sequence, Literal
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, ToolMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from pydantic import BaseModel, Field
import logging
from datetime import datetime

# Import tools and helper functions
from .tools import (check_leave_balance, submit_leave_request, get_company_holidays,
                    view_leave_history, answer_policy_question)
from services.excel_handler import get_employee_data, update_leave_balance
from .prompts import get_system_prompt

# --- Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

llm = ChatOpenAI(model="gpt-4o", temperature=0)
tools = [check_leave_balance, submit_leave_request, get_company_holidays, view_leave_history, answer_policy_question]
tool_node = ToolNode(tools)
llm_with_tools = llm.bind_tools(tools)

# --- Pydantic Schema for Structured Extraction ---
class LeaveDetails(BaseModel):
    """Schema for extracting leave request details from user text."""
    leave_type: str | None = Field(description="The type of leave (e.g., 'sick', 'annual', 'casual').")
    start_date: str | None = Field(description="The start date in YYYY-MM-DD format.")
    end_date: str | None = Field(description="The end date in YYYY-MM-DD format.")

# --- Agent State Schema ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    employee_id: str
    employee_name: str
    next_node: Literal["router", "tool_executor", "leave_gather", "leave_confirm", "leave_submit", "leave_final_submit", "end"]
    leave_type: str | None
    start_date: str | None
    end_date: str | None

# --- Node Functions ---

def initialize_node(state: AgentState, config: dict) -> dict:
    """Ensures the agent's state is correctly populated with the user's identity."""
    logger.info("--- Stage: Initializer ---")
    thread_id = config['configurable']['thread_id']
    
    if not state.get('employee_id'):
        logger.info(f"Initializing state for employee_id: {thread_id}")
        employee_info = get_employee_data(thread_id)
        state['employee_id'] = thread_id
        state['employee_name'] = employee_info.get('name', 'Employee') if employee_info else 'Employee'
    
    # If a leave process is underway, jump to the correct step. Otherwise, go to the router.
    if state.get('next_node') in ["leave_confirm", "leave_submit", "leave_final_submit"]:
        logger.info(f"Resuming at node: {state['next_node']}")
        return state
    else:
        state['next_node'] = "router"
        return state

def router_node(state: AgentState) -> dict:
    """Decides if the user wants to use a standard tool or request leave."""
    logger.info(f"--- Stage: Router ---")
    
    # This improved prompt helps the LLM better distinguish between asking and doing.
    system_prompt = get_system_prompt(state) + (
        "\nAnalyze the user's last message. If they are asking a question about a leave type (e.g., 'what is accident leave?'), "
        "call the `answer_policy_question` tool. If they are explicitly asking to apply for or book leave, call the `submit_leave_request` tool. "
        "For other direct questions (balance, history, holidays), use the appropriate tool."
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        MessagesPlaceholder(variable_name="messages")
    ])
    chain = prompt | llm_with_tools
    response = chain.invoke({"messages": [state['messages'][-1]]})

    if not response.tool_calls:
        logger.info("Router -> End (General Chit-chat)")
        return {"messages": [response], "next_node": "end"}
    
    if any(tc['name'] == 'submit_leave_request' for tc in response.tool_calls):
        logger.info("Router -> Leave Gather")
        return {"next_node": "leave_gather"}
    else:
        logger.info("Router -> Tool Executor")
        return {"messages": [response], "next_node": "tool_executor"}

def tool_executor_node(state: AgentState) -> dict:
    """Executes standard tools and generates a final response."""
    logger.info("--- Stage: Tool Executor ---")
    
    tool_output = tool_node.invoke(state)
    
    if isinstance(tool_output, dict) and "messages" in tool_output:
        tool_messages = tool_output["messages"]
    elif isinstance(tool_output, list):
        tool_messages = tool_output
    else:
        tool_messages = [tool_output]

    summary_prompt = ChatPromptTemplate.from_messages([
        ("system", get_system_prompt(state) + "\nSummarize the result of the tool call in a helpful and friendly way."),
        MessagesPlaceholder(variable_name="messages")
    ])
    chain = summary_prompt | llm
    final_response = chain.invoke({"messages": state['messages'] + tool_messages})
    
    return {"messages": tool_messages + [final_response], "next_node": "end"}


def leave_gather_node(state: AgentState) -> dict:
    """Asks for leave details and waits for user input."""
    logger.info("--- Stage: Leave Gather ---")
    return {
        "messages": [AIMessage(content="I can help with that. What type of leave is it, and for what dates? For example: 'sick leave tomorrow for one day'.")],
        "next_node": "leave_confirm"
    }

def leave_confirm_node(state: AgentState) -> dict:
    """Intelligently extracts details and asks for confirmation."""
    logger.info("--- Stage: Leave Confirm ---")
    user_message = state['messages'][-1].content
    
    # FIX: Add an escape hatch for cancellation.
    cancellation_keywords = ['cancel', 'stop', 'never mind', 'don\'t want', 'no leave']
    if any(keyword in user_message.lower() for keyword in cancellation_keywords):
        logger.info("User cancelled the leave request.")
        return {
            "messages": [AIMessage(content="Okay, I've cancelled the leave request. Is there anything else I can help with?")],
            "next_node": "end",
            "leave_type": None, "start_date": None, "end_date": None
        }
        
    extraction_llm = llm.with_structured_output(LeaveDetails)
    prompt_for_extraction = f"Today's date is {datetime.now().strftime('%Y-%m-%d')}. Extract leave details from the following user request: '{user_message}'"
    details = extraction_llm.invoke(prompt_for_extraction)

    if details.start_date and details.end_date and details.leave_type:
        logger.info(f"Details extracted: {details.leave_type}, {details.start_date}-{details.end_date}")
        confirmation_text = f"Got it. Just to confirm, you want to request **{details.leave_type} leave** from **{details.start_date}** to **{details.end_date}**. Is this correct? (yes/no)"
        return {
            "messages": [AIMessage(content=confirmation_text)],
            "leave_type": details.leave_type, "start_date": details.start_date, "end_date": details.end_date,
            "next_node": "leave_submit"
        }
    else:
        logger.info("Not enough details extracted, asking user for more info.")
        return {"messages": [AIMessage(content="I'm sorry, I couldn't understand the dates. Please provide the leave type, start date, and end date.")], "next_node": "leave_confirm"}

def leave_submit_node(state: AgentState) -> dict:
    """Processes the user's confirmation (yes/no) and asks for a reason."""
    logger.info("--- Stage: Leave Submit ---")
    user_message = state["messages"][-1].content.lower()

    if "yes" in user_message:
        return {"messages": [AIMessage(content="Great. Could you please provide a brief reason for your leave?")], "next_node": "leave_final_submit"}
    elif "no" in user_message:
        return {"messages": [AIMessage(content="Okay, I've cancelled the request. Let's start over. What type of leave and for what dates?")], "next_node": "leave_gather", "leave_type": None, "start_date": None, "end_date": None}
    else:
        return {"messages": [AIMessage(content="Please respond with 'yes' to confirm or 'no' to start over.")], "next_node": "leave_submit"}

def leave_final_submit_node(state: AgentState) -> dict:
    """Takes the reason and performs the final submission."""
    logger.info("--- Stage: Final Leave Submit ---")
    reason = state["messages"][-1].content
    
    submission_result = submit_leave_request.invoke({
        "employee_id": state["employee_id"], "leave_type": state["leave_type"],
        "start_date": state["start_date"], "end_date": state["end_date"], "reason": reason
    })
    
    if "Success" in submission_result:
        update_leave_balance(state["employee_id"], state["start_date"], state["end_date"])
        
    final_message = f"{submission_result}\n\nIs there anything else I can help you with today?"
    
    return {
        "messages": [AIMessage(content=final_message)], "next_node": "end",
        "leave_type": None, "start_date": None, "end_date": None
    }

# --- Graph Assembly ---
def get_graph_app() -> StateGraph:
    """Builds the graph object."""
    graph = StateGraph(AgentState)

    graph.add_node("initialize", initialize_node)
    graph.add_node("router", router_node)
    graph.add_node("tool_executor", tool_executor_node)
    graph.add_node("leave_gather", leave_gather_node)
    graph.add_node("leave_confirm", leave_confirm_node)
    graph.add_node("leave_submit", leave_submit_node)
    graph.add_node("leave_final_submit", leave_final_submit_node)

    graph.set_entry_point("initialize")

    # This conditional entry point correctly resumes the conversation at the right step.
    graph.add_conditional_edges("initialize", lambda state: state["next_node"], {
        "router": "router",
        "leave_confirm": "leave_confirm",
        "leave_submit": "leave_submit",
        "leave_final_submit": "leave_final_submit"
    })
    
    graph.add_conditional_edges("router", lambda state: state["next_node"], {
        "tool_executor": "tool_executor", 
        "leave_gather": "leave_gather", 
        "end": END
    })
    
    # After each node in the leave flow, the graph now terminates to wait for user input.
    graph.add_edge("leave_gather", END)
    graph.add_edge("leave_confirm", END)
    graph.add_edge("leave_submit", END)
    graph.add_edge("leave_final_submit", END)
    graph.add_edge("tool_executor", END)

    return graph
