from flask import Flask, request, jsonify
import httpx
import os
from datetime import datetime, timedelta

app = Flask(__name__)

# Airtable config
AIRTABLE_API_KEY = os.environ.get('AIRTABLE_API_KEY')
AIRTABLE_BASE_ID = 'app8CI7NAZqhQ4G1Y'
AIRTABLE_PROJECTS_TABLE = 'Projects'


def get_client_projects(client_code):
    """Fetch all active projects for a client from Airtable"""
    if not AIRTABLE_API_KEY:
        return [], []
    
    try:
        headers = {
            'Authorization': f'Bearer {AIRTABLE_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Map client codes to full client names for filtering
        client_map = {
            'ONE': 'One NZ',
            'ONS': 'One NZ (Simplification)',
            'SKY': 'Sky',
            'TOW': 'Tower',
            'FIS': 'Fisher Funds',
            'FST': 'Firestop',
            'HUN': 'Hunch',
            'EON': 'Eon Fibre',
            'LAB': 'Labour',
            'OTH': 'Other'
        }
        
        # Get display name for email header, use code if not mapped
        display_name = client_map.get(client_code, client_code)
        
        # Filter using FIND to match client codes that START with the code
        # This catches "One NZ (Marketing)" and "One NZ (Simplification)" for ONE
        filter_formula = f"AND(FIND('{client_code}', {{Job Number}})=1, OR({{Status}}='In Progress', {{Status}}='On Hold'))"
        
        url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_PROJECTS_TABLE}"
        params = {'filterByFormula': filter_formula}
        
        response = httpx.get(url, headers=headers, params=params, timeout=30.0)
        response.raise_for_status()
        
        records = response.json().get('records', [])
        
        active_projects = []
        for record in records:
            fields = record.get('fields', {})
            active_projects.append({
                'job_number': fields.get('Job Number', ''),
                'job_name': fields.get('Project Name', ''),
                'description': fields.get('Description', ''),
                'stage': fields.get('Stage', ''),
                'status': fields.get('Status', ''),
                'with_client': fields.get('With Client?', False),
                'latest_update': fields.get('Latest Update', ''),
                'update_due': fields.get('Update Due', ''),
                'live_date': fields.get('Live Date', '')
            })
        
        # Now get recently completed projects (Status = Completed, Status Changed in last 6 weeks)
        six_weeks_ago = (datetime.now() - timedelta(days=42)).strftime('%Y-%m-%d')
        completed_filter = f"AND(FIND('{client_code}', {{Job Number}})=1, {{Status}}='Completed', IS_AFTER({{Status Changed}}, '{six_weeks_ago}'))"
        
        completed_params = {'filterByFormula': completed_filter, 'sort[0][field]': 'Status Changed', 'sort[0][direction]': 'desc'}
        completed_response = httpx.get(url, headers=headers, params=completed_params, timeout=30.0)
        completed_response.raise_for_status()
        
        completed_records = completed_response.json().get('records', [])
        
        completed_projects = []
        for record in completed_records:
            fields = record.get('fields', {})
            completed_projects.append({
                'job_number': fields.get('Job Number', ''),
                'job_name': fields.get('Project Name', ''),
                'description': fields.get('Description', '')
            })
        
        return active_projects, completed_projects, display_name
        
    except Exception as e:
        print(f"Airtable error: {e}")
        return [], [], client_code


def build_wip_email(client_name, projects, completed_projects):
    """Build HTML email for WIP report"""
    
    # Sort projects into categories
    with_us = [p for p in projects if p['status'] == 'In Progress' and not p['with_client']]
    with_you = [p for p in projects if p['status'] == 'In Progress' and p['with_client']]
    on_hold = [p for p in projects if p['status'] == 'On Hold']
    
    # Build project rows
    def project_row(project, show_stage=True):
        stage_html = f"<span style='background-color: #f0f0f0; padding: 2px 8px; border-radius: 3px; font-size: 12px;'>{project['stage']}</span>" if show_stage and project['stage'] else ""
        live_date = f"<br><span style='color: #666; font-size: 12px;'>Live: {project['live_date']}</span>" if project['live_date'] else ""
        
        return f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #eee;">
                <strong style="color: #ED1C24;">{project['job_number']}</strong> - {project['job_name']}<br>
                <span style="color: #666; font-size: 14px;">{project['description']}</span>
                {live_date}
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">
                {stage_html}
            </td>
        </tr>
        """
    
    def section(title, emoji, project_list, show_stage=True):
        if not project_list:
            return ""
        rows = "".join([project_row(p, show_stage) for p in project_list])
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom: 24px;">
            <tr>
                <td colspan="2" style="padding: 12px; background-color: #f8f8f8; border-left: 4px solid #ED1C24;">
                    <strong>{emoji} {title}</strong> <span style="color: #666;">({len(project_list)} projects)</span>
                </td>
            </tr>
            {rows}
        </table>
        """
    
    def completed_section(completed_list):
        if not completed_list:
            return ""
        
        items = "".join([
            f"<li style='margin-bottom: 8px;'><strong style='color: #ED1C24;'>{p['job_number']}</strong> - {p['job_name']} - {p['description']}</li>"
            for p in completed_list
        ])
        
        return f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="margin-top: 32px; border-top: 2px solid #eee; padding-top: 24px;">
            <tr>
                <td style="padding: 12px;">
                    <strong>✅ RECENTLY COMPLETED</strong>
                    <ul style="margin-top: 12px; padding-left: 20px; color: #666;">
                        {items}
                    </ul>
                </td>
            </tr>
        </table>
        """
    
    today = datetime.now().strftime('%d %B %Y')
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="IE=edge">
    <!--[if mso]>
    <style type="text/css">
        table {{border-collapse: collapse; border-spacing: 0; margin: 0;}}
        div, td {{padding: 0;}}
        div {{margin: 0 !important;}}
    </style>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
    <style>
        @media screen and (max-width: 600px) {{
            .wrapper {{
                width: 100% !important;
                padding: 12px !important;
            }}
            .header-banner {{
                padding: 16px !important;
            }}
        }}
    </style>
</head>
<body style="margin: 0; padding: 0; font-family: Calibri, Arial, sans-serif; font-size: 15px; line-height: 1.5; color: #333; background-color: #ffffff; width: 100% !important; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%;">
    
    <!-- Wrapper table for full width background -->
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: #ffffff;">
        <tr>
            <td align="center" style="padding: 20px 0;">
                
                <!-- Content table -->
                <table class="wrapper" width="600" cellpadding="0" cellspacing="0" border="0" style="max-width: 600px; width: 100%;">
        
                    <!-- Header -->
                    <tr>
                        <td class="header-banner" style="padding: 20px; background-color: #ED1C24;">
                            <h1 style="margin: 0; color: #ffffff; font-size: 24px; font-weight: bold;">Work in Progress</h1>
                            <p style="margin: 8px 0 0 0; color: #ffffff; opacity: 0.9;">{client_name} | {today}</p>
                        </td>
                    </tr>
        
                    <!-- Content -->
                    <tr>
                        <td style="padding: 24px 20px;">
                            {section("WITH US", "🔨", with_us)}
                            {section("WITH YOU", "📤", with_you)}
                            {section("ON HOLD", "⏸️", on_hold, show_stage=False)}
                            {completed_section(completed_projects)}
                        </td>
                    </tr>
        
                    <!-- Footer -->
                    <tr>
                        <td style="padding: 20px; border-top: 1px solid #eee; color: #999; font-size: 12px;">
                            Generated by Dot @ Hunch
                        </td>
                    </tr>
        
                </table>
                
            </td>
        </tr>
    </table>
    
</body>
</html>
"""
    
    return html


# ===================
# WIP ENDPOINT
# ===================
@app.route('/wip', methods=['POST'])
def wip():
    """Generate WIP email HTML for a client"""
    try:
        data = request.get_json()
        client_code = data.get('clientCode', '')
        
        if not client_code:
            return jsonify({'error': 'No client code provided'}), 400
        
        # Get projects from Airtable
        active_projects, completed_projects, display_name = get_client_projects(client_code)
        
        if not active_projects and not completed_projects:
            return jsonify({
                'error': 'No projects found',
                'clientCode': client_code
            }), 404
        
        # Build HTML
        html = build_wip_email(display_name, active_projects, completed_projects)
        
        return jsonify({
            'clientCode': client_code,
            'clientName': display_name,
            'activeCount': len(active_projects),
            'completedCount': len(completed_projects),
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
