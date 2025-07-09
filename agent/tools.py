# /agent/tools.py

import logging
from datetime import datetime, date
from langchain.tools import tool

from services import excel_handler, policy_rag

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _normalize_leave_type(leave_type: str) -> str:
    """Standardizes the leave type string for consistency."""
    lt = leave_type.lower().strip()
    if "causal" in lt:
        return "casual"
    # For now, we keep the original leave types for clarity in records.
    # The policy check can handle the different types.
    return lt

@tool
def answer_policy_question(question: str) -> str:
    """Use this tool to answer general questions about the company's leave policy."""
    logger.info(f"Tool 'answer_policy_question' called with question: '{question}'")
    return policy_rag.answer_general_question(question)

@tool
def check_leave_balance(employee_id: str) -> str:
    """Use this tool to check the current annual leave balance for the logged-in employee."""
    logger.info(f"Tool 'check_leave_balance' called for employee: {employee_id}")
    balance = excel_handler.get_annual_leave_balance(employee_id)
    return f"Your current annual leave balance is {balance} days."

@tool
def view_leave_history(employee_id: str) -> str:
    """Use this tool to view the history of all past and pending leave requests for the logged-in employee."""
    logger.info(f"Tool 'view_leave_history' called for employee: {employee_id}")
    history = excel_handler.get_leave_history(employee_id)
    if not history:
        return "You have no leave requests in your history."
    
    response = "Here is your leave history:\n"
    for record in history:
        response += (f"- ID: {record.get('request_id', 'N/A')}, Type: {record.get('leave_type', 'N/A').capitalize()}, "
                     f"From: {record.get('start_date', 'N/A')}, To: {record.get('end_date', 'N/A')}, "
                     f"Status: {record.get('status', 'N/A')}\n")
    return response.strip()

@tool
def submit_leave_request(employee_id: str, leave_type: str, start_date: str, end_date: str, reason: str) -> str:
    """Use this tool to submit a leave request after all information has been collected and confirmed."""
    logger.info(f"--- Tool 'submit_leave_request' initiated for {employee_id} ---")
    
    normalized_leave_type = _normalize_leave_type(leave_type)
    
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
        num_days = (end_dt - start_dt).days + 1
        if num_days <= 0:
            return "Error: The leave end date must be on or after the start date."
    except ValueError:
        return "Error: Invalid date format. Please use YYYY-MM-DD."

    # Step 1: Common Sense Validation
    if normalized_leave_type == 'sick' and start_dt > date.today():
        logger.warning(f"Leave denied for {employee_id}: Future sick leave application.")
        return "Request Denied. Sick leave cannot be applied for a future date."

    # Step 2: Overlap Check
    overlap_error = excel_handler.check_for_overlapping_leave(employee_id, start_dt, end_dt)
    if overlap_error:
        logger.warning(f"Leave denied for {employee_id} due to overlap: {overlap_error}")
        return f"Request Denied. {overlap_error}"

    # Step 3: Policy Compliance Check via RAG
    policy_check = policy_rag.check_policy_compliance(normalized_leave_type, num_days, reason)
    if not policy_check.get('compliant'):
        logger.warning(f"Leave denied for {employee_id} due to policy violation: {policy_check.get('reason')}")
        return f"Request Denied. Policy Violation: {policy_check.get('reason', 'The request violates company policy.')}"

    # Step 4: Balance Check
    # We assume all leave types for this tool deduct from the main balance for simplicity.
    available_days = excel_handler.get_annual_leave_balance(employee_id)
    if available_days < num_days:
        logger.warning(f"Leave denied for {employee_id} due to insufficient balance.")
        return f"Request Denied. Insufficient balance. You need {num_days} days but only have {available_days} available."

    # Step 5: Write Request to Excel
    request_id = excel_handler.add_leave_request(employee_id, normalized_leave_type, start_date, end_date, num_days, reason, "approved")
    if not request_id:
        logger.error(f"CRITICAL ERROR: Failed to save leave request for {employee_id}.")
        return "CRITICAL ERROR: Your request could not be saved. Please contact HR."

    # Step 6: Final Success Response (Balance update is handled separately in the graph)
    logger.info(f"Leave request {request_id} successfully submitted for {employee_id}.")
    return f"Success! Your {normalized_leave_type} leave request has been approved and submitted. Your Request ID is {request_id}."

@tool
def get_company_holidays() -> str:
    """Use this tool to get a list of the company's public and optional holidays from the leave policy document."""
    logger.info("Tool 'get_company_holidays' called, using RAG.")
    question = "What are the company's public and optional holidays mentioned in the policy document? List them out clearly."
    return policy_rag.answer_general_question(question)
