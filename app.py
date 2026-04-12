from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os
import uuid
from datetime import datetime
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
    
    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'ip_target': self.ip_target, 'description': self.description}

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
    due_date = db.Column(db.DateTime, nullable=True)
    assignee_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    assignee = db.relationship('User', backref=db.backref('tickets', lazy=True))
    tags = db.relationship('Tag', secondary=ticket_tags, lazy='subquery', backref=db.backref('tickets', lazy=True))

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'description': self.description,
            'priority': self.priority, 'status': self.status, 'task_type': self.task_type,
            'due_date': self.due_date.strftime('%Y-%m-%d') if self.due_date else None,
            'assignee': self.assignee.name if self.assignee else None, 'assignee_id': self.assignee_id,
            'tags': [tag.to_dict() for tag in self.tags],
            'created_at': self.created_at.strftime('%Y-%m-%dT%H:%M:%SZ')
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
        db.session.add_all([Tag(name='DB Issue', color='#ef4444'), Tag(name='Server', color='#8b5cf6'), Tag(name='UI/UX', color='#0ea5e9')])
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
    a = Asset(name=request.json.get('name'), ip_target=request.json.get('ip_target'), description=request.json.get('description'))
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
        status=data.get('status', 'New'), task_type=data.get('task_type', 'Short-term'), due_date=due, assignee_id=data.get('assignee_id', None))
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
