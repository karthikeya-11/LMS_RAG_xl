# /services/excel_handler.py

import pandas as pd
import os
import logging
from datetime import datetime
from threading import Lock

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
EXCEL_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'employee_leave_data.xlsx')
file_lock = Lock()

# --- Helper Functions ---
def _load_sheet(sheet_name):
    """Loads a specific sheet from the Excel file in a thread-safe manner."""
    with file_lock:
        if not os.path.exists(EXCEL_FILE):
            raise FileNotFoundError(f"Excel data file not found at {EXCEL_FILE}.")
        return pd.read_excel(EXCEL_FILE, sheet_name=sheet_name)

def _save_sheets(writer, df_dict):
    """Saves multiple DataFrames to their respective sheets."""
    for sheet_name, df in df_dict.items():
        df.to_excel(writer, sheet_name=sheet_name, index=False)

# --- Core Data Functions ---

def set_annual_leave_balance(employee_id: str, new_balance: int) -> bool:
    """Explicitly sets the annual leave balance to a specific value."""
    with file_lock:
        try:
            employees_df = pd.read_excel(EXCEL_FILE, sheet_name='Employees')
            leave_requests_df = pd.read_excel(EXCEL_FILE, sheet_name='LeaveRequests')

            employee_index = employees_df.index[employees_df['employee_id'] == employee_id].tolist()
            if not employee_index:
                logging.error(f"Set balance failed: Employee {employee_id} not found.")
                return False
            
            employees_df.loc[employee_index[0], 'annual_leave_balance'] = new_balance
            
            with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
                _save_sheets(writer, {'Employees': employees_df, 'LeaveRequests': leave_requests_df})
            
            logging.info(f"Successfully set annual leave balance for {employee_id} to {new_balance}.")
            return True
        except Exception as e:
            logging.error(f"Failed to set annual leave balance for {employee_id}: {e}")
            return False

def update_leave_balance(employee_id: str, start_date: str, end_date: str) -> bool:
    """
    Calculates the number of leave days and deducts it from the annual balance.
    This is called by the graph after a leave request is successfully submitted.
    """
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        num_days = (end_dt - start_dt).days + 1
        if num_days <= 0: return False

        current_balance = get_annual_leave_balance(employee_id)
        new_balance = current_balance - num_days
        
        logging.info(f"Updating balance for {employee_id}. Old: {current_balance}, New: {new_balance}")
        return set_annual_leave_balance(employee_id, new_balance)
    except Exception as e:
        logging.error(f"Failed during balance update for {employee_id}: {e}")
        return False

def check_for_overlapping_leave(employee_id: str, start_date_new: datetime, end_date_new: datetime) -> str:
    """Checks for any approved leave requests that overlap with the given date range."""
    try:
        df = _load_sheet('LeaveRequests')
        if df.empty: return None
        history_df = df[(df['employee_id'] == employee_id) & (df['status'] == 'approved')].copy()
        if history_df.empty: return None

        history_df['start_date'] = pd.to_datetime(history_df['start_date'])
        history_df['end_date'] = pd.to_datetime(history_df['end_date'])

        for _, row in history_df.iterrows():
            if start_date_new <= row['end_date'] and end_date_new >= row['start_date']:
                return f"Request overlaps with an existing approved leave (ID: {row['request_id']})"
        return None
    except Exception as e:
        logging.error(f"Overlap check error for {employee_id}: {e}")
        return "An internal error occurred while checking for leave conflicts."

def add_leave_request(employee_id: str, leave_type: str, start_date: str, end_date: str, days: int, reason: str, status: str) -> str:
    """Adds a new leave request record to the Excel sheet."""
    with file_lock:
        try:
            employees_df = pd.read_excel(EXCEL_FILE, sheet_name='Employees')
            leave_requests_df = pd.read_excel(EXCEL_FILE, sheet_name='LeaveRequests')
            req_id = f"REQ{len(leave_requests_df) + 101:03d}"
            new_req = pd.DataFrame([{'request_id': req_id, 'employee_id': employee_id, 'leave_type': leave_type, 
                                     'start_date': start_date, 'end_date': end_date, 'days': days, 'reason': reason, 
                                     'status': status, 'request_date': datetime.now().strftime('%Y-%m-%d')}])
            updated_df = pd.concat([leave_requests_df, new_req], ignore_index=True)
            with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
                _save_sheets(writer, {'Employees': employees_df, 'LeaveRequests': updated_df})
            return req_id
        except Exception as e:
            logging.error(f"Failed to add leave request for {employee_id}: {e}")
            return None

def get_annual_leave_balance(employee_id: str) -> int:
    """Retrieves only the annual leave balance for a given employee."""
    employee_data = get_employee_data(employee_id)
    return employee_data.get('annual_leave_balance', 0) if employee_data else 0

def verify_credentials(employee_id: str, password: str) -> bool:
    """Verifies user credentials against the 'Employees' sheet."""
    try:
        df = _load_sheet('Employees')
        employee = df[df['employee_id'] == employee_id]
        return not employee.empty and employee.iloc[0]['password'] == password
    except Exception: return False

def get_employee_data(employee_id: str) -> dict:
    """Retrieves all data for a single employee."""
    try:
        df = _load_sheet('Employees')
        employee = df[df['employee_id'] == employee_id]
        return employee.iloc[0].to_dict() if not employee.empty else None
    except Exception: return None

def get_leave_history(employee_id: str) -> list:
    """Retrieves all leave requests for a single employee."""
    try:
        df = _load_sheet('LeaveRequests')
        history = df[df['employee_id'] == employee_id]
        return history.to_dict('records') if not history.empty else []
    except Exception: return []
