from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from models import User, Invite

web_bp = Blueprint('web', __name__)

@web_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('web.index'))
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            login_user(user)
            return redirect(url_for('web.index'))
        flash('Invalid email or password', 'error')
    return render_template('login.html')

@web_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('web.login'))

@web_bp.route('/set-password/<token>', methods=['GET', 'POST'])
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
        return redirect(url_for('web.index'))
    return render_template('set_password.html', email=invite.email)

@web_bp.route('/')
@login_required
def index(): return render_template('index.html', user=current_user)

@web_bp.route('/analytics')
@login_required
def analytics(): return render_template('analytics.html', user=current_user)

@web_bp.route('/settings')
@login_required
def settings():
    if current_user.role != 'Admin': return redirect(url_for('web.index'))
    return render_template('settings.html', user=current_user)

@web_bp.route('/assets')
@login_required
def assets(): return render_template('assets.html', user=current_user)
