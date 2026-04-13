from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from extensions import db
from models import Ticket, SystemSetting

webhook_bp = Blueprint('webhook', __name__)

@webhook_bp.route('/api/webhooks/alert', methods=['POST'])
def receive_alert():
    """
    Expects JSON payload from a monitoring tool (Nagios, Prometheus):
    {
      "source": "Zabbix",
      "alert_title": "High CPU on DB-01",
      "description": "CPU usage exceeded 95% for 10m",
      "priority": "High"
    }
    """
    data = request.json
    if not data or 'alert_title' not in data:
        return jsonify({'error': 'Invalid payload'}), 400

    title = f"[{data.get('source', 'Monitor')}] {data['alert_title']}"
    pri = data.get('priority', 'High')
    
    # Calculate SLA Breach time
    # This requires looking up `sla_{priority.lower()}_hours` from settings or defaulting
    hours_setting = f"sla_{pri.lower()}_hours"
    setting = SystemSetting.query.filter_by(key=hours_setting).first()
    hours = int(setting.value) if setting and setting.value and setting.value.isdigit() else 4
    
    breach = datetime.utcnow() + timedelta(hours=hours)

    t = Ticket(
        title=title,
        description=data.get('description', 'Auto-generated via Webhook.'),
        priority=pri,
        status='New',
        task_type='Short-term',
        sla_breach_time=breach
    )
    
    db.session.add(t)
    db.session.commit()
    
    return jsonify({'success': True, 'ticket_id': t.id, 'sla_breach': breach.isoformat()}), 201
