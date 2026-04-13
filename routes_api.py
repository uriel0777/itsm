from flask import Blueprint, request, jsonify, url_for
from flask_login import login_required, current_user
import uuid
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from extensions import db
from models import User, Invite, SystemSetting, Tag, Asset, Ticket

api_bp = Blueprint('api', __name__)

def send_email_invite(to_email, invite_url):
    sets = {s.key: s.value for s in SystemSetting.query.all()}
    if not sets.get('smtp_server'):
        return False, "SMTP server not configured."
        
    try:
        msg = MIMEMultipart()
        msg['From'] = sets.get('smtp_user')
        msg['To'] = to_email
        msg['Subject'] = "You have been invited to Leumi ITSM"
        msg.attach(MIMEText(f"Hello, you have been invited. Click here to join: {invite_url}", 'html'))
        
        server = smtplib.SMTP(sets.get('smtp_server'), int(sets.get('smtp_port')))
        server.ehlo()
        if sets.get('smtp_tls') == 'true': server.starttls()
        server.login(sets.get('smtp_user'), sets.get('smtp_pass'))
        server.send_message(msg)
        server.quit()
        return True, "Success"
    except Exception as e:
        return False, str(e)

@api_bp.route('/invite', methods=['POST', 'GET'])
@login_required
def manage_invites():
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    if request.method == 'GET':
        return jsonify([{'id': i.id, 'email': i.email, 'role': i.role, 'token': i.token} for i in Invite.query.all()])
        
    data = request.json
    email = data.get('email')
    
    if User.query.filter_by(email=email).first(): return jsonify({'error': 'Email already registered'}), 400
    existing = Invite.query.filter_by(email=email).first()
    if existing: db.session.delete(existing)
        
    token = str(uuid.uuid4())
    new_invite = Invite(email=email, token=token, role=data.get('role', 'Member'))
    db.session.add(new_invite)
    db.session.commit()
    
    url = url_for('web.set_password', token=token, _external=True)
    
    success, msg = send_email_invite(email, url)
    if success:
        return jsonify({'message': 'Invitation created and email sent successfully.', 'url': url})
    else:
        return jsonify({'message': f'Invitation created but email failed: {msg}', 'url': url})

@api_bp.route('/users', methods=['GET'])
@login_required
def get_users(): return jsonify([u.to_dict() for u in User.query.all()])

@api_bp.route('/users/<int:id>', methods=['DELETE', 'PUT'])
@login_required
def handle_users(id):
    if current_user.role != 'Admin' or current_user.id == id: return jsonify({'error': 'Unauthorized'}), 403
    user = User.query.get_or_404(id)
    if request.method == 'DELETE': db.session.delete(user)
    elif request.method == 'PUT': user.role = request.json.get('role', 'Member')
    db.session.commit()
    return jsonify({'success': True})

@api_bp.route('/invite/<int:id>', methods=['DELETE'])
@login_required
def delete_invite(id):
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    inv = Invite.query.get_or_404(id)
    db.session.delete(inv)
    db.session.commit()
    return jsonify({'success': True})

@api_bp.route('/settings', methods=['GET', 'PUT'])
@login_required
def manage_settings():
    if request.method == 'GET': return jsonify({s.key: s.value for s in SystemSetting.query.all()})
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    for key, val in request.json.items():
        s = SystemSetting.query.filter_by(key=key).first()
        if s: s.value = str(val)
        else: db.session.add(SystemSetting(key=key, value=str(val)))
    db.session.commit()
    return jsonify({'success': True})

@api_bp.route('/tags', methods=['GET', 'POST'])
@login_required
def manage_tags():
    if request.method == 'GET': return jsonify([t.to_dict() for t in Tag.query.all()])
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    t = Tag(name=request.json.get('name'), color=request.json.get('color', '#0072CE'))
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201

@api_bp.route('/tags/<int:id>', methods=['DELETE'])
@login_required
def delete_tag(id):
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(Tag.query.get_or_404(id))
    db.session.commit()
    return jsonify({'success': True})

@api_bp.route('/assets', methods=['GET', 'POST'])
@login_required
def manage_assets():
    if request.method == 'GET': return jsonify([a.to_dict() for a in Asset.query.all()])
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    a = Asset(name=request.json.get('name'), ip_target=request.json.get('ip_target'), description=request.json.get('description'), launcher_url=request.json.get('launcher_url'))
    db.session.add(a)
    db.session.commit()
    return jsonify(a.to_dict()), 201

@api_bp.route('/assets/<int:id>', methods=['DELETE'])
@login_required
def delete_asset(id):
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(Asset.query.get_or_404(id))
    db.session.commit()
    return jsonify({'success': True})

@api_bp.route('/tickets', methods=['GET', 'POST'])
@login_required
def tickets():
    if request.method == 'GET': return jsonify([t.to_dict() for t in Ticket.query.order_by(Ticket.created_at.desc()).all()])
    data = request.json
    due = datetime.strptime(data.get('due_date'), '%Y-%m-%d') if data.get('due_date') else None
    
    pri = data.get('priority', 'Medium')
    # Calculate SLA Breach time
    hours_setting = f"sla_{pri.lower()}_hours"
    setting = SystemSetting.query.filter_by(key=hours_setting).first()
    hours = int(setting.value) if setting and setting.value and setting.value.isdigit() else 24
    breach = datetime.utcnow() + timedelta(hours=hours)

    t = Ticket(title=data.get('title'), description=data.get('description', ''), priority=pri,
        status=data.get('status', 'New'), task_type=data.get('task_type', 'Short-term'), due_date=due, assignee_id=data.get('assignee_id', None),
        sla_breach_time=breach)
    if data.get('tag_ids'): t.tags.extend(Tag.query.filter(Tag.id.in_(data['tag_ids'])).all())
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201

@api_bp.route('/tickets/<int:id>', methods=['PUT', 'DELETE'])
@login_required
def single_ticket(id):
    ticket = Ticket.query.get_or_404(id)
    if request.method == 'DELETE':
        db.session.delete(ticket)
        db.session.commit()
        return jsonify({'success': True})
    data = request.json
    if 'status' in data: ticket.status = data['status']
    if 'assignee_id' in data: ticket.assignee_id = data['assignee_id'] if data['assignee_id'] else None
    if 'priority' in data: 
        ticket.priority = data['priority']
        # Recalculate SLA on priority change?
        hours_setting = f"sla_{ticket.priority.lower()}_hours"
        setting = SystemSetting.query.filter_by(key=hours_setting).first()
        hours = int(setting.value) if setting and setting.value and setting.value.isdigit() else 24
        ticket.sla_breach_time = ticket.created_at + timedelta(hours=hours)

    if 'task_type' in data: ticket.task_type = data['task_type']
    if 'due_date' in data and data['due_date']: ticket.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d')
    if 'tag_ids' in data:
        ticket.tags.clear()
        if data['tag_ids']: ticket.tags.extend(Tag.query.filter(Tag.id.in_(data['tag_ids'])).all())
    db.session.commit()
    return jsonify(ticket.to_dict())

@api_bp.route('/stats', methods=['GET'])
@login_required
def get_stats():
    tickets = Ticket.query.all()
    bs = {'New': 0, 'In Progress': 0, 'Resolved': 0}
    ba = {}
    for t in tickets:
        bs[t.status] = bs.get(t.status, 0) + 1
        name = t.assignee.name if t.assignee else 'Unassigned'
        ba[name] = ba.get(name, 0) + 1
    return jsonify({'status': bs, 'assignee': ba, 'total': len(tickets)})
