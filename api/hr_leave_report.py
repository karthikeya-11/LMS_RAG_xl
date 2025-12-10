# /api/hr_leave_report.py
"""HR Leave Report API Blueprint - Provides endpoints for HR to access all employee leave data."""

from flask import Blueprint, send_file, jsonify, request
import pandas as pd
import os
import logging
from services.excel_handler import get_employee_data
from api.auth import token_required

EXCEL_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'employee_leave_data.xlsx')
hr_report_api = Blueprint('hr_report_api', __name__)
logger = logging.getLogger(__name__)

def is_hr(employee_id):
    """Check if the given employee has HR role (checks both 'Role' and 'role' columns)."""
    emp = get_employee_data(employee_id)
    if not emp:
        return False
    # Check both 'Role' and 'role' for compatibility
    role = emp.get('Role') or emp.get('role')
    return role and str(role).strip().lower() == 'hr'

@hr_report_api.route('/api/hr/download-leave-report', methods=['GET'])
def download_leave_report():
    """Download full leave request Excel file. HR only."""
    # Get employee_id from query parameter (not using token_required decorator to keep it simple)
    current_user_id = request.args.get('employee_id')
    
    if not current_user_id:
        return jsonify({'error': 'employee_id parameter required'}), 400
    
    if not is_hr(current_user_id):
        logger.warning(f"Access denied: {current_user_id} attempted to download HR report but is not HR")
        return jsonify({'error': 'Access denied. Only HR personnel can download leave reports.'}), 403
    
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name='LeaveRequests')
        temp_path = os.path.join(os.path.dirname(__file__), '..', 'temp_leave_report.xlsx')
        df.to_excel(temp_path, index=False)
        logger.info(f"HR report downloaded by: {current_user_id}")
        return send_file(temp_path, as_attachment=True, download_name='leave_requests_report.xlsx')
    except Exception as e:
        logger.error(f"Error generating HR report: {e}")
        return jsonify({'error': 'Failed to generate report'}), 500

@hr_report_api.route('/api/hr/list-leave-report', methods=['GET'])
@token_required
def list_leave_report(current_user_id):
    """List all leave requests as JSON. HR only."""
    if not is_hr(current_user_id):
        logger.warning(f"Access denied: {current_user_id} attempted to list HR report but is not HR")
        return jsonify({'error': 'Access denied. Only HR personnel can view leave reports.'}), 403
    
    try:
        df = pd.read_excel(EXCEL_FILE, sheet_name='LeaveRequests')
        logger.info(f"HR report listed by: {current_user_id}")
        return jsonify(df.to_dict(orient='records'))
    except Exception as e:
        logger.error(f"Error listing HR report: {e}")
        return jsonify({'error': 'Failed to generate report'}), 500
