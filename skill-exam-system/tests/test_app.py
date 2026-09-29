"""核心业务与权限测试"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import (User, Skill, TimeSlot, Booking, Consumable, ScoreItem,
                        Score, ST_BOOKED, ST_SCORED, ST_CANCELLED)
from app.seed import seed


@pytest.fixture()
def app():
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'WTF_CSRF_ENABLED': False,
    })
    with app.app_context():
        db.create_all()
        seed()
    yield app
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username, password):
    return client.post('/login', data={'username': username, 'password': password},
                       follow_redirects=True)


def logout(client):
    return client.get('/logout', follow_redirects=True)


# ---------- 认证 ----------
def test_login_logout(client):
    r = login(client, 'student1', '123456')
    assert '我的预约'.encode() in r.data
    r = logout(client)
    assert '登录'.encode() in r.data


def test_login_wrong_password(client):
    r = login(client, 'student1', 'wrong')
    assert '用户名或密码错误'.encode() in r.data


def test_register(client):
    r = client.post('/register', data={
        'username': 'newbie', 'name': '新考生', 'phone': '13900000000',
        'password': 'abc123', 'password2': 'abc123'}, follow_redirects=True)
    assert '注册成功'.encode() in r.data
    r = login(client, 'newbie', 'abc123')
    assert '我的预约'.encode() in r.data


# ---------- 预约流程 ----------
def _first_open_slot_id(app, skill_code='WELD'):
    with app.app_context():
        skill = Skill.query.filter_by(code=skill_code).first()
        slot = TimeSlot.query.filter_by(skill_id=skill.id, status='open').first()
        return slot.id


def test_booking_assigns_resources_and_deducts_stock(client, app):
    login(client, 'student1', '123456')
    slot_id = _first_open_slot_id(app)
    with app.app_context():
        slot = db.session.get(TimeSlot, slot_id)
        before = {c.name: c.stock for c in
                  Consumable.query.filter_by(skill_id=slot.skill_id).all()}

    r = client.post('/candidate/book', data={'slot_id': slot_id}, follow_redirects=True)
    assert '预约成功'.encode() in r.data

    with app.app_context():
        b = Booking.query.filter_by(slot_id=slot_id).first()
        assert b is not None
        assert b.workstation_id is not None   # 已分配工位
        assert b.examiner_id is not None      # 已分配考评员
        assert b.status == ST_BOOKED
        # 耗材已扣减
        for c in Consumable.query.filter_by(skill_id=b.slot.skill_id).all():
            assert c.stock == before[c.name] - c.per_exam


def test_duplicate_booking_rejected(client, app):
    login(client, 'student1', '123456')
    slot_id = _first_open_slot_id(app)
    client.post('/candidate/book', data={'slot_id': slot_id})
    r = client.post('/candidate/book', data={'slot_id': slot_id}, follow_redirects=True)
    assert '已预约过该场次'.encode() in r.data
    with app.app_context():
        assert Booking.query.filter_by(slot_id=slot_id).count() == 1


def test_capacity_limit(client, app):
    """同一场次第5个考生预约失败（容量4）"""
    slot_id = _first_open_slot_id(app, 'COOK')
    for i in range(1, 5):  # student1..4 先占位（种子只有3个，注册第4个）
        name = f'student{i}'
        if i == 4:
            client.post('/register', data={'username': name, 'name': f'考生{i}',
                                           'password': '123456', 'password2': '123456'})
        login(client, name, '123456')
        r = client.post('/candidate/book', data={'slot_id': slot_id}, follow_redirects=True)
        assert '预约成功'.encode() in r.data
        logout(client)
    # 第5个考生
    client.post('/register', data={'username': 'student5', 'name': '考生5',
                                   'password': '123456', 'password2': '123456'})
    login(client, 'student5', '123456')
    r = client.post('/candidate/book', data={'slot_id': slot_id}, follow_redirects=True)
    assert ('名额已满'.encode() in r.data or '工位已排满'.encode() in r.data
            or '考评员不足'.encode() in r.data)


def test_cancel_restores_stock(client, app):
    login(client, 'student1', '123456')
    slot_id = _first_open_slot_id(app)
    client.post('/candidate/book', data={'slot_id': slot_id})
    with app.app_context():
        b = Booking.query.filter_by(slot_id=slot_id).first()
        bid = b.id
        stocks_before_cancel = {c.id: c.stock for c in
                                Consumable.query.filter_by(skill_id=b.slot.skill_id)}
    r = client.post(f'/candidate/booking/{bid}/cancel', follow_redirects=True)
    assert '已取消'.encode() in r.data
    with app.app_context():
        b = db.session.get(Booking, bid)
        assert b.status == ST_CANCELLED
        for c in Consumable.query.filter_by(skill_id=b.slot.skill_id).all():
            assert c.stock == stocks_before_cancel[c.id] + c.per_exam


# ---------- 评分流程 ----------
def _make_booking(client, app, username='student1', skill='WELD'):
    login(client, username, '123456')
    slot_id = _first_open_slot_id(app, skill)
    client.post('/candidate/book', data={'slot_id': slot_id})
    logout(client)
    with app.app_context():
        return Booking.query.filter_by(slot_id=slot_id).first().id


def test_examiner_scores_booking(client, app):
    bid = _make_booking(client, app)
    login(client, 'exam_weld1', 'exam123')
    with app.app_context():
        b = db.session.get(Booking, bid)
        items = ScoreItem.query.filter_by(skill_id=b.slot.skill_id).all()
        data = {f'item_{it.id}': str(it.max_score - 1) for it in items}
        data['examiner_comment'] = '整体表现良好'
    r = client.post(f'/examiner/score/{bid}', data=data, follow_redirects=True)
    assert '评分完成'.encode() in r.data
    with app.app_context():
        b = db.session.get(Booking, bid)
        assert b.status == ST_SCORED
        expected = sum(it.max_score - 1 for it in items)
        assert abs(b.total_score - expected) < 0.01
        assert b.examiner_comment == '整体表现良好'


def test_score_out_of_range_rejected(client, app):
    bid = _make_booking(client, app)
    login(client, 'exam_weld1', 'exam123')
    with app.app_context():
        b = db.session.get(Booking, bid)
        items = ScoreItem.query.filter_by(skill_id=b.slot.skill_id).all()
        data = {f'item_{it.id}': '999' for it in items}  # 超出满分
    r = client.post(f'/examiner/score/{bid}', data=data)
    assert r.status_code == 400
    with app.app_context():
        assert db.session.get(Booking, bid).status == ST_BOOKED  # 未保存


def test_examiner_cannot_score_others_booking(client, app):
    """考评员不能评分未分配给自己的预约"""
    bid = _make_booking(client, app)
    login(client, 'exam_weld2', 'exam123')  # 另一个电焊考评员
    r = client.get(f'/examiner/score/{bid}')
    assert r.status_code == 403


# ---------- 成绩可见性（核心安全需求） ----------
def _score_booking(client, app, bid, examiner='exam_weld1'):
    login(client, examiner, 'exam123')
    with app.app_context():
        b = db.session.get(Booking, bid)
        items = ScoreItem.query.filter_by(skill_id=b.slot.skill_id).all()
        data = {f'item_{it.id}': str(it.max_score) for it in items}
    client.post(f'/examiner/score/{bid}', data=data)
    logout(client)


def test_candidate_sees_only_own_scores(client, app):
    # student1 完成一次考试并评分
    bid1 = _make_booking(client, app, 'student1')
    _score_booking(client, app, bid1)
    # student2 也完成一次（同工种下一场次）
    login(client, 'student2', '123456')
    with app.app_context():
        skill = Skill.query.filter_by(code='WELD').first()
        slot2 = (TimeSlot.query.filter_by(skill_id=skill.id, status='open')
                 .order_by(TimeSlot.id).offset(1).first())
        slot2_id = slot2.id
    client.post('/candidate/book', data={'slot_id': slot2_id})
    logout(client)
    with app.app_context():
        bid2 = Booking.query.filter_by(slot_id=slot2_id).first().id
    _score_booking(client, app, bid2, examiner='exam_weld1')

    # student1 登录：能看到自己的成绩
    login(client, 'student1', '123456')
    r = client.get('/candidate/scores')
    assert r.status_code == 200
    # 直接访问 student2 的成绩详情 → 404（不暴露存在性）
    r = client.get(f'/candidate/scores/{bid2}')
    assert r.status_code == 404
    # 访问自己的 → 200
    r = client.get(f'/candidate/scores/{bid1}')
    assert r.status_code == 200


def test_candidate_cannot_access_admin_export(client, app):
    login(client, 'student1', '123456')
    assert client.get('/admin/export/scores').status_code == 403
    assert client.get('/admin/bookings').status_code == 403
    assert client.get('/admin/dashboard').status_code == 403


def test_examiner_cannot_access_admin(client, app):
    login(client, 'exam_weld1', 'exam123')
    assert client.get('/admin/dashboard').status_code == 403
    assert client.get('/admin/export/scores').status_code == 403


def test_anonymous_redirected_to_login(client):
    r = client.get('/candidate/dashboard')
    assert r.status_code == 302 and '/login' in r.headers['Location']


# ---------- 导出 ----------
def test_admin_export_csv(client, app):
    bid = _make_booking(client, app)
    _score_booking(client, app, bid)
    login(client, 'admin', 'admin123')
    r = client.get('/admin/export/scores')
    assert r.status_code == 200
    assert r.mimetype == 'text/csv'
    text = r.data.decode('utf-8-sig')
    assert '准考证号' in text and '总分' in text
    assert '考生1号' in text
    # 包含分类小计列
    assert '步骤小计' in text and '成品小计' in text and '安全小计' in text


def test_admin_export_printable_sheet(client, app):
    bid = _make_booking(client, app)
    _score_booking(client, app, bid)
    login(client, 'admin', 'admin123')
    r = client.get(f'/admin/export/sheet/{bid}')
    assert r.status_code == 200
    assert '评分表'.encode() in r.data
    assert '考生1号'.encode() in r.data
