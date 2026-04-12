from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import uuid
from datetime import datetime
import json
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)

# Config
BASE_DIR = os.path.abspath(os.path.dirname(__name__))
app.config['SECRET_KEY'] = 'dev_secret_key_leumi_itsm'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'itsm.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- Models ---
class SystemSetting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.String(255), nullable=True)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=True)
    role = db.Column(db.String(50), default='Member')

    def to_dict(self):
        return {'id': self.id, 'email': self.email, 'name': self.name, 'role': self.role}

class Invite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    token = db.Column(db.String(120), unique=True, nullable=False)
    role = db.Column(db.String(50), default='Member')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    color = db.Column(db.String(20), default='#0072CE')
    
    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'color': self.color}

class Asset(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    ip_target = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    asset_type = db.Column(db.String(50), default='RDP')
    expiry_date = db.Column(db.DateTime, nullable=True)
    
    def to_dict(self):
        return {
            'id': self.id, 'name': self.name, 'ip_target': self.ip_target, 
            'description': self.description, 'asset_type': self.asset_type,
            'expiry_date': self.expiry_date.strftime('%Y-%m-%d') if self.expiry_date else None
        }

class Runbook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    alert_pattern = db.Column(db.String(255), nullable=False)
    resolution_script = db.Column(db.Text, nullable=True)
    guide = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {'id': self.id, 'alert_pattern': self.alert_pattern, 'resolution_script': self.resolution_script, 'guide': self.guide}

ticket_tags = db.Table('ticket_tags',
    db.Column('ticket_id', db.Integer, db.ForeignKey('ticket.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True)
)

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    priority = db.Column(db.String(20), nullable=False, default='Medium') 
    status = db.Column(db.String(20), nullable=False, default='New') 
    task_type = db.Column(db.String(50), nullable=False, default='Short-term') 
    source = db.Column(db.String(50), default='User')
    payload = db.Column(db.Text, nullable=True)
    due_date = db.Column(db.DateTime, nullable=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    runbook_id = db.Column(db.Integer, db.ForeignKey('runbook.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime, nullable=True)
    
    assignee = db.relationship('User', backref=db.backref('tickets', lazy=True))
    runbook = db.relationship('Runbook', backref=db.backref('tickets', lazy=True))
    tags = db.relationship('Tag', secondary=ticket_tags, lazy='subquery', backref=db.backref('tickets', lazy=True))

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'description': self.description,
            'priority': self.priority, 'status': self.status, 'task_type': self.task_type,
            'source': self.source, 'payload': self.payload,
            'due_date': self.due_date.strftime('%Y-%m-%d') if self.due_date else None,
            'assignee': self.assignee.name if self.assignee else None, 'assignee_id': self.assignee_id,
            'runbook': self.runbook.to_dict() if self.runbook else None,
            'tags': [tag.to_dict() for tag in self.tags],
            'created_at': self.created_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'resolved_at': self.resolved_at.strftime('%Y-%m-%dT%H:%M:%SZ') if self.resolved_at else None
        }

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# DB setup
os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
with app.app_context():
    db.create_all()
    if not User.query.filter_by(email='admin@leumi.co.il').first():
        hashed = generate_password_hash('admin', method='pbkdf2:sha256')
        admin = User(email='admin@leumi.co.il', name='System Admin', password_hash=hashed, role='Admin')
        db.session.add(admin)
    default_settings = {
        'sla_critical_hours': '1', 'sla_high_hours': '4',
        'sla_medium_hours': '24', 'sla_low_hours': '48',
        'smtp_server': '', 'smtp_port': '587', 'smtp_user': '', 'smtp_pass': '', 'smtp_tls': 'true'
    }
    for k, v in default_settings.items():
        if not SystemSetting.query.filter_by(key=k).first(): db.session.add(SystemSetting(key=k, value=v))
    if Tag.query.count() == 0:
        db.session.add_all([Tag(name='DB Issue', color='#ef4444'), Tag(name='Server', color='#8b5cf6'), Tag(name='UI/UX', color='#0ea5e9'), Tag(name='Auto-generated', color='#f59e0b')])
    
    if Asset.query.count() == 0:
        initial_assets = [
            # EKSA
            Asset(name='Banker Reply Indicator', ip_target='https://bll-crm-prd.hq.il.leumi/banker-reply-indicator/vitality', asset_type='URL', description='Red Bubble'),
            Asset(name='Banker Reply Update', ip_target='https://bll-crm-prd.hq.il.leumi/banker-reply-update/vitality', asset_type='URL'),
            Asset(name='OpenAI Chat Service', ip_target='https://bll-openai-prd.hq.il.leumi/openai/vitality', asset_type='URL'),
            Asset(name='Retrieval Transaction', ip_target='https://bll-crm-prd.hq.il.leumi/retrieval-transaction/vitality', asset_type='URL'),
            Asset(name='CRM Events Manager', ip_target='https://bll-crm-prd.hq.il.leumi/crm-events-manager/vitality', asset_type='URL'),
            Asset(name='OCR Pub', ip_target='https://bll-stringout-prd.hq.il.leumi/ocr-pub/vitality', asset_type='URL'),
            Asset(name='OCR Data Management', ip_target='https://bll-stringout-prd.hq.il.leumi/ocr-data-management/vitality', asset_type='URL'),
            
            # MC Servers
            Asset(name='MC Node 1', ip_target='10.235.143.131', asset_type='RDP'),
            Asset(name='MC Node 2', ip_target='10.235.143.132', asset_type='RDP'),
            Asset(name='MC Node 3', ip_target='10.235.143.140', asset_type='RDP'),
            Asset(name='MC Node 4', ip_target='10.235.143.141', asset_type='RDP'),
            Asset(name='MC Node 5', ip_target='10.235.143.146', asset_type='RDP'),
            Asset(name='MC Node 6', ip_target='10.235.143.147', asset_type='RDP'),
            Asset(name='MC Node 7', ip_target='10.235.143.152', asset_type='RDP'),
            Asset(name='MC Node 8', ip_target='10.235.143.153', asset_type='RDP'),

            # SMB Shares
            Asset(name='CRM SF ETL Shared', ip_target='\\\\crmfs\\CRM_SF_ETL\\Informatica\\infa_shared', asset_type='SMB'),
            Asset(name='InfaSrv C Drive', ip_target='\\\\infasrv\\c$', asset_type='SMB'),
            Asset(name='InfaSrv E Drive', ip_target='\\\\infasrv\\e$', asset_type='SMB'),
            Asset(name='Vitality Checker Server', ip_target='\\\\leumisrv1\\Data2\\SFVersions\\VitalityChecker', asset_type='SMB', description='Leumisrv1')
        ]
        db.session.add_all(initial_assets)

    if Runbook.query.count() == 0:
        db.session.add_all([
            Runbook(alert_pattern='.*LOW SPACE.*', guide='1. Connect to the server via Asset Explorer.\n2. Open Disk Cleanup.\n3. Clear Temp folders.', resolution_script='powershell.exe -Command "Remove-Item -Path $env:TEMP\\* -Recurse -Force"'),
            Runbook(alert_pattern='.*Out of Memory.*', guide='1. Check Node usage.\n2. Restart specific node services.', resolution_script='taskkill /F /FI "MEMUSAGE gt 2000000"'),
            Runbook(alert_pattern='.*Legacy Tool Errors.*', guide='1. RDP to leumisrv1.\n2. Check latest logs in \\Data2\\SFVersions\\VitalityChecker\\logs.')
        ])
    
    db.session.commit()

# --- Auth ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid email or password', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/set-password/<token>', methods=['GET', 'POST'])
def set_password(token):
    invite = Invite.query.filter_by(token=token).first()
    if not invite: return "Invalid or expired invitation token.", 400
    if request.method == 'POST':
        password = request.form.get('password')
        name = request.form.get('name')
        new_user = User(email=invite.email, name=name, password_hash=generate_password_hash(password, method='pbkdf2:sha256'), role=invite.role)
        db.session.add(new_user)
        db.session.delete(invite)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('index'))
    return render_template('set_password.html', email=invite.email)

# --- App Routes ---
@app.route('/')
@login_required
def index(): return render_template('index.html', user=current_user)

@app.route('/analytics')
@login_required
def analytics(): return render_template('analytics.html', user=current_user)

@app.route('/settings')
@login_required
def settings():
    if current_user.role != 'Admin': return redirect(url_for('index'))
    return render_template('settings.html', user=current_user)

@app.route('/assets')
@login_required
def assets(): return render_template('assets.html', user=current_user)

# --- APIs ---
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

@app.route('/api/invite', methods=['POST', 'GET'])
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
    
    url = url_for('set_password', token=token, _external=True)
    
    success, msg = send_email_invite(email, url)
    if success:
        return jsonify({'message': 'Invitation created and email sent successfully.', 'url': url})
    else:
        return jsonify({'message': f'Invitation created but email failed: {msg}', 'url': url})

@app.route('/api/users', methods=['GET'])
@login_required
def get_users(): return jsonify([u.to_dict() for u in User.query.all()])

@app.route('/api/users/<int:id>', methods=['DELETE', 'PUT'])
@login_required
def handle_users(id):
    if current_user.role != 'Admin' or current_user.id == id: return jsonify({'error': 'Unauthorized'}), 403
    user = User.query.get_or_404(id)
    if request.method == 'DELETE': db.session.delete(user)
    elif request.method == 'PUT': user.role = request.json.get('role', 'Member')
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/invite/<int:id>', methods=['DELETE'])
@login_required
def delete_invite(id):
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    inv = Invite.query.get_or_404(id)
    db.session.delete(inv)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/settings', methods=['GET', 'PUT'])
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

@app.route('/api/tags', methods=['GET', 'POST'])
@login_required
def manage_tags():
    if request.method == 'GET': return jsonify([t.to_dict() for t in Tag.query.all()])
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    t = Tag(name=request.json.get('name'), color=request.json.get('color', '#0072CE'))
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201

@app.route('/api/tags/<int:id>', methods=['DELETE'])
@login_required
def delete_tag(id):
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(Tag.query.get_or_404(id))
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/assets', methods=['GET', 'POST'])
@login_required
def manage_assets():
    if request.method == 'GET': return jsonify([a.to_dict() for a in Asset.query.all()])
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    a = Asset(name=request.json.get('name'), ip_target=request.json.get('ip_target'), description=request.json.get('description'), asset_type=request.json.get('asset_type', 'RDP'))
    db.session.add(a)
    db.session.commit()
    return jsonify(a.to_dict()), 201

@app.route('/api/assets/<int:id>', methods=['DELETE'])
@login_required
def delete_asset(id):
    if current_user.role != 'Admin': return jsonify({'error': 'Unauthorized'}), 403
    db.session.delete(Asset.query.get_or_404(id))
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/tickets', methods=['GET', 'POST'])
@login_required
def tickets():
    if request.method == 'GET': return jsonify([t.to_dict() for t in Ticket.query.order_by(Ticket.created_at.desc()).all()])
    data = request.json
    due = datetime.strptime(data.get('due_date'), '%Y-%m-%d') if data.get('due_date') else None
    t = Ticket(title=data.get('title'), description=data.get('description', ''), priority=data.get('priority', 'Medium'),
        status=data.get('status', 'New'), task_type=data.get('task_type', 'Short-term'), source=data.get('source', 'User'),
        payload=data.get('payload', ''), due_date=due, assignee_id=data.get('assignee_id', None))
    if data.get('tag_ids'): t.tags.extend(Tag.query.filter(Tag.id.in_(data['tag_ids'])).all())
    db.session.add(t)
    db.session.commit()
    return jsonify(t.to_dict()), 201

@app.route('/api/tickets/<int:id>', methods=['PUT', 'DELETE'])
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
    if 'priority' in data: ticket.priority = data['priority']
    if 'task_type' in data: ticket.task_type = data['task_type']
    if 'due_date' in data and data['due_date']: ticket.due_date = datetime.strptime(data['due_date'], '%Y-%m-%d')
    if 'tag_ids' in data:
        ticket.tags.clear()
        if data['tag_ids']: ticket.tags.extend(Tag.query.filter(Tag.id.in_(data['tag_ids'])).all())
    db.session.commit()
    return jsonify(ticket.to_dict())

@app.route('/api/stats', methods=['GET'])
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

@app.route('/api/webhooks/morning-check', methods=['POST'])
def webhook_morning_check():
    data = request.json
    incident_key = data.get('incident_key', 'Generic Incident')
    status_ind = data.get('status', 'ERROR')
    payload_str = json.dumps(data)
    
    existing_ticket = Ticket.query.filter(Ticket.title == incident_key, Ticket.status != 'Resolved').first()
    
    if status_ind == 'OK':
        if existing_ticket:
            existing_ticket.status = 'Resolved'
            existing_ticket.resolved_at = datetime.utcnow()
            db.session.commit()
            return jsonify({'message': f'Incident {incident_key} resolved automatically.'})
        return jsonify({'message': 'No open incidents found for this key.'})
    else:
        if existing_ticket:
            existing_ticket.payload = payload_str
            db.session.commit()
            return jsonify({'message': 'Updated existing incident payload.'})
            
        t = Ticket(title=incident_key, description=data.get('description', 'Automated Alert'), 
                   priority=data.get('priority', 'High'), source='Webhook', payload=payload_str)
                   
        auto_tag = Tag.query.filter_by(name='Auto-generated').first()
        if auto_tag: t.tags.append(auto_tag)
            
        runbooks = Runbook.query.all()
        for rb in runbooks:
            if re.search(rb.alert_pattern, incident_key, re.IGNORECASE):
                t.runbook_id = rb.id
                break
                
        db.session.add(t)
        db.session.commit()
        return jsonify({'message': f'Incident {incident_key} created successfully.'}), 201

@app.route('/api/runbooks', methods=['GET'])
@login_required
def get_runbooks():
    return jsonify([r.to_dict() for r in Runbook.query.all()])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
