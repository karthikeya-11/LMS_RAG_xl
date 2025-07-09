# /agent/prompts.py

from datetime import datetime

# This is the base system prompt that provides context to the agent.
BASE_SYSTEM_PROMPT = """
You are a smart and versatile HR Assistant for the company "tech.at.core".
You are responsible for routing user queries to the correct tool or guiding them through the multi-step leave submission process.

You are currently speaking with employee **{employee_name}** (ID: **{employee_id}**).
Today's date is {current_date}.

**Your Routing Logic:**
- If the user asks to apply for, book, request, or take any form of leave (vacation, sick, time off, etc.), you MUST call the `submit_leave_request` tool. This will trigger the multi-step guidance process.
- For questions about company leave policy (e.g., "how many sick days?"), use the `answer_policy_question` tool.
- For requests about leave balance, history, or company holidays, use the appropriate tools (`check_leave_balance`, `view_leave_history`, `get_company_holidays`).
- For general conversation (greetings, etc.), respond naturally without using a tool.
"""

def get_system_prompt(state: dict) -> str:
    """
    Formats the system prompt with dynamic, user-specific information from the state.
    """
    from services.excel_handler import get_employee_data
    
    # FIX: Use .get() for safe dictionary access to prevent KeyErrors.
    employee_id = state.get("employee_id")
    employee_name = state.get("employee_name")

    # This should not happen if the frontend sends the correct config, but it's a good safeguard.
    if not employee_id:
        return BASE_SYSTEM_PROMPT.format(
            employee_name="Employee",
            employee_id="N/A",
            current_date=datetime.now().strftime("%Y-%m-%d")
        )

    # If the name is missing from the state for any reason, fetch it using the ID.
    if not employee_name:
        employee_info = get_employee_data(employee_id)
        employee_name = employee_info.get('name', 'Employee') if employee_info else 'Employee'

    return BASE_SYSTEM_PROMPT.format(
        employee_name=employee_name,
        employee_id=employee_id,
        current_date=datetime.now().strftime("%Y-%m-%d")
    )
