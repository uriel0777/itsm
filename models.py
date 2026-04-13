from extensions import db
from flask_login import UserMixin
from datetime import datetime

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
    launcher_url = db.Column(db.String(255), nullable=True) # e.g., rdp://192.168.1.1
    
    def to_dict(self):
        return {'id': self.id, 'name': self.name, 'ip_target': self.ip_target, 'description': self.description, 'launcher_url': self.launcher_url}

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
    sla_breach_time = db.Column(db.DateTime, nullable=True) # SLA Tracking
    
    assignee = db.relationship('User', backref=db.backref('tickets', lazy=True))
    tags = db.relationship('Tag', secondary=ticket_tags, lazy='subquery', backref=db.backref('tickets', lazy=True))

    def evaluate_sla(self):
        if not self.sla_breach_time or self.status == 'Resolved':
            return "OK"
        now = datetime.utcnow()
        if now > self.sla_breach_time:
            return "Breached"
        if (self.sla_breach_time - now).total_seconds() < 3600:
            return "Warning"
        return "OK"

    def to_dict(self):
        return {
            'id': self.id, 'title': self.title, 'description': self.description,
            'priority': self.priority, 'status': self.status, 'task_type': self.task_type,
            'due_date': self.due_date.strftime('%Y-%m-%d') if self.due_date else None,
            'assignee': self.assignee.name if self.assignee else None, 'assignee_id': self.assignee_id,
            'tags': [tag.to_dict() for tag in self.tags],
            'created_at': self.created_at.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'sla_breach_time': self.sla_breach_time.strftime('%Y-%m-%dT%H:%M:%SZ') if self.sla_breach_time else None,
            'sla_status': self.evaluate_sla()
        }
