"""端到端测试：预约→自动安排→评分→发布→查分→导出→隐私隔离"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.db import get_db
from app.seed import seed


@pytest.fixture()
def app():
    db_fd, db_path = tempfile.mkstemp(suffix='.sqlite')
    app = create_app({'TESTING': True, 'DATABASE': db_path,
                      'SECRET_KEY': 'test'})
    with app.app_context():
        seed()
    yield app
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username, password):
    return client.post('/auth/login',
                       data={'username': username, 'password': password},
                       follow_redirects=True)


def logout(client):
    return client.get('/auth/logout', follow_redirects=True)


def first_open_session_id(app, skill_code='welding'):
    with app.app_context():
        row = get_db().execute(
            '''SELECT es.id FROM exam_sessions es JOIN skills s ON s.id = es.skill_id
               WHERE s.code = ? AND es.status = 'open' ORDER BY es.exam_date LIMIT 1''',
            (skill_code,)).fetchone()
        return row['id']


def test_full_flow_and_privacy(app, client):
    """完整流程：注册→预约→评分→发布→查分，且考生不可见他人成绩"""
    # 1) 考生注册 + 登录
    rv = client.post('/auth/register', data={
        'username': 'stu_a', 'password': 'pw123456', 'real_name': '考生甲',
        'id_card': '110101200303031234', 'phone': '13800000001'},
        follow_redirects=True)
    assert '注册成功' in rv.get_data(as_text=True)
    login(client, 'stu_a', 'pw123456')

    # 2) 预约电焊场次
    sid = first_open_session_id(app, 'welding')
    rv = client.post('/candidate/book', data={'session_id': sid},
                     follow_redirects=True)
    text = rv.get_data(as_text=True)
    assert '预约成功' in text
    assert '电焊' in text and '工位' in text  # 页面显示已安排的工位

    # 3) 验证系统自动安排：工位/考评员已分配，耗材已扣减
    with app.app_context():
        db = get_db()
        b = db.execute('SELECT * FROM bookings WHERE booking_no LIKE "BK%"').fetchone()
        assert b is not None
        assert b['workstation_id'] is not None and b['examiner_id'] is not None
        cons = db.execute(
            '''SELECT c.name, c.stock, c.qty_per_exam FROM consumables c
               JOIN skills s ON s.id = c.skill_id WHERE s.code = "welding"''').fetchall()
        # 焊条初始 500，每场 10 → 应剩 490
        welding_rod = [c for c in cons if c['name'] == '焊条'][0]
        assert welding_rod['stock'] == 500 - 10
        detail = db.execute('SELECT COUNT(*) c FROM booking_consumables WHERE booking_id = ?',
                            (b['id'],)).fetchone()
        assert detail['c'] == len(cons)  # 每种耗材都有分配明细
        booking_id = b['id']

    # 4) 未评分前考生查不到成绩
    rv = client.get('/candidate/scores')
    assert '暂无已发布的成绩' in rv.get_data(as_text=True)
    logout(client)

    # 5) 考评员登录并评分（步骤/成品/安全全覆盖）
    login(client, 'examiner01', 'exam123')
    rv = client.get(f'/examiner/score/{booking_id}')
    text = rv.get_data(as_text=True)
    assert '操作步骤' in text and '成品质量' in text and '安全行为' in text
    with app.app_context():
        items = get_db().execute(
            '''SELECT ri.* FROM rubric_items ri JOIN skills s ON s.id = ri.skill_id
               WHERE s.code = "welding" ORDER BY ri.id''').fetchall()
    data = {}
    expect_total = 0
    for it in items:
        give = it['max_score'] - 1  # 每项扣 1 分
        expect_total += give
        data[f'score_{it["id"]}'] = str(give)
        data[f'comment_{it["id"]}'] = 'ok'
    rv = client.post(f'/examiner/score/{booking_id}', data=data,
                     follow_redirects=True)
    assert '评分完成' in rv.get_data(as_text=True)
    with app.app_context():
        r = get_db().execute('SELECT * FROM results WHERE booking_id = ?',
                             (booking_id,)).fetchone()
        assert r['total_score'] == expect_total
        assert r['passed'] == 1  # 只扣 8 分，远超 60 分合格线
        assert r['published'] == 0
    logout(client)

    # 6) 成绩未发布时考生仍不可见
    login(client, 'stu_a', 'pw123456')
    rv = client.get(f'/candidate/scores/{booking_id}', follow_redirects=True)
    assert '尚未发布' in rv.get_data(as_text=True)
    logout(client)

    # 7) 管理员发布成绩并导出 CSV
    login(client, 'admin', 'admin123')
    rv = client.post(f'/admin/sessions/{sid}/publish', follow_redirects=True)
    assert '已发布 1 条成绩' in rv.get_data(as_text=True)
    rv = client.get(f'/admin/sessions/{sid}/export')
    assert rv.status_code == 200
    csv_text = rv.get_data(as_text=True)
    assert '考生甲' in csv_text and '步骤得分' in csv_text
    assert str(expect_total) in csv_text or f'{expect_total:g}' in csv_text
    rv = client.get(f'/admin/bookings/{booking_id}/export')
    assert rv.status_code == 200
    assert '职业技能实操评分表' in rv.get_data(as_text=True)
    logout(client)

    # 8) 考生可见本人成绩
    login(client, 'stu_a', 'pw123456')
    rv = client.get('/candidate/scores')
    text = rv.get_data(as_text=True)
    assert '考生' in text or '合格' in text
    rv = client.get(f'/candidate/scores/{booking_id}')
    assert '成绩明细' in rv.get_data(as_text=True)
    logout(client)

    # 9) 隐私：另一考生不可见他人成绩
    client.post('/auth/register', data={
        'username': 'stu_b', 'password': 'pw123456', 'real_name': '考生乙'},
        follow_redirects=True)
    login(client, 'stu_b', 'pw123456')
    rv = client.get(f'/candidate/scores/{booking_id}', follow_redirects=True)
    text = rv.get_data(as_text=True)
    assert '成绩明细' not in text          # 看不到甲的评分表
    assert '成绩不存在或尚未发布' in text
    rv = client.get('/candidate/scores')
    assert '考生甲' not in rv.get_data(as_text=True)  # 列表也不泄露
    # 考生不能访问管理端导出接口
    rv = client.get(f'/admin/sessions/{sid}/export', follow_redirects=True)
    assert '无权访问' in rv.get_data(as_text=True)


def test_double_booking_rejected(app, client):
    login(client, 'candidate01', 'cand123')
    sid = first_open_session_id(app, 'cooking')
    client.post('/candidate/book', data={'session_id': sid}, follow_redirects=True)
    rv = client.post('/candidate/book', data={'session_id': sid},
                     follow_redirects=True)
    assert '请勿重复预约' in rv.get_data(as_text=True)


def test_workstation_exhaustion(app, client):
    """工种只有 2 个工位，第 3 人预约同一场次应失败"""
    sid = first_open_session_id(app, 'beauty')
    for i in range(2):
        uname = f'cand_x{i}'
        client.post('/auth/register', data={
            'username': uname, 'password': 'pw123456',
            'real_name': f'考生{i}'}, follow_redirects=True)
        login(client, uname, 'pw123456')
        rv = client.post('/candidate/book', data={'session_id': sid},
                         follow_redirects=True)
        assert '预约成功' in rv.get_data(as_text=True)
        logout(client)
    client.post('/auth/register', data={
        'username': 'cand_x2', 'password': 'pw123456',
        'real_name': '考生2'}, follow_redirects=True)
    login(client, 'cand_x2', 'pw123456')
    rv = client.post('/candidate/book', data={'session_id': sid},
                     follow_redirects=True)
    assert '工位已约满' in rv.get_data(as_text=True)


def test_cancel_restores_consumables(app, client):
    login(client, 'candidate02', 'cand123')
    sid = first_open_session_id(app, 'auto_repair')
    client.post('/candidate/book', data={'session_id': sid}, follow_redirects=True)
    with app.app_context():
        db = get_db()
        b = db.execute("SELECT * FROM bookings WHERE status='booked'").fetchone()
        stock_before = db.execute(
            '''SELECT c.stock FROM consumables c JOIN skills s ON s.id=c.skill_id
               WHERE s.code='auto_repair' AND c.name='机油' ''').fetchone()['stock']
    client.post(f'/candidate/booking/{b["id"]}/cancel', follow_redirects=True)
    with app.app_context():
        db = get_db()
        stock_after = db.execute(
            '''SELECT c.stock FROM consumables c JOIN skills s ON s.id=c.skill_id
               WHERE s.code='auto_repair' AND c.name='机油' ''').fetchone()['stock']
        assert stock_after == stock_before + 4  # 机油每场 4 升，取消后返还
        st = db.execute('SELECT status FROM bookings WHERE id = ?',
                        (b['id'],)).fetchone()['status']
        assert st == 'cancelled'


def test_examiner_cannot_score_others_booking(app, client):
    """考评员不能评分未分配给自己的预约"""
    login(client, 'candidate01', 'cand123')
    sid = first_open_session_id(app, 'welding')
    client.post('/candidate/book', data={'session_id': sid}, follow_redirects=True)
    logout(client)
    with app.app_context():
        b = get_db().execute("SELECT * FROM bookings WHERE status='booked'").fetchone()
    # examiner02 是烹饪考评员，无电焊资质，不会被分配
    login(client, 'examiner02', 'exam123')
    rv = client.get(f'/examiner/score/{b["id"]}')
    assert rv.status_code == 403
