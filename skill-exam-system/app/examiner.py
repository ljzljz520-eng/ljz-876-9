"""考评员端：查看考评任务、按步骤/成品/安全评分"""
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from . import db
from .auth import role_required
from .models import (Booking, Score, ScoreItem, CATEGORY_NAMES,
                     ROLE_EXAMINER, ST_BOOKED, ST_SCORED, ST_ABSENT)

examiner_bp = Blueprint('examiner', __name__)


@examiner_bp.route('/dashboard')
@role_required(ROLE_EXAMINER)
def dashboard():
    bookings = (Booking.query
                .filter_by(examiner_id=current_user.id)
                .filter(Booking.status.in_([ST_BOOKED, ST_SCORED, ST_ABSENT]))
                .join(Booking.slot)
                .order_by(db.text('time_slots.start_time')).all())
    return render_template('examiner/dashboard.html', bookings=bookings)


@examiner_bp.route('/score/<int:booking_id>', methods=['GET', 'POST'])
@role_required(ROLE_EXAMINER)
def score(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking:
        abort(404)
    # 考评员只能评分分配给自己的考生
    if booking.examiner_id != current_user.id:
        abort(403)
    if booking.status == ST_ABSENT:
        flash('该考生已标记缺考', 'warning')
        return redirect(url_for('examiner.dashboard'))

    items = (ScoreItem.query.filter_by(skill_id=booking.slot.skill_id)
             .order_by(ScoreItem.category, ScoreItem.sort_order).all())

    if request.method == 'POST':
        total = 0.0
        errors = []
        parsed = []
        for item in items:
            raw = request.form.get(f'item_{item.id}', '').strip()
            comment = request.form.get(f'comment_{item.id}', '').strip()[:256]
            if raw == '':
                errors.append(f'「{item.name}」未评分')
                continue
            try:
                val = float(raw)
            except ValueError:
                errors.append(f'「{item.name}」分数无效')
                continue
            if val < 0 or val > item.max_score:
                errors.append(f'「{item.name}」分数须在 0~{item.max_score:g} 之间')
                continue
            parsed.append((item, val, comment))
            total += val

        if errors:
            for e in errors:
                flash(e, 'danger')
            score_map = {s.item_id: s for s in booking.scores}
            return render_template('examiner/score.html', booking=booking,
                                   items=items, categories=CATEGORY_NAMES,
                                   score_map=score_map), 400

        # 覆盖式保存（允许改分，直到提交后也可修正）
        for item, val, comment in parsed:
            existing = next((s for s in booking.scores if s.item_id == item.id), None)
            if existing:
                existing.score, existing.comment = val, comment
            else:
                db.session.add(Score(booking_id=booking.id, item_id=item.id,
                                     score=val, comment=comment))
        booking.total_score = round(total, 1)
        booking.examiner_comment = request.form.get('examiner_comment', '').strip()
        booking.status = ST_SCORED
        booking.scored_at = datetime.now()
        db.session.commit()
        flash(f'评分完成，总分 {booking.total_score:g}', 'success')
        return redirect(url_for('examiner.dashboard'))

    score_map = {s.item_id: s for s in booking.scores}
    return render_template('examiner/score.html', booking=booking,
                           items=items, categories=CATEGORY_NAMES,
                           score_map=score_map)


@examiner_bp.route('/absent/<int:booking_id>', methods=['POST'])
@role_required(ROLE_EXAMINER)
def mark_absent(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking:
        abort(404)
    if booking.examiner_id != current_user.id:
        abort(403)
    if booking.status == ST_BOOKED:
        booking.status = ST_ABSENT
        db.session.commit()
        flash('已标记缺考', 'info')
    return redirect(url_for('examiner.dashboard'))
