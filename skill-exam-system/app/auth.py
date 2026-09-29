"""用户认证与权限控制"""
import functools
from flask import (Blueprint, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash
from .db import get_db

bp = Blueprint('auth', __name__, url_prefix='/auth')


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            'SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()


def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if g.user is None:
            return redirect(url_for('auth.login'))
        return view(**kwargs)
    return wrapped


def role_required(*roles):
    """限制接口只允许指定角色访问"""
    def decorator(view):
        @functools.wraps(view)
        def wrapped(**kwargs):
            if g.user is None:
                return redirect(url_for('auth.login'))
            if g.user['role'] not in roles:
                flash('无权访问该页面', 'error')
                return redirect(url_for('index'))
            return view(**kwargs)
        return wrapped
    return decorator


@bp.route('/register', methods=['GET', 'POST'])
def register():
    """考生自助注册（考评员/管理员由后台创建）"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        real_name = request.form.get('real_name', '').strip()
        id_card = request.form.get('id_card', '').strip()
        phone = request.form.get('phone', '').strip()
        db = get_db()
        error = None
        if not username or not password or not real_name:
            error = '用户名、密码、姓名为必填项'
        elif db.execute('SELECT id FROM users WHERE username = ?',
                        (username,)).fetchone():
            error = f'用户名 {username} 已被注册'
        if error is None:
            db.execute(
                'INSERT INTO users (username, password_hash, role, real_name, id_card, phone)'
                ' VALUES (?,?,?,?,?,?)',
                (username, generate_password_hash(password), 'candidate',
                 real_name, id_card, phone))
            db.commit()
            flash('注册成功，请登录', 'success')
            return redirect(url_for('auth.login'))
        flash(error, 'error')
    return render_template('auth/register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = get_db().execute(
            'SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user is None or not check_password_hash(user['password_hash'], password):
            flash('用户名或密码错误', 'error')
        else:
            session.clear()
            session['user_id'] = user['id']
            return redirect(url_for('index'))
    return render_template('auth/login.html')


@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))
