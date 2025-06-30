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
    """Loads a specific sheet from the Excel file."""
    with file_lock:
        if not os.path.exists(EXCEL_FILE):
            raise FileNotFoundError(f"Excel data file not found at {EXCEL_FILE}.")
        return pd.read_excel(EXCEL_FILE, sheet_name=sheet_name)

def _save_sheets(writer, df_dict):
    """Saves multiple DataFrames to their respective sheets."""
    for sheet_name, df in df_dict.items():
        df.to_excel(writer, sheet_name=sheet_name, index=False)

# --- NEW `set` function for explicit updates ---
def set_annual_leave_balance(employee_id: str, new_balance: int) -> bool:
    """
    Sets the annual leave balance to a specific value in a thread-safe manner.
    This function performs the write operation only.
    """
    with file_lock:
        try:
            employees_df = pd.read_excel(EXCEL_FILE, sheet_name='Employees')
            leave_requests_df = pd.read_excel(EXCEL_FILE, sheet_name='LeaveRequests')

            employee_index = employees_df.index[employees_df['employee_id'] == employee_id].tolist()
            if not employee_index:
                logging.error(f"Set balance failed: Employee {employee_id} not found.")
                return False
            idx = employee_index[0]
            
            # Directly set the new value
            employees_df.at[idx, 'annual_leave_balance'] = new_balance
            
            with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
                _save_sheets(writer, {'Employees': employees_df, 'LeaveRequests': leave_requests_df})
            
            logging.info(f"Successfully set annual leave balance for {employee_id} to {new_balance}.")
            return True
        except Exception as e:
            logging.error(f"Failed to set annual leave balance for {employee_id}: {e}")
            return False

# --- Other functions remain largely the same ---

def check_for_overlapping_leave(employee_id: str, start_date_new: datetime, end_date_new: datetime) -> str:
    """Checks for any approved leave requests that overlap with the given date range."""
    try:
        df = _load_sheet('LeaveRequests')
        if df.empty or 'start_date' not in df.columns: return None
        history_df = df[(df['employee_id'] == employee_id) & (df['status'] == 'approved')].copy()
        if history_df.empty: return None

        history_df['start_date'] = pd.to_datetime(history_df['start_date'], errors='coerce')
        history_df['end_date'] = pd.to_datetime(history_df['end_date'], errors='coerce')
        history_df.dropna(subset=['start_date', 'end_date'], inplace=True)

        for _, existing_leave in history_df.iterrows():
            if start_date_new <= existing_leave['end_date'] and end_date_new >= existing_leave['start_date']:
                return (f"Request overlaps with an existing approved leave (ID: {existing_leave['request_id']})")
        return None
    except Exception as e:
        logging.error(f"Overlap check error for {employee_id}: {e}")
        return "An internal error occurred while checking for leave conflicts."

def get_annual_leave_balance(employee_id: str) -> int:
    """Retrieves only the annual leave balance for a given employee."""
    employee_data = get_employee_data(employee_id)
    return employee_data.get('annual_leave_balance', 0) if employee_data else 0

def add_leave_request(employee_id: str, leave_type: str, start_date: str, end_date: str, days: int, reason: str, status: str) -> str:
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
            
# ... (verify_credentials, get_employee_data, get_leave_history, etc. are unchanged)
def verify_credentials(employee_id: str, password: str) -> bool:
    try:
        df = _load_sheet('Employees'); employee = df[df['employee_id'] == employee_id]
        return employee.iloc[0]['password'] == password if not employee.empty else False
    except: return False
def get_employee_data(employee_id: str) -> dict:
    try:
        df = _load_sheet('Employees'); employee = df[df['employee_id'] == employee_id]
        return employee.iloc[0].to_dict() if not employee.empty else None
    except: return None
def get_leave_history(employee_id: str) -> list:
    try:
        df = _load_sheet('LeaveRequests'); employee_history = df[df['employee_id'] == employee_id]
        return employee_history.to_dict('records') if not employee_history.empty else []
    except: return []
