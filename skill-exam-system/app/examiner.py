"""考评员端：查看考评任务、现场评分（步骤/成品/安全）"""
from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, url_for)
from .auth import role_required
from .db import get_db

bp = Blueprint('examiner', __name__, url_prefix='/examiner')

CATEGORY_NAMES = {'step': '操作步骤', 'product': '成品质量', 'safety': '安全行为'}
PASS_RATIO = 0.6  # 合格线：总分 60%


@bp.route('/')
@role_required('examiner')
def dashboard():
    tasks = get_db().execute(
        '''SELECT b.id, b.booking_no, b.status, s.name AS skill_name,
                  es.exam_date, es.start_time, es.end_time,
                  w.name AS ws_name, c.real_name AS candidate_name,
                  r.total_score, r.published
           FROM bookings b
           JOIN exam_sessions es ON es.id = b.session_id
           JOIN skills s ON s.id = es.skill_id
           JOIN workstations w ON w.id = b.workstation_id
           JOIN users c ON c.id = b.candidate_id
           LEFT JOIN results r ON r.booking_id = b.id
           WHERE b.examiner_id = ? AND b.status != 'cancelled'
           ORDER BY es.exam_date DESC, es.start_time''',
        (g.user['id'],)).fetchall()
    return render_template('examiner/dashboard.html', tasks=tasks)


@bp.route('/score/<int:booking_id>', methods=['GET', 'POST'])
@role_required('examiner')
def score(booking_id):
    db = get_db()
    b = db.execute(
        '''SELECT b.*, s.id AS skill_id, s.name AS skill_name,
                  es.exam_date, es.start_time, w.name AS ws_name,
                  c.real_name AS candidate_name, c.id_card
           FROM bookings b
           JOIN exam_sessions es ON es.id = b.session_id
           JOIN skills s ON s.id = es.skill_id
           JOIN workstations w ON w.id = b.workstation_id
           JOIN users c ON c.id = b.candidate_id
           WHERE b.id = ?''', (booking_id,)).fetchone()
    if b is None:
        abort(404)
    # 只能评分分配给自己的考生
    if b['examiner_id'] != g.user['id']:
        abort(403)
    if b['status'] == 'cancelled':
        flash('该预约已取消，无法评分', 'error')
        return redirect(url_for('examiner.dashboard'))

    rubric = db.execute(
        "SELECT * FROM rubric_items WHERE skill_id = ? "
        "ORDER BY CASE category WHEN 'step' THEN 1 WHEN 'product' THEN 2 "
        "ELSE 3 END, seq, id",
        (b['skill_id'],)).fetchall()

    if request.method == 'POST':
        error = None
        entries = []
        for item in rubric:
            raw = request.form.get(f'score_{item["id"]}', '').strip()
            try:
                val = float(raw)
            except ValueError:
                error = f'「{item["name"]}」得分无效'
                break
            if not (0 <= val <= item['max_score']):
                error = f'「{item["name"]}」得分须在 0~{item["max_score"]:g} 之间'
                break
            entries.append((item['id'], val,
                            request.form.get(f'comment_{item["id"]}', '').strip()))
        if error:
            flash(error, 'error')
        else:
            for item_id, val, comment in entries:
                db.execute(
                    '''INSERT INTO scores (booking_id, rubric_item_id, score, comment, scored_by)
                       VALUES (?,?,?,?,?)
                       ON CONFLICT(booking_id, rubric_item_id)
                       DO UPDATE SET score=excluded.score, comment=excluded.comment,
                                     scored_by=excluded.scored_by,
                                     scored_at=CURRENT_TIMESTAMP''',
                    (booking_id, item_id, val, comment, g.user['id']))
            total = sum(v for _, v, _ in entries)
            max_total = sum(i['max_score'] for i in rubric)
            passed = 1 if max_total > 0 and total >= max_total * PASS_RATIO else 0
            # 保留原有发布状态
            db.execute(
                '''INSERT INTO results (booking_id, total_score, max_score, passed, published)
                   VALUES (?,?,?,?, COALESCE((SELECT published FROM results
                                              WHERE booking_id = ?), 0))
                   ON CONFLICT(booking_id)
                   DO UPDATE SET total_score=excluded.total_score,
                                 max_score=excluded.max_score,
                                 passed=excluded.passed''',
                (booking_id, total, max_total, passed, booking_id))
            db.execute("UPDATE bookings SET status = 'completed' WHERE id = ?",
                       (booking_id,))
            db.commit()
            flash(f'评分完成，总分 {total:g}/{max_total:g}'
                  f'（{"合格" if passed else "不合格"}，待管理员发布）', 'success')
            return redirect(url_for('examiner.dashboard'))

    existing = {r['rubric_item_id']: r for r in db.execute(
        'SELECT * FROM scores WHERE booking_id = ?', (booking_id,)).fetchall()}
    grouped = {}
    for item in rubric:
        grouped.setdefault(item['category'], []).append(item)
    return render_template('examiner/score.html', b=b, grouped=grouped,
                           existing=existing, cat_names=CATEGORY_NAMES)
