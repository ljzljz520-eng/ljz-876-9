"""考生端：预约实操考试、查看本人成绩"""
import datetime
from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from .auth import role_required
from .db import get_db

bp = Blueprint('candidate', __name__, url_prefix='/candidate')


@bp.route('/')
@role_required('candidate')
def dashboard():
    db = get_db()
    bookings = db.execute(
        '''SELECT b.*, s.name AS skill_name, w.name AS ws_name,
                  es.exam_date, es.start_time, es.end_time,
                  u.real_name AS examiner_name,
                  r.total_score, r.passed, r.published
           FROM bookings b
           JOIN exam_sessions es ON es.id = b.session_id
           JOIN skills s ON s.id = es.skill_id
           JOIN workstations w ON w.id = b.workstation_id
           JOIN users u ON u.id = b.examiner_id
           LEFT JOIN results r ON r.booking_id = b.id
           WHERE b.candidate_id = ?
           ORDER BY es.exam_date DESC, b.id DESC''',
        (g.user['id'],)).fetchall()
    return render_template('candidate/dashboard.html', bookings=bookings)


@bp.route('/book', methods=['GET', 'POST'])
@role_required('candidate')
def book():
    db = get_db()
    if request.method == 'POST':
        session_id = request.form.get('session_id', type=int)
        error = _do_booking(db, session_id, g.user['id'])
        if error:
            flash(error, 'error')
        else:
            flash('预约成功！系统已为您安排工位、考评员和耗材。', 'success')
            return redirect(url_for('candidate.dashboard'))

    # 可预约场次：开放中、日期不早于今天、仍有空工位
    sessions = db.execute(
        '''SELECT es.*, s.name AS skill_name,
                  (SELECT COUNT(*) FROM workstations w
                    WHERE w.skill_id = es.skill_id AND w.status = 'available'
                      AND w.id NOT IN (
                          SELECT workstation_id FROM bookings
                          WHERE session_id = es.id AND status != 'cancelled')
                  ) AS free_ws
           FROM exam_sessions es JOIN skills s ON s.id = es.skill_id
           WHERE es.status = 'open' AND es.exam_date >= date('now')
           ORDER BY es.exam_date, es.start_time''').fetchall()
    return render_template('candidate/book.html', sessions=sessions)


def _do_booking(db, session_id, candidate_id):
    """预约核心逻辑：自动分配工位 + 考评员 + 扣减耗材（整体事务）"""
    sess = db.execute(
        "SELECT * FROM exam_sessions WHERE id = ? AND status = 'open'",
        (session_id,)).fetchone()
    if sess is None:
        return '场次不存在或已停止预约'

    if db.execute(
            "SELECT 1 FROM bookings WHERE candidate_id = ? AND session_id = ?"
            " AND status != 'cancelled'", (candidate_id, session_id)).fetchone():
        return '您已预约过该场次，请勿重复预约'

    # 1) 分配本工种空闲工位
    ws = db.execute(
        '''SELECT * FROM workstations w
           WHERE w.skill_id = ? AND w.status = 'available'
             AND w.id NOT IN (SELECT workstation_id FROM bookings
                              WHERE session_id = ? AND status != 'cancelled')
           ORDER BY w.id LIMIT 1''',
        (sess['skill_id'], session_id)).fetchone()
    if ws is None:
        return '该场次工位已约满'

    # 2) 分配有资质且当前场次负载最低的考评员
    examiner = db.execute(
        '''SELECT u.id,
                  (SELECT COUNT(*) FROM bookings b
                    WHERE b.examiner_id = u.id AND b.session_id = ?
                      AND b.status != 'cancelled') AS load
           FROM users u JOIN examiner_skills esk ON esk.examiner_id = u.id
           WHERE u.role = 'examiner' AND esk.skill_id = ?
           ORDER BY load, u.id LIMIT 1''',
        (session_id, sess['skill_id'])).fetchone()
    if examiner is None:
        return '该工种暂无可用考评员，请联系管理员'

    # 3) 校验耗材库存
    cons = db.execute('SELECT * FROM consumables WHERE skill_id = ?',
                      (sess['skill_id'],)).fetchall()
    for c in cons:
        if c['stock'] < c['qty_per_exam']:
            return f"耗材「{c['name']}」库存不足，暂无法预约"

    # 4) 事务：建预约 + 扣库存 + 记录耗材明细
    booking_no = 'BK' + datetime.datetime.now().strftime('%Y%m%d%H%M%S') \
                 + f'{candidate_id:04d}'
    try:
        cur = db.execute(
            '''INSERT INTO bookings
               (booking_no, candidate_id, session_id, workstation_id, examiner_id)
               VALUES (?,?,?,?,?)''',
            (booking_no, candidate_id, session_id, ws['id'], examiner['id']))
        booking_id = cur.lastrowid
        for c in cons:
            db.execute('UPDATE consumables SET stock = stock - ? WHERE id = ?',
                       (c['qty_per_exam'], c['id']))
            db.execute(
                'INSERT INTO booking_consumables (booking_id, consumable_id, qty)'
                ' VALUES (?,?,?)', (booking_id, c['id'], c['qty_per_exam']))
        db.commit()
    except Exception:
        db.rollback()
        return '预约失败，请重试'
    return None


@bp.route('/booking/<int:booking_id>/cancel', methods=['POST'])
@role_required('candidate')
def cancel(booking_id):
    db = get_db()
    b = db.execute(
        "SELECT * FROM bookings WHERE id = ? AND candidate_id = ?",
        (booking_id, g.user['id'])).fetchone()
    if b is None:
        flash('预约不存在', 'error')
    elif b['status'] != 'booked':
        flash('当前状态不可取消', 'error')
    else:
        # 取消预约并返还耗材
        db.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?",
                   (booking_id,))
        for bc in db.execute(
                'SELECT * FROM booking_consumables WHERE booking_id = ?',
                (booking_id,)).fetchall():
            db.execute('UPDATE consumables SET stock = stock + ? WHERE id = ?',
                       (bc['qty'], bc['consumable_id']))
        db.commit()
        flash('预约已取消，耗材已返还库存', 'success')
    return redirect(url_for('candidate.dashboard'))


@bp.route('/scores')
@role_required('candidate')
def scores():
    """我的成绩：只查本人 + 已发布的成绩"""
    rows = get_db().execute(
        '''SELECT b.id, b.booking_no, s.name AS skill_name, es.exam_date,
                  es.start_time, r.total_score, r.max_score, r.passed
           FROM bookings b
           JOIN exam_sessions es ON es.id = b.session_id
           JOIN skills s ON s.id = es.skill_id
           JOIN results r ON r.booking_id = b.id
           WHERE b.candidate_id = ? AND r.published = 1
           ORDER BY es.exam_date DESC''',
        (g.user['id'],)).fetchall()
    return render_template('candidate/scores.html', rows=rows)


@bp.route('/scores/<int:booking_id>')
@role_required('candidate')
def score_detail(booking_id):
    """成绩明细：严格校验归属，防止考生看到他人成绩"""
    db = get_db()
    b = db.execute(
        '''SELECT b.*, s.name AS skill_name, es.exam_date, es.start_time,
                  w.name AS ws_name, u.real_name AS examiner_name
           FROM bookings b
           JOIN exam_sessions es ON es.id = b.session_id
           JOIN skills s ON s.id = es.skill_id
           JOIN workstations w ON w.id = b.workstation_id
           JOIN users u ON u.id = b.examiner_id
           WHERE b.id = ? AND b.candidate_id = ?''',
        (booking_id, g.user['id'])).fetchone()
    result = db.execute(
        'SELECT * FROM results WHERE booking_id = ? AND published = 1',
        (booking_id,)).fetchone()
    if b is None or result is None:
        # 他人成绩或未发布：一律按"不存在"处理，不泄露任何信息
        flash('成绩不存在或尚未发布', 'error')
        return redirect(url_for('candidate.scores'))
    items = db.execute(
        '''SELECT ri.category, ri.name, ri.max_score, ri.seq, s.score, s.comment
           FROM scores s JOIN rubric_items ri ON ri.id = s.rubric_item_id
           WHERE s.booking_id = ?
           ORDER BY CASE ri.category WHEN 'step' THEN 1 WHEN 'product' THEN 2 ELSE 3 END, ri.seq''', (booking_id,)).fetchall()
    return render_template('candidate/score_detail.html',
                           b=b, result=result, items=items)
