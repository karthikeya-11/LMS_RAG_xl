# /agent/tools.py

import logging
from datetime import datetime
from langchain.tools import tool

from services import excel_handler, policy_rag

def normalize_leave_type(leave_type: str) -> str:
    lt = leave_type.lower().strip()
    return "casual" if "causal" in lt else lt

@tool
def answer_policy_question(question: str) -> str:
    """Answers general questions about the company's leave policy."""
    return policy_rag.answer_general_question(question)

@tool
def check_leave_balance(employee_id: str) -> str:
    """Checks the current annual leave balance."""
    balance = excel_handler.get_annual_leave_balance(employee_id)
    return f"Your current annual leave balance is {balance} days."

@tool
def view_leave_history(employee_id: str) -> str:
    """Views the history of all past and pending leave requests."""
    history = excel_handler.get_leave_history(employee_id)
    if not history: return "You have no leave requests in your history."
    response = "Here is your leave history:\n"
    for record in history:
        response += (f"- ID: {record.get('request_id', 'N/A')}, Type: {record.get('leave_type', 'N/A').capitalize()}, "
                     f"From: {record.get('start_date', 'N/A')}, To: {record.get('end_date', 'N/A')}, "
                     f"Status: {record.get('status', 'N/A')}\n")
    return response.strip()

@tool
def submit_leave_request(employee_id: str, leave_type: str, start_date: str, end_date: str, reason: str) -> str:
    """Submits a leave request after all information has been collected and confirmed."""
    logging.info(f"--- Starting Leave Submission for {employee_id} ---")
    
    normalized_leave_type = normalize_leave_type(leave_type)
    leave_types_deducted_from_annual = ['annual', 'sick', 'casual']

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        num_days = (end_dt - start_dt).days + 1
        if num_days <= 0: return "Error: Leave must be for at least one day."
    except ValueError:
        return "Error: Invalid date format. Dates must be in YYYY-MM-DD format."

    # Step 1: Overlap Check
    overlap_error = excel_handler.check_for_overlapping_leave(employee_id, start_dt, end_dt)
    if overlap_error: return f"Request Denied. {overlap_error}"

    # Step 2: Policy Check
    policy_check = policy_rag.check_policy_compliance(normalized_leave_type, num_days, reason)
    if not policy_check.get('compliant'):
        return f"Request Denied. Policy Violation: {policy_check.get('reason', 'The request violates company policy.')}"

    # Step 3: Balance Check (if applicable)
    if normalized_leave_type in leave_types_deducted_from_annual:
        available_days = excel_handler.get_annual_leave_balance(employee_id)
        if available_days < num_days:
            return f"Request Denied. Insufficient balance. You need {num_days} days but only have {available_days} in your annual leave pool."
        
        # **THE FIX**: Explicitly subtract first, then call the update function.
        new_balance = available_days - num_days
        logging.info(f"Balance check passed. New balance will be: {new_balance}")
    
    # Step 4: Write Request to Excel
    request_id = excel_handler.add_leave_request(employee_id, normalized_leave_type, start_date, end_date, num_days, reason, "approved")
    if not request_id:
        return "CRITICAL ERROR: Your request could not be saved. Please contact HR."

    # Step 5: Update Balance in Excel (if applicable)
    if normalized_leave_type in leave_types_deducted_from_annual:
        success = excel_handler.set_annual_leave_balance(employee_id, new_balance)
        if not success:
            return f"CRITICAL ERROR: Request {request_id} was saved, but your balance could not be updated. Contact HR immediately."

    # Step 6: Final Response
    final_message = f"Success! Your {normalized_leave_type} leave request has been approved and submitted.\n- Request ID: {request_id}"
    if normalized_leave_type in leave_types_deducted_from_annual:
        final_message += f"\n- Your new annual leave balance is {new_balance} days."
    return final_message

@tool
def get_company_holidays() -> str:
    """Returns a list of upcoming official company holidays."""
    return "Upcoming Company Holidays:\n- 2025-11-27: Thanksgiving Day"
