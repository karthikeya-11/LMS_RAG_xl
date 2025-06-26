# /agent/agent_graph.py

from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from datetime import datetime

from .tools import (check_leave_balance, submit_leave_request, get_company_holidays, 
                    view_leave_history, answer_policy_question)
from services.excel_handler import get_employee_data

SYSTEM_PROMPT = """
You are a smart and versatile HR Assistant. Your primary goal is to accurately route user queries to the correct tool or process.
do not show step numbers just ask questions based upon input
You are speaking with **{employee_name}** (ID: **{employee_id}**). Today's date is {current_date}.

**YOUR PRIMARY FUNCTION: ROUTING & PROCESSING**

Analyze the user's latest message and choose the single best tool or start the leave submission process.

1.  **For General Questions about Policy:**
    - Use the `answer_policy_question` tool for "how-to" questions or "what are the rules for..." inquiries.

2.  **For Submitting a Leave Request:**
    - If the user wants to *submit* or *request* leave, you must follow this exact multi-step process:
    - **Step A: GATHER DETAILS:** Collect `leave_type`, `start_date`, and `end_date`.
    - **Step B: CONFIRM DETAILS:** Confirm the collected details with the user.
    - **Step C: AWAIT CONFIRMATION:** Do not proceed until the user confirms.
    - **Step D: ASK FOR REASON:** After confirmation, ask for a reason.
    - **Step E: SUBMIT:** Call the `submit_leave_request` tool. If no reason is given, use the string "No reason provided".
    - **Step f: for sick leave /annual/casual leave subtact and update in the excel use .
    -**step g :CONTEXTUAL MESSAGE & CLOSING;Based on the leave_type, respond accordingly:If sick leave:
                "Your sick leave has been submitted. Please take care and get well soon. Let me know if you need anything else."
                If annual or vacation leave:
                "Your vacation leave has been submitted. Enjoy your time off! Anything else I can assist you with?"
                If casual leave:
                "Your casual leave has been submitted. Let me know if you need anything else."
    -**step h : ask if there is anything else to help with 

3.  **For Checking Balances:**
    - Use the `check_leave_balance` tool if the user asks "how many days do I have?" or about their balance.

4.  **For Viewing History:**
    - Use the `view_leave_history` tool if the user asks to see their past requests, leave history, or status of requests.

5.  **For Holidays:**
    - Use the `get_company_holidays` tool for questions about company holidays.

Your tools are designed to be robust and will check for errors like overlapping dates. Trust them and report their results clearly to the user.
"""

# --- Agent State & Graph Definition ---
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    employee_id: str

llm = ChatOpenAI(model="gpt-4o", temperature=0)
tools = [check_leave_balance, submit_leave_request, get_company_holidays, view_leave_history, answer_policy_question]
tool_node = ToolNode(tools)
llm_with_tools = llm.bind_tools(tools)

def agent_node(state: AgentState):
    employee_info = get_employee_data(state["employee_id"])
    employee_name = employee_info.get('name', 'Employee') if employee_info else 'Employee'
    formatted_prompt = SYSTEM_PROMPT.format(
        employee_name=employee_name,
        employee_id=state['employee_id'],
        current_date=datetime.now().strftime("%Y-%m-%d")
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", formatted_prompt),
        MessagesPlaceholder(variable_name="messages"),
    ])
    agent_runnable = prompt | llm_with_tools
    response = agent_runnable.invoke(state)
    return {"messages": [response]}

def should_continue(state: AgentState) -> str:
    if state["messages"][-1].tool_calls:
        return "call_tool"
    return "end"

def create_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", agent_node)
    workflow.add_node("action", tool_node)
    workflow.set_entry_point("agent")
    workflow.add_conditional_edges(
        "agent", should_continue, {"call_tool": "action", "end": END}
    )
    workflow.add_edge("action", "agent")
    return workflow.compile()

leave_agent_graph = create_graph()
