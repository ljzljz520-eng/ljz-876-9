"""考生端：预约实操、查看预约与自己的成绩"""
import secrets
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import current_user
from sqlalchemy.exc import IntegrityError
from . import db
from .auth import role_required
from .models import (Skill, TimeSlot, Booking, Workstation, Consumable,
                     BookingConsumable, User, ScoreItem,
                     ROLE_CANDIDATE, ROLE_EXAMINER,
                     ST_BOOKED, ST_CANCELLED, ST_SCORED)

candidate_bp = Blueprint('candidate', __name__)


def _begin_immediate():
    """SQLite 下使用 BEGIN IMMEDIATE 防止并发预约产生资源冲突"""
    if db.engine.url.get_backend_name() == 'sqlite':
        db.session.execute(db.text('BEGIN IMMEDIATE'))


def _assign_resources(slot):
    """为场次分配空闲工位与考评员，返回 (workstation, examiner)"""
    used_ws = {b.workstation_id for b in slot.active_bookings()}
    used_ex = {b.examiner_id for b in slot.active_bookings()}

    workstation = (Workstation.query
                   .filter_by(skill_id=slot.skill_id, active=True)
                   .filter(~Workstation.id.in_(used_ws or {0}))
                   .order_by(Workstation.id).first())
    examiner = (User.query
                .filter_by(role=ROLE_EXAMINER, skill_id=slot.skill_id)
                .filter(~User.id.in_(used_ex or {0}))
                .order_by(User.id).first())
    return workstation, examiner


@candidate_bp.route('/dashboard')
@role_required(ROLE_CANDIDATE)
def dashboard():
    bookings = (Booking.query.filter_by(candidate_id=current_user.id)
                .order_by(Booking.created_at.desc()).all())
    return render_template('candidate/dashboard.html', bookings=bookings)


@candidate_bp.route('/book', methods=['GET', 'POST'])
@role_required(ROLE_CANDIDATE)
def book():
    if request.method == 'POST':
        slot_id = request.form.get('slot_id', type=int)
        slot = db.session.get(TimeSlot, slot_id)
        if not slot or slot.status != 'open':
            flash('该场次不可预约', 'danger')
            return redirect(url_for('candidate.book'))
        if slot.start_time <= datetime.now():
            flash('该场次已开始，无法预约', 'danger')
            return redirect(url_for('candidate.book'))

        try:
            _begin_immediate()

            # 同一考生同一场次只能预约一次
            dup = (Booking.query
                   .filter_by(candidate_id=current_user.id, slot_id=slot.id)
                   .filter(Booking.status != ST_CANCELLED).first())
            if dup:
                flash('您已预约过该场次', 'warning')
                db.session.rollback()
                return redirect(url_for('candidate.book'))

            if slot.remaining() <= 0:
                flash('该场次名额已满', 'danger')
                db.session.rollback()
                return redirect(url_for('candidate.book'))

            workstation, examiner = _assign_resources(slot)
            if not workstation:
                flash('该场次工位已排满，请选择其他场次', 'danger')
                db.session.rollback()
                return redirect(url_for('candidate.book'))
            if not examiner:
                flash('该场次考评员不足，请选择其他场次', 'danger')
                db.session.rollback()
                return redirect(url_for('candidate.book'))

            # 检查并扣减耗材库存
            consumables = Consumable.query.filter_by(skill_id=slot.skill_id).all()
            for c in consumables:
                if c.stock < c.per_exam:
                    flash(f'耗材「{c.name}」库存不足，请联系管理员', 'danger')
                    db.session.rollback()
                    return redirect(url_for('candidate.book'))

            booking = Booking(
                booking_no='BK' + datetime.now().strftime('%Y%m%d') + secrets.token_hex(3).upper(),
                candidate_id=current_user.id,
                slot_id=slot.id,
                workstation_id=workstation.id,
                examiner_id=examiner.id,
                status=ST_BOOKED)
            db.session.add(booking)
            db.session.flush()

            for c in consumables:
                c.stock -= c.per_exam
                db.session.add(BookingConsumable(
                    booking_id=booking.id, consumable_id=c.id, quantity=c.per_exam))

            db.session.commit()
            flash(f'预约成功！准考证号：{booking.booking_no}，'
                  f'工位：{workstation.name}', 'success')
            return redirect(url_for('candidate.dashboard'))
        except IntegrityError:
            db.session.rollback()
            flash('预约冲突，请重试', 'danger')
            return redirect(url_for('candidate.book'))

    # GET：展示可预约的场次（按工种分组）
    skills = Skill.query.order_by(Skill.id).all()
    now = datetime.now()
    slots = (TimeSlot.query.filter(TimeSlot.status == 'open', TimeSlot.start_time > now)
             .order_by(TimeSlot.start_time).all())
    my_slot_ids = {b.slot_id for b in Booking.query.filter_by(candidate_id=current_user.id)
                   .filter(Booking.status != ST_CANCELLED).all()}
    return render_template('candidate/book.html', skills=skills, slots=slots,
                           my_slot_ids=my_slot_ids)


@candidate_bp.route('/booking/<int:booking_id>/cancel', methods=['POST'])
@role_required(ROLE_CANDIDATE)
def cancel(booking_id):
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.candidate_id != current_user.id:
        abort(404)
    if booking.status != ST_BOOKED:
        flash('当前状态不可取消', 'warning')
        return redirect(url_for('candidate.dashboard'))
    if booking.slot.start_time <= datetime.now():
        flash('考试已开始，无法取消', 'danger')
        return redirect(url_for('candidate.dashboard'))

    _begin_immediate()
    # 取消预约：释放工位/考评员，回补耗材库存
    for bc in booking.consumables_used:
        bc.consumable.stock += bc.quantity
    booking.status = ST_CANCELLED
    db.session.commit()
    flash('预约已取消，耗材已回补库存', 'success')
    return redirect(url_for('candidate.dashboard'))


@candidate_bp.route('/scores')
@role_required(ROLE_CANDIDATE)
def my_scores():
    """考生只能查看自己的成绩"""
    bookings = (Booking.query
                .filter_by(candidate_id=current_user.id, status=ST_SCORED)
                .order_by(Booking.scored_at.desc()).all())
    return render_template('candidate/my_scores.html', bookings=bookings)


@candidate_bp.route('/scores/<int:booking_id>')
@role_required(ROLE_CANDIDATE)
def score_detail(booking_id):
    """成绩详情：严格校验归属，防止越权查看他人成绩"""
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.candidate_id != current_user.id:
        abort(404)  # 不暴露记录是否存在
    if booking.status != ST_SCORED:
        flash('该场考试尚未公布成绩', 'warning')
        return redirect(url_for('candidate.my_scores'))
    items = (ScoreItem.query.filter_by(skill_id=booking.slot.skill_id)
             .order_by(ScoreItem.category, ScoreItem.sort_order).all())
    score_map = {s.item_id: s for s in booking.scores}
    return render_template('candidate/score_detail.html', booking=booking,
                           items=items, score_map=score_map)
