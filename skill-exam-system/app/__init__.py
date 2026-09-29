"""职业技能实操预约评分系统 - 应用工厂"""
import os
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message = '请先登录'
login_manager.login_message_category = 'warning'


def create_app(config=None):
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
    basedir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
        'DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'exam_system.db'))
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    if config:
        app.config.update(config)

    db.init_app(app)
    login_manager.init_app(app)

    from . import models  # noqa: F401  (确保模型已注册)
    from .auth import auth_bp
    from .candidate import candidate_bp
    from .examiner import examiner_bp
    from .admin import admin_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(candidate_bp, url_prefix='/candidate')
    app.register_blueprint(examiner_bp, url_prefix='/examiner')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    @app.route('/')
    def index():
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        if current_user.role == 'examiner':
            return redirect(url_for('examiner.dashboard'))
        return redirect(url_for('candidate.dashboard'))

    return app
