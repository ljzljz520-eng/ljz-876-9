"""管理端：工种资源管理、场次管理、考评员管理、评分表导出"""
import csv
import io
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, Response, abort)
from . import db
from .auth import role_required
from .models import (Skill, Workstation, Consumable, TimeSlot, Booking,
                     ScoreItem, User, CATEGORY_NAMES,
                     ROLE_ADMIN, ROLE_EXAMINER, ST_SCORED, ST_CANCELLED)

admin_bp = Blueprint('admin', __name__)


@admin_bp.route('/dashboard')
@role_required(ROLE_ADMIN)
def dashboard():
    stats = {
        'skills': Skill.query.count(),
        'workstations': Workstation.query.filter_by(active=True).count(),
        'examiners': User.query.filter_by(role=ROLE_EXAMINER).count(),
        'candidates': User.query.filter_by(role='candidate').count(),
        'slots_open': TimeSlot.query.filter_by(status='open').count(),
        'bookings': Booking.query.filter(Booking.status != ST_CANCELLED).count(),
        'scored': Booking.query.filter_by(status=ST_SCORED).count(),
    }
    low_stock = [c for c in Consumable.query.all() if c.stock < c.per_exam * 3]
    return render_template('admin/dashboard.html', stats=stats, low_stock=low_stock)


# ---------- 工位管理 ----------
@admin_bp.route('/workstations', methods=['GET', 'POST'])
@role_required(ROLE_ADMIN)
def workstations():
    if request.method == 'POST':
        ws = Workstation(
            skill_id=request.form.get('skill_id', type=int),
            name=request.form.get('name', '').strip(),
            location=request.form.get('location', '').strip())
        if ws.skill_id and ws.name:
            db.session.add(ws)
            db.session.commit()
            flash('工位已添加', 'success')
        else:
            flash('请填写完整信息', 'danger')
        return redirect(url_for('admin.workstations'))
    items = Workstation.query.order_by(Workstation.skill_id, Workstation.id).all()
    return render_template('admin/workstations.html',
                           items=items, skills=Skill.query.all())


@admin_bp.route('/workstations/<int:ws_id>/toggle', methods=['POST'])
@role_required(ROLE_ADMIN)
def toggle_workstation(ws_id):
    ws = db.session.get(Workstation, ws_id) or abort(404)
    ws.active = not ws.active
    db.session.commit()
    flash(f'工位「{ws.name}」已{"启用" if ws.active else "停用"}', 'success')
    return redirect(url_for('admin.workstations'))


# ---------- 耗材管理 ----------
@admin_bp.route('/consumables', methods=['GET', 'POST'])
@role_required(ROLE_ADMIN)
def consumables():
    if request.method == 'POST':
        c = Consumable(
            skill_id=request.form.get('skill_id', type=int),
            name=request.form.get('name', '').strip(),
            unit=request.form.get('unit', '').strip(),
            stock=request.form.get('stock', type=float) or 0,
            per_exam=request.form.get('per_exam', type=float) or 1)
        if c.skill_id and c.name and c.unit:
            db.session.add(c)
            db.session.commit()
            flash('耗材已添加', 'success')
        else:
            flash('请填写完整信息', 'danger')
        return redirect(url_for('admin.consumables'))
    items = Consumable.query.order_by(Consumable.skill_id, Consumable.id).all()
    return render_template('admin/consumables.html',
                           items=items, skills=Skill.query.all())


@admin_bp.route('/consumables/<int:cid>/restock', methods=['POST'])
@role_required(ROLE_ADMIN)
def restock(cid):
    c = db.session.get(Consumable, cid) or abort(404)
    qty = request.form.get('quantity', type=float) or 0
    if qty > 0:
        c.stock += qty
        db.session.commit()
        flash(f'「{c.name}」已入库 {qty:g}{c.unit}，当前库存 {c.stock:g}{c.unit}', 'success')
    return redirect(url_for('admin.consumables'))


# ---------- 场次管理 ----------
@admin_bp.route('/slots', methods=['GET', 'POST'])
@role_required(ROLE_ADMIN)
def slots():
    if request.method == 'POST':
        try:
            start = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
            end = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')
        except (KeyError, ValueError):
            flash('时间格式不正确', 'danger')
            return redirect(url_for('admin.slots'))
        slot = TimeSlot(skill_id=request.form.get('skill_id', type=int),
                        start_time=start, end_time=end,
                        capacity=request.form.get('capacity', type=int) or 4)
        if not slot.skill_id or end <= start:
            flash('请检查场次信息（结束时间须晚于开始时间）', 'danger')
        else:
            db.session.add(slot)
            db.session.commit()
            flash('场次已创建', 'success')
        return redirect(url_for('admin.slots'))
    items = TimeSlot.query.order_by(TimeSlot.start_time.desc()).all()
    return render_template('admin/slots.html', items=items, skills=Skill.query.all())


@admin_bp.route('/slots/<int:slot_id>/toggle', methods=['POST'])
@role_required(ROLE_ADMIN)
def toggle_slot(slot_id):
    slot = db.session.get(TimeSlot, slot_id) or abort(404)
    slot.status = 'closed' if slot.status == 'open' else 'open'
    db.session.commit()
    flash(f'场次已{"开放" if slot.status == "open" else "关闭"}', 'success')
    return redirect(url_for('admin.slots'))


# ---------- 考评员管理 ----------
@admin_bp.route('/examiners', methods=['GET', 'POST'])
@role_required(ROLE_ADMIN)
def examiners():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        skill_id = request.form.get('skill_id', type=int)
        if not all([username, name, password, skill_id]):
            flash('请填写完整信息', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
        else:
            u = User(username=username, name=name, role=ROLE_EXAMINER,
                     skill_id=skill_id)
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            flash(f'考评员「{name}」已创建', 'success')
        return redirect(url_for('admin.examiners'))
    items = User.query.filter_by(role=ROLE_EXAMINER).all()
    return render_template('admin/examiners.html', items=items,
                           skills=Skill.query.all())


# ---------- 预约与成绩总览 ----------
@admin_bp.route('/bookings')
@role_required(ROLE_ADMIN)
def bookings():
    slot_id = request.args.get('slot_id', type=int)
    q = Booking.query.filter(Booking.status != ST_CANCELLED).join(TimeSlot)
    if slot_id:
        q = q.filter(Booking.slot_id == slot_id)
    items = q.order_by(TimeSlot.start_time.desc()).all()
    slots = TimeSlot.query.order_by(TimeSlot.start_time.desc()).all()
    return render_template('admin/bookings.html', items=items, slots=slots,
                           selected_slot=slot_id)


# ---------- 导出评分表（仅管理员） ----------
@admin_bp.route('/export/scores')
@role_required(ROLE_ADMIN)
def export_scores():
    """导出 CSV 评分表：一行一个考生，含各评分项得分与分类小计"""
    slot_id = request.args.get('slot_id', type=int)
    q = (Booking.query.filter_by(status=ST_SCORED)
         .join(TimeSlot).order_by(TimeSlot.start_time, Booking.booking_no))
    filename = 'scores_all.csv'
    if slot_id:
        q = q.filter(Booking.slot_id == slot_id)
        filename = f'scores_slot_{slot_id}.csv'
    bookings = q.all()
    if not bookings:
        flash('暂无可导出的已评分记录', 'warning')
        return redirect(url_for('admin.bookings'))

    # 以第一个考生的工种评分项为表头（同场次同工种）；跨工种导出时取并集
    item_ids = set()
    for b in bookings:
        item_ids.update(s.item_id for s in b.scores)
    items = (ScoreItem.query.filter(ScoreItem.id.in_(item_ids))
             .order_by(ScoreItem.skill_id, ScoreItem.category,
                       ScoreItem.sort_order).all()) if item_ids else []

    output = io.StringIO()
    writer = csv.writer(output)
    header = ['准考证号', '考生姓名', '工种', '考试时间', '工位', '考评员']
    for it in items:
        header.append(f'[{CATEGORY_NAMES[it.category]}]{it.name}(满分{it.max_score:g})')
    header += ['步骤小计', '成品小计', '安全小计', '总分', '考评员评语']
    writer.writerow(header)

    for b in bookings:
        score_map = {s.item_id: s.score for s in b.scores}
        row = [b.booking_no, b.candidate.name, b.slot.skill.name,
               b.slot.start_time.strftime('%Y-%m-%d %H:%M'),
               b.workstation.name if b.workstation else '',
               b.examiner.name if b.examiner else '']
        row += [score_map.get(it.id, '') for it in items]
        row += [b.category_subtotal('step'), b.category_subtotal('product'),
                b.category_subtotal('safety'), b.total_score,
                b.examiner_comment or '']
        writer.writerow(row)

    # utf-8-sig 保证 Excel 打开中文不乱码
    data = output.getvalue().encode('utf-8-sig')
    return Response(data, mimetype='text/csv',
                    headers={'Content-Disposition':
                             f'attachment; filename={filename}'})


@admin_bp.route('/export/sheet/<int:booking_id>')
@role_required(ROLE_ADMIN)
def export_sheet(booking_id):
    """单个考生的评分表（可打印页面）"""
    booking = db.session.get(Booking, booking_id) or abort(404)
    if booking.status != ST_SCORED:
        flash('该预约尚未完成评分', 'warning')
        return redirect(url_for('admin.bookings'))
    items = (ScoreItem.query.filter_by(skill_id=booking.slot.skill_id)
             .order_by(ScoreItem.category, ScoreItem.sort_order).all())
    score_map = {s.item_id: s for s in booking.scores}
    return render_template('admin/score_sheet.html', booking=booking,
                           items=items, score_map=score_map,
                           categories=CATEGORY_NAMES)
