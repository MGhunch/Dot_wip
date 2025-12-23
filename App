from flask import Flask, request, jsonify
import httpx
import os
from datetime import datetime

app = Flask(__name__)

# Airtable config
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = 'app8CI7NAZqhQ4G1Y'
AIRTABLE_PROJECTS_TABLE = 'Projects'


def get_client_projects(client_name):
    """Fetch all active projects for a client from Airtable"""
    if not AIRTABLE_API_KEY:
        return []
    
    try:
        headers = {
            'Authorization': f'Bearer {AIRTABLE_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Filter by client and active status
        filter_formula = f"AND({{Client}}='{client_name}', OR({{Status}}='In Progress', {{Status}}='On Hold'))"
        
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
                'live_date': fields.get('Live Date', '')
            })
        
        return projects
        
    except Exception as e:
        print(f"Error fetching projects: {e}")
        return []


def build_job_html(job):
    """Build HTML block for a single job"""
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
          <tr><td style="padding: 2px 10px 2px 0;"><strong>Stage:</strong></td><td>{job['stage']}</td></tr>
          <tr><td style="padding: 2px 10px 2px 0;"><strong>Update:</strong></td><td>{job['update_summary']}</td></tr>
          <tr><td style="padding: 2px 10px 2px 0;"><strong>Update due:</strong></td><td>{job['update_due']}</td></tr>
          <tr><td style="padding: 2px 10px 2px 0;"><strong>Live:</strong></td><td>{job['live_date']}</td></tr>
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


def build_wip_email(client_name, projects):
    """Build complete WIP email HTML"""
    today = datetime.now().strftime('%d %B %Y')
    
    # Sort projects into categories
    with_us = [p for p in projects if p['status'] == 'In Progress' and not p['with_client']]
    with_you = [p for p in projects if p['status'] == 'In Progress' and p['with_client']]
    on_hold = [p for p in projects if p['status'] == 'On Hold']
    
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
        <span style="font-size: 28px; font-weight: bold; color: #ED1C24;">HUNCH — WIP</span>
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
        client_name = data.get('client', '')
        
        if not client_name:
            return jsonify({'error': 'No client name provided'}), 400
        
        # Get projects from Airtable
        projects = get_client_projects(client_name)
        
        if not projects:
            return jsonify({
                'error': 'No active projects found',
                'client': client_name
            }), 404
        
        # Build HTML
        html = build_wip_email(client_name, projects)
        
        return jsonify({
            'client': client_name,
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
