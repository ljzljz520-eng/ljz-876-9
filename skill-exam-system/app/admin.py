"""管理员端：场次/资源管理、成绩发布、评分表导出"""
import csv
from urllib.parse import quote
import io
from flask import (Blueprint, Response, abort, flash, g, redirect,
                   render_template, request, url_for)
from werkzeug.security import generate_password_hash
from .auth import role_required
from .db import get_db

bp = Blueprint('admin', __name__, url_prefix='/admin')

CATEGORY_NAMES = {'step': '操作步骤', 'product': '成品质量', 'safety': '安全行为'}


@bp.route('/')
@role_required('admin')
def dashboard():
    db = get_db()
    stats = {
        'candidates': db.execute(
            "SELECT COUNT(*) c FROM users WHERE role='candidate'").fetchone()['c'],
        'examiners': db.execute(
            "SELECT COUNT(*) c FROM users WHERE role='examiner'").fetchone()['c'],
        'sessions': db.execute('SELECT COUNT(*) c FROM exam_sessions').fetchone()['c'],
        'bookings': db.execute(
            "SELECT COUNT(*) c FROM bookings WHERE status != 'cancelled'").fetchone()['c'],
        'scored': db.execute('SELECT COUNT(*) c FROM results').fetchone()['c'],
        'published': db.execute(
            'SELECT COUNT(*) c FROM results WHERE published = 1').fetchone()['c'],
    }
    return render_template('admin/dashboard.html', stats=stats)


# ---------- 场次管理 ----------
@bp.route('/sessions')
@role_required('admin')
def sessions():
    rows = get_db().execute(
        '''SELECT es.*, s.name AS skill_name,
                  (SELECT COUNT(*) FROM bookings b
                    WHERE b.session_id = es.id AND b.status != 'cancelled') AS n_booked,
                  (SELECT COUNT(*) FROM results r JOIN bookings b2
                    ON r.booking_id = b2.id
                    WHERE b2.session_id = es.id AND r.published = 1) AS n_published
           FROM exam_sessions es JOIN skills s ON s.id = es.skill_id
           ORDER BY es.exam_date DESC, es.start_time''').fetchall()
    skills = get_db().execute('SELECT * FROM skills ORDER BY id').fetchall()
    return render_template('admin/sessions.html', rows=rows, skills=skills)


@bp.route('/sessions/create', methods=['POST'])
@role_required('admin')
def session_create():
    db = get_db()
    db.execute(
        'INSERT INTO exam_sessions (skill_id, exam_date, start_time, end_time)'
        ' VALUES (?,?,?,?)',
        (request.form['skill_id'], request.form['exam_date'],
         request.form['start_time'], request.form['end_time']))
    db.commit()
    flash('场次已创建', 'success')
    return redirect(url_for('admin.sessions'))


@bp.route('/sessions/<int:session_id>/status', methods=['POST'])
@role_required('admin')
def session_status(session_id):
    status = request.form.get('status')
    if status in ('open', 'closed', 'finished'):
        db = get_db()
        db.execute('UPDATE exam_sessions SET status = ? WHERE id = ?',
                   (status, session_id))
        db.commit()
        flash('场次状态已更新', 'success')
    return redirect(url_for('admin.sessions'))


@bp.route('/sessions/<int:session_id>')
@role_required('admin')
def session_detail(session_id):
    db = get_db()
    sess = db.execute(
        '''SELECT es.*, s.name AS skill_name, s.id AS skill_id
           FROM exam_sessions es JOIN skills s ON s.id = es.skill_id
           WHERE es.id = ?''', (session_id,)).fetchone()
    if sess is None:
        abort(404)
    bookings = db.execute(
        '''SELECT b.*, c.real_name AS candidate_name, c.id_card,
                  w.name AS ws_name, e.real_name AS examiner_name,
                  r.total_score, r.max_score, r.passed, r.published
           FROM bookings b
           JOIN users c ON c.id = b.candidate_id
           JOIN workstations w ON w.id = b.workstation_id
           JOIN users e ON e.id = b.examiner_id
           LEFT JOIN results r ON r.booking_id = b.id
           WHERE b.session_id = ? AND b.status != 'cancelled'
           ORDER BY w.id''', (session_id,)).fetchall()
    return render_template('admin/session_detail.html', sess=sess,
                           bookings=bookings)


@bp.route('/sessions/<int:session_id>/publish', methods=['POST'])
@role_required('admin')
def session_publish(session_id):
    """发布该场次全部已评分成绩（发布后考生可见本人成绩）"""
    db = get_db()
    cur = db.execute(
        '''UPDATE results SET published = 1, published_at = CURRENT_TIMESTAMP
           WHERE booking_id IN (SELECT id FROM bookings WHERE session_id = ?)''',
        (session_id,))
    db.commit()
    flash(f'已发布 {cur.rowcount} 条成绩', 'success')
    return redirect(url_for('admin.session_detail', session_id=session_id))


# ---------- 评分表导出 ----------
@bp.route('/sessions/<int:session_id>/export')
@role_required('admin')
def session_export(session_id):
    """导出场次成绩汇总表 CSV（含步骤/成品/安全分项得分）"""
    db = get_db()
    sess = db.execute(
        '''SELECT es.*, s.name AS skill_name FROM exam_sessions es
           JOIN skills s ON s.id = es.skill_id WHERE es.id = ?''',
        (session_id,)).fetchone()
    if sess is None:
        abort(404)
    rows = db.execute(
        '''SELECT b.booking_no, c.real_name, c.id_card, w.name AS ws_name,
                  e.real_name AS examiner_name, r.total_score, r.max_score,
                  r.passed, r.published,
                  SUM(CASE WHEN ri.category='step'    THEN s.score ELSE 0 END) AS step_score,
                  SUM(CASE WHEN ri.category='product' THEN s.score ELSE 0 END) AS product_score,
                  SUM(CASE WHEN ri.category='safety'  THEN s.score ELSE 0 END) AS safety_score
           FROM bookings b
           JOIN users c ON c.id = b.candidate_id
           JOIN workstations w ON w.id = b.workstation_id
           JOIN users e ON e.id = b.examiner_id
           LEFT JOIN results r ON r.booking_id = b.id
           LEFT JOIN scores s ON s.booking_id = b.id
           LEFT JOIN rubric_items ri ON ri.id = s.rubric_item_id
           WHERE b.session_id = ? AND b.status != 'cancelled'
           GROUP BY b.id ORDER BY w.id''', (session_id,)).fetchall()

    out = io.StringIO()
    out.write('﻿')  # BOM，保证 Excel 正确识别中文
    w = csv.writer(out)
    w.writerow([f'{sess["skill_name"]}实操考试成绩表',
                f'{sess["exam_date"]} {sess["start_time"]}-{sess["end_time"]}'])
    w.writerow(['预约号', '姓名', '身份证号', '工位', '考评员',
                '步骤得分', '成品得分', '安全得分', '总分', '满分',
                '是否合格', '是否发布'])
    for r in rows:
        w.writerow([
            r['booking_no'], r['real_name'], r['id_card'] or '', r['ws_name'],
            r['examiner_name'],
            f"{r['step_score']:g}" if r['total_score'] is not None else '',
            f"{r['product_score']:g}" if r['total_score'] is not None else '',
            f"{r['safety_score']:g}" if r['total_score'] is not None else '',
            f"{r['total_score']:g}" if r['total_score'] is not None else '未评分',
            f"{r['max_score']:g}" if r['max_score'] is not None else '',
            '合格' if r['passed'] else ('不合格' if r['total_score'] is not None else ''),
            '已发布' if r['published'] else '未发布'])
    filename = f"scores_{sess['skill_name']}_{sess['exam_date']}_{session_id}.csv"
    return Response(out.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition':
                             f"attachment; filename*=UTF-8''{quote(filename)}"})


@bp.route('/bookings/<int:booking_id>/export')
@role_required('admin')
def booking_export(booking_id):
    """导出单个考生的详细评分表 CSV（逐项）"""
    db = get_db()
    b = db.execute(
        '''SELECT b.booking_no, c.real_name, c.id_card, s.name AS skill_name,
                  es.exam_date, es.start_time, w.name AS ws_name,
                  e.real_name AS examiner_name, r.total_score, r.max_score, r.passed
           FROM bookings b
           JOIN users c ON c.id = b.candidate_id
           JOIN exam_sessions es ON es.id = b.session_id
           JOIN skills s ON s.id = es.skill_id
           JOIN workstations w ON w.id = b.workstation_id
           JOIN users e ON e.id = b.examiner_id
           LEFT JOIN results r ON r.booking_id = b.id
           WHERE b.id = ?''', (booking_id,)).fetchone()
    if b is None:
        abort(404)
    items = db.execute(
        '''SELECT ri.category, ri.seq, ri.name, ri.max_score, s.score, s.comment
           FROM scores s JOIN rubric_items ri ON ri.id = s.rubric_item_id
           WHERE s.booking_id = ? ORDER BY CASE ri.category WHEN 'step' THEN 1 WHEN 'product' THEN 2 ELSE 3 END, ri.seq''',
        (booking_id,)).fetchall()

    out = io.StringIO()
    out.write('﻿')
    w = csv.writer(out)
    w.writerow(['职业技能实操评分表'])
    w.writerow(['预约号', b['booking_no'], '工种', b['skill_name']])
    w.writerow(['考生', b['real_name'], '身份证号', b['id_card'] or ''])
    w.writerow(['考试时间', f"{b['exam_date']} {b['start_time']}",
                '工位', b['ws_name'], '考评员', b['examiner_name']])
    w.writerow([])
    w.writerow(['类别', '评分项目', '满分', '得分', '备注'])
    for it in items:
        w.writerow([CATEGORY_NAMES[it['category']], it['name'],
                    f"{it['max_score']:g}", f"{it['score']:g}",
                    it['comment'] or ''])
    w.writerow([])
    w.writerow(['总分', f"{b['total_score']:g}" if b['total_score'] is not None else '未评分',
                '满分', f"{b['max_score']:g}" if b['max_score'] is not None else '',
                '结论', '合格' if b['passed'] else '不合格'])
    filename = f"score_sheet_{b['booking_no']}.csv"
    return Response(out.getvalue(), mimetype='text/csv; charset=utf-8',
                    headers={'Content-Disposition':
                             f"attachment; filename*=UTF-8''{quote(filename)}"})


# ---------- 工位管理 ----------
@bp.route('/workstations', methods=['GET', 'POST'])
@role_required('admin')
def workstations():
    db = get_db()
    if request.method == 'POST':
        db.execute(
            'INSERT INTO workstations (skill_id, name, location) VALUES (?,?,?)',
            (request.form['skill_id'], request.form['name'],
             request.form.get('location', '')))
        db.commit()
        flash('工位已添加', 'success')
        return redirect(url_for('admin.workstations'))
    rows = db.execute(
        '''SELECT w.*, s.name AS skill_name FROM workstations w
           JOIN skills s ON s.id = w.skill_id ORDER BY s.id, w.id''').fetchall()
    skills = db.execute('SELECT * FROM skills ORDER BY id').fetchall()
    return render_template('admin/workstations.html', rows=rows, skills=skills)


@bp.route('/workstations/<int:ws_id>/toggle', methods=['POST'])
@role_required('admin')
def workstation_toggle(ws_id):
    db = get_db()
    db.execute(
        """UPDATE workstations
           SET status = CASE status WHEN 'available' THEN 'maintenance'
                                    ELSE 'available' END
           WHERE id = ?""", (ws_id,))
    db.commit()
    return redirect(url_for('admin.workstations'))


# ---------- 耗材管理 ----------
@bp.route('/consumables', methods=['GET', 'POST'])
@role_required('admin')
def consumables():
    db = get_db()
    if request.method == 'POST':
        db.execute(
            '''INSERT INTO consumables (skill_id, name, unit, stock, qty_per_exam)
               VALUES (?,?,?,?,?)''',
            (request.form['skill_id'], request.form['name'],
             request.form.get('unit', '份'),
             request.form.get('stock', type=int) or 0,
             request.form.get('qty_per_exam', type=int) or 1))
        db.commit()
        flash('耗材已添加', 'success')
        return redirect(url_for('admin.consumables'))
    rows = db.execute(
        '''SELECT c.*, s.name AS skill_name FROM consumables c
           JOIN skills s ON s.id = c.skill_id ORDER BY s.id, c.id''').fetchall()
    skills = db.execute('SELECT * FROM skills ORDER BY id').fetchall()
    return render_template('admin/consumables.html', rows=rows, skills=skills)


@bp.route('/consumables/<int:cid>/restock', methods=['POST'])
@role_required('admin')
def consumable_restock(cid):
    qty = request.form.get('qty', type=int) or 0
    if qty > 0:
        db = get_db()
        db.execute('UPDATE consumables SET stock = stock + ? WHERE id = ?',
                   (qty, cid))
        db.commit()
        flash(f'已补货 {qty}', 'success')
    return redirect(url_for('admin.consumables'))


# ---------- 考评员管理 ----------
@bp.route('/examiners', methods=['GET', 'POST'])
@role_required('admin')
def examiners():
    db = get_db()
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if db.execute('SELECT 1 FROM users WHERE username = ?',
                      (username,)).fetchone():
            flash('用户名已存在', 'error')
        else:
            cur = db.execute(
                '''INSERT INTO users (username, password_hash, role, real_name, phone)
                   VALUES (?,?, 'examiner', ?, ?)''',
                (username, generate_password_hash(request.form['password']),
                 request.form['real_name'], request.form.get('phone', '')))
            examiner_id = cur.lastrowid
            for sid in request.form.getlist('skill_ids'):
                db.execute(
                    'INSERT INTO examiner_skills (examiner_id, skill_id)'
                    ' VALUES (?,?)', (examiner_id, sid))
            db.commit()
            flash('考评员已创建', 'success')
        return redirect(url_for('admin.examiners'))
    rows = db.execute(
        '''SELECT u.*, GROUP_CONCAT(s.name, '、') AS skill_names
           FROM users u
           LEFT JOIN examiner_skills esk ON esk.examiner_id = u.id
           LEFT JOIN skills s ON s.id = esk.skill_id
           WHERE u.role = 'examiner' GROUP BY u.id ORDER BY u.id''').fetchall()
    skills = db.execute('SELECT * FROM skills ORDER BY id').fetchall()
    return render_template('admin/examiners.html', rows=rows, skills=skills)
