from flask import Flask
from config import Config
from extensions import db, login_manager

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    login_manager.init_app(app)

    from routes_web import web_bp
    from routes_api import api_bp

    app.register_blueprint(web_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    @login_manager.user_loader
    def load_user(user_id):
        from models import User
        return User.query.get(int(user_id))

    with app.app_context():
        db.create_all()
        from models import User, SystemSetting, Tag
        from werkzeug.security import generate_password_hash
        
        if not User.query.filter_by(email='admin@leumi.co.il').first():
            hashed = generate_password_hash('admin', method='pbkdf2:sha256')
            admin = User(email='admin@leumi.co.il', name='System Admin', password_hash=hashed, role='Admin')
            db.session.add(admin)
        
        default_settings = {
            'sla_critical_hours': '1', 'sla_high_hours': '4',
            'sla_medium_hours': '24', 'sla_low_hours': '48',
            'smtp_server': '127.0.0.1', 'smtp_port': '25', 'smtp_user': '', 'smtp_pass': '', 'smtp_tls': 'false'
        }
        for k, v in default_settings.items():
            if not SystemSetting.query.filter_by(key=k).first(): db.session.add(SystemSetting(key=k, value=v))
        if Tag.query.count() == 0:
            db.session.add_all([Tag(name='DB Issue', color='#ef4444'), Tag(name='Server', color='#8b5cf6'), Tag(name='UI/UX', color='#0ea5e9')])
        db.session.commit()

    return app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
