from flask import Flask, request, jsonify
import httpx
import os
from datetime import datetime

app = Flask(__name__)

# Airtable config
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = 'app8CI7NAZqhQ4G1Y'
AIRTABLE_PROJECTS_TABLE = 'Projects'
AIRTABLE_CLIENTS_TABLE = 'Clients'


def format_date(date_str):
    """Format date string to 'D MMM' format (e.g., '5 Jan')"""
    if not date_str:
        return ''
    try:
        # Handle various date formats
        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y']:
            try:
                date_obj = datetime.strptime(date_str, fmt)
                return date_obj.strftime('%-d %b')
            except ValueError:
                continue
        return date_str  # Return original if can't parse
    except:
        return date_str


def get_client_info(client_code):
    """Fetch client info including WIP header image from Clients table"""
    if not AIRTABLE_API_KEY:
        return None
    
    try:
        headers = {
            'Authorization': f'Bearer {AIRTABLE_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Find client by code
        filter_formula = f"{{Client code}}='{client_code}'"
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_CLIENTS_TABLE}"
        params = {'filterByFormula': filter_formula}
        
        response = httpx.get(url, headers=headers, params=params, timeout=30.0)
        response.raise_for_status()
        
        records = response.json().get('records', [])
        
        if not records:
            return None
        
        fields = records[0].get('fields', {})
        
        # Get WIP header image URL (Airtable attachments are arrays)
        wip_header = fields.get('Wip headers', [])
        header_url = wip_header[0].get('url', '') if wip_header else ''
        
        return {
            'client_name': fields.get('Client', ''),
            'client_code': fields.get('Client code', ''),
            'header_url': header_url
        }
        
    except Exception as e:
        print(f"Error fetching client info: {e}")
        return None


def get_client_projects(client_name):
    """Fetch all active projects for a client from Airtable"""
    if not AIRTABLE_API_KEY:
        return []
    
    try:
        headers = {
            'Authorization': f'Bearer {AIRTABLE_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Filter by client code (Job Number prefix) and active status
        filter_formula = f"AND(FIND('{client_name}', {{Job Number}})=1, OR({{Status}}='In Progress', {{Status}}='On Hold'))"
        
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_PROJECTS_TABLE}"
        params = {'filterByFormula': filter_formula}
        
        response = httpx.get(url, headers=headers, params=params, timeout=30.0)
        response.raise_for_status()
        
        records = response.json().get('records', [])
        
        projects = []
        for record in records:
            fields = record.get('fields', {})
            projects.append({
                'job_number': fields.get('Job Number', ''),
                'job_name': fields.get('Project Name', ''),
                'description': fields.get('Description', ''),
                'stage': fields.get('Stage', ''),
                'status': fields.get('Status', ''),
                'with_client': fields.get('With Client?', False),
                'update_summary': fields.get('Latest Update', ''),
                'update_due': fields.get('Update Due', ''),
                'live_date': fields.get('Live Date', ''),
                'client': fields.get('Client', ''),
                'project_owner': fields.get('Project Owner', '')
            })
        
        return projects
        
    except Exception as e:
        print(f"Error fetching projects: {e}")
        return []


def build_job_html(job):
    """Build HTML block for a single job"""
    update_due = format_date(job['update_due'])
    live_date = format_date(job['live_date']) if job['live_date'] not in ['TBC', 'tbc', ''] else job['live_date']
    
    return f'''
    <tr>
      <td style="padding: 15px 20px; border-bottom: 1px solid #eee;">
        <p style="margin: 0 0 5px 0; font-size: 16px; font-weight: bold; color: #333;">
          {job['job_number']} — {job['job_name']}
        </p>
        <p style="margin: 0 0 10px 0; font-size: 14px; color: #666; line-height: 1.4;">
          {job['description']}
        </p>
        <table cellpadding="0" cellspacing="0" style="font-size: 13px; color: #888;">
          <tr><td style="padding: 2px 10px 2px 0;"><strong>Owner:</strong></td><td>{job['project_owner']}</td></tr>
          <tr><td style="padding: 2px 10px 2px 0;"><strong>Update:</strong></td><td>{job['update_summary']}</td></tr>
          <tr><td style="padding: 2px 10px 2px 0;"><strong>Stage:</strong></td><td>{job['stage']}</td></tr>
          <tr><td style="padding: 2px 10px 2px 0;"><strong>Due on:</strong></td><td>{update_due}</td></tr>
          <tr><td style="padding: 2px 10px 2px 0;"><strong>Live by:</strong></td><td>{live_date}</td></tr>
        </table>
      </td>
    </tr>'''


def build_section_html(title, jobs, color="#ED1C24"):
    """Build HTML section with header and jobs"""
    if not jobs:
        return ''
    
    section = f'''
    <tr>
      <td style="padding: 20px 20px 0 20px;">
        <div style="background-color: {color}; color: #ffffff; padding: 8px 15px; font-size: 14px; font-weight: bold; border-radius: 3px;">
          {title}
        </div>
      </td>
    </tr>'''
    
    for job in jobs:
        section += build_job_html(job)
    
    return section


def build_wip_email(client_name, projects, header_url=''):
    """Build complete WIP email HTML"""
    today = datetime.now().strftime('%d %B %Y')
    
    # Sort projects into categories
    with_us = [p for p in projects if p['status'] == 'In Progress' and not p['with_client']]
    with_you = [p for p in projects if p['status'] == 'In Progress' and p['with_client']]
    on_hold = [p for p in projects if p['status'] == 'On Hold']
    
    # Build header - use image if available, otherwise text
    if header_url:
        header_content = f'''<img src="{header_url}" width="600" style="width: 100%; max-width: 600px; height: auto; display: block;">'''
    else:
        header_content = f'''<span style="font-size: 28px; font-weight: bold; color: #ED1C24;">HUNCH — WIP</span>'''
    
    html = f'''<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 20px; font-family: Arial, sans-serif; background-color: #f5f5f5;">
  
  <table width="100%" cellpadding="0" cellspacing="0" style="max-width: 600px; margin: 0 auto; background-color: #ffffff;">
    
    <!-- Header -->
    <tr>
      <td style="border-bottom: 4px solid #ED1C24; padding: 20px;">
        {header_content}
        <p style="margin: 15px 0 0 0; font-size: 22px; font-weight: bold; color: #333;">{client_name}</p>
        <p style="margin: 5px 0 0 0; font-size: 12px; color: #999;">{today}</p>
      </td>
    </tr>
    
    {build_section_html("WITH US", with_us)}
    {build_section_html("WITH YOU", with_you)}
    {build_section_html("ON HOLD", on_hold, "#999999")}
    
    <!-- Footer -->
    <tr>
      <td style="padding: 25px 20px; border-top: 1px solid #eee; text-align: center;">
        <p style="margin: 0; font-size: 12px; color: #999;">WIP updated by Dot@hunch</p>
      </td>
    </tr>
    
  </table>
  
</body>
</html>'''
    
    return html


# ===================
# WIP ENDPOINT
# ===================
@app.route('/wip', methods=['POST'])
def wip():
    """Generate WIP email HTML for a client"""
    try:
        data = request.get_json()
        client_code = data.get('clientCode', data.get('client', ''))
        
        if not client_code:
            return jsonify({'error': 'No client code provided'}), 400
        
        # Get projects from Airtable
        projects = get_client_projects(client_code)
        
        if not projects:
            return jsonify({
                'error': 'No active projects found',
                'clientCode': client_code
            }), 404
        
        # Get client info (including header image) from Clients table
        client_info = get_client_info(client_code)
        header_url = client_info.get('header_url', '') if client_info else ''
        
        # Get client name from first project (for the header)
        client_name = projects[0].get('client', client_code)
        
        # Build HTML
        html = build_wip_email(client_name, projects, header_url)
        
        return jsonify({
            'clientCode': client_code,
            'clientName': client_name,
            'projectCount': len(projects),
            'html': html
        })
        
    except Exception as e:
        return jsonify({
            'error': 'Internal server error',
            'details': str(e)
        }), 500


# ===================
# HEALTH CHECK
# ===================
@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'Dot WIP',
        'endpoints': ['/wip', '/health']
    })


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
