# Script to generate the dummy Excel file 

import pandas as pd
import os

def create_dummy_excel_file(filename="employee_leave_data.xlsx"):
    """Creates the Excel file with initial data."""
    
    # Create the data directory if it doesn't exist
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    os.makedirs(data_dir, exist_ok=True)
    file_path = os.path.join(data_dir, filename)

    employees_data = {
        'employee_id': ['E001', 'E002'],
        'name': ['Alice Smith (Manager)', 'Bob Johnson (Employee)'],
        'password': ['pass123', 'pass456'], # Use hashed passwords in production
        'annual_leave_balance': [15, 12],
        'sick_leave_balance': [10, 8],
        'personal_leave_balance': [5, 3]
    }
    employees_df = pd.DataFrame(employees_data)
    
    leave_requests_data = {
        'request_id': [], 'employee_id': [], 'leave_type': [],
        'start_date': [], 'end_date': [], 'days': [], 'reason': [],
        'status': [], 'request_date': []
    }
    leave_requests_df = pd.DataFrame(leave_requests_data)
    
    with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
        employees_df.to_excel(writer, sheet_name='Employees', index=False)
        leave_requests_df.to_excel(writer, sheet_name='LeaveRequests', index=False)
        
    print(f"Successfully created '{file_path}'")

if __name__ == "__main__":
    create_dummy_excel_file()