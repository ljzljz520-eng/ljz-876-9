"""认证与权限控制"""
from functools import wraps
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort)
from flask_login import login_user, logout_user, login_required, current_user
from . import db
from .models import User, ROLE_CANDIDATE

auth_bp = Blueprint('auth', __name__)


def role_required(*roles):
    """限制访问角色的装饰器"""
    def decorator(f):
        @wraps(f)
        @login_required
        def wrapper(*args, **kwargs):
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorator


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('用户名或密码错误', 'danger')
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """考生自助注册（考评员/管理员账号由管理员创建）"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        name = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        password = request.form.get('password', '')
        password2 = request.form.get('password2', '')

        if not all([username, name, password]):
            flash('请填写完整信息', 'danger')
        elif len(password) < 6:
            flash('密码长度至少6位', 'danger')
        elif password != password2:
            flash('两次输入的密码不一致', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('该用户名已被注册', 'danger')
        else:
            user = User(username=username, name=name, phone=phone,
                        role=ROLE_CANDIDATE)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('注册成功，请登录', 'success')
            return redirect(url_for('auth.login'))
    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('已退出登录', 'info')
    return redirect(url_for('auth.login'))
