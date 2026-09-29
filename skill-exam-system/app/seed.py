"""初始化数据库并写入基础数据：flask --app run init-db / seed"""
import datetime
from werkzeug.security import generate_password_hash
from .db import get_db, init_db

SKILLS = [('welding', '电焊'), ('cooking', '烹饪'),
          ('auto_repair', '汽修'), ('beauty', '美容')]

WORKSTATIONS = {
    'welding':    [('电焊1号工位', '实训楼A101'), ('电焊2号工位', '实训楼A102')],
    'cooking':    [('烹饪1号工位', '实训楼B201'), ('烹饪2号工位', '实训楼B202')],
    'auto_repair': [('汽修1号工位', '实训车间C1'), ('汽修2号工位', '实训车间C2')],
    'beauty':     [('美容1号工位', '实训楼D301'), ('美容2号工位', '实训楼D302')],
}

CONSUMABLES = {
    'welding':    [('焊条', '根', 500, 10), ('试件钢板', '块', 100, 2),
                   ('保护气体', '瓶', 40, 1)],
    'cooking':    [('食材包', '份', 60, 1), ('调料包', '份', 60, 1),
                   ('燃气', '罐', 20, 1)],
    'auto_repair': [('机油', '升', 200, 4), ('机油滤清器', '个', 50, 1),
                    ('刹车片', '套', 30, 1)],
    'beauty':     [('护肤品套装', '套', 40, 1), ('一次性用品包', '包', 80, 1),
                   ('假睫毛练习装', '盒', 30, 1)],
}

# 评分标准：(category, seq, 项目名, 说明, 满分)
RUBRICS = {
    'welding': [
        ('step', 1, '焊前准备与设备检查', '焊机、电缆、工件检查与参数设置', 10),
        ('step', 2, '引弧与运条操作', '引弧手法、运条速度与角度', 20),
        ('step', 3, '焊缝接头与收弧处理', '接头平整、收弧无弧坑', 15),
        ('step', 4, '焊后清理', '清渣、飞溅处理、工件归位', 5),
        ('product', 1, '焊缝外观成型', '焊缝均匀、波纹细密、无咬边', 25),
        ('product', 2, '焊缝尺寸与缺陷控制', '尺寸达标、无气孔夹渣裂纹', 15),
        ('safety', 1, '个人防护穿戴', '面罩、焊工服、手套、绝缘鞋', 5),
        ('safety', 2, '安全用电与防火', '规范用电、清理易燃物、灭火器就位', 5),
    ],
    'cooking': [
        ('step', 1, '原料验收与初加工', '原料检查、清洗、初步处理', 10),
        ('step', 2, '刀工处理', '刀法规范、粗细均匀、形状达标', 15),
        ('step', 3, '火候与烹制过程', '油温控制、投料顺序、火候掌握', 20),
        ('step', 4, '装盘与点缀', '装盘规范、造型美观', 5),
        ('product', 1, '口味与质感', '味型准确、质地符合要求', 25),
        ('product', 2, '色泽与造型', '色泽自然、形态完整美观', 15),
        ('safety', 1, '食品卫生操作', '生熟分开、操作台清洁、个人卫生', 5),
        ('safety', 2, '用火用电安全', '规范使用灶具、人走火灭', 5),
    ],
    'auto_repair': [
        ('step', 1, '故障诊断流程', '问诊、检测、诊断思路清晰', 15),
        ('step', 2, '拆装操作规范', '工具选用正确、拆装顺序规范', 15),
        ('step', 3, '检测与调试', '维修后检测、参数调试达标', 15),
        ('step', 4, '工具归位与场地整理', '工具清点归位、场地清洁', 5),
        ('product', 1, '故障排除效果', '故障彻底排除、功能恢复正常', 25),
        ('product', 2, '维修质量', '装配到位、无漏装错装、扭矩达标', 15),
        ('safety', 1, '设备安全操作', '举升机、千斤顶等规范使用', 5),
        ('safety', 2, '个人防护', '工作服、手套、护目镜穿戴', 5),
    ],
    'beauty': [
        ('step', 1, '皮肤分析与准备', '皮肤判断准确、清洁消毒到位', 10),
        ('step', 2, '操作手法规范', '手法正确、力度适中、流程完整', 20),
        ('step', 3, '产品使用规范', '产品选择恰当、用量合理', 15),
        ('step', 4, '收尾整理', '工具消毒归位、台面整理', 5),
        ('product', 1, '整体效果', '妆面/护理整体效果达标', 25),
        ('product', 2, '细节处理', '边缘过渡、对称性等细节', 15),
        ('safety', 1, '消毒卫生', '器械消毒、一客一换', 5),
        ('safety', 2, '仪器安全使用', '仪器操作规范、参数设置正确', 5),
    ],
}


def seed():
    init_db()
    db = get_db()

    # 工种
    skill_ids = {}
    for code, name in SKILLS:
        cur = db.execute('INSERT INTO skills (code, name) VALUES (?,?)', (code, name))
        skill_ids[code] = cur.lastrowid

    # 工位
    for code, ws_list in WORKSTATIONS.items():
        for name, loc in ws_list:
            db.execute('INSERT INTO workstations (skill_id, name, location)'
                       ' VALUES (?,?,?)', (skill_ids[code], name, loc))

    # 耗材
    for code, items in CONSUMABLES.items():
        for name, unit, stock, qty in items:
            db.execute('INSERT INTO consumables (skill_id, name, unit, stock, qty_per_exam)'
                       ' VALUES (?,?,?,?,?)', (skill_ids[code], name, unit, stock, qty))

    # 评分标准
    for code, items in RUBRICS.items():
        for cat, seq, name, desc, max_score in items:
            db.execute('INSERT INTO rubric_items (skill_id, category, seq, name, description, max_score)'
                       ' VALUES (?,?,?,?,?,?)',
                       (skill_ids[code], cat, seq, name, desc, max_score))

    # 账号：admin/admin123；examiner01~04/exam123；candidate01~02/cand123
    db.execute("INSERT INTO users (username, password_hash, role, real_name)"
               " VALUES ('admin', ?, 'admin', '系统管理员')",
               (generate_password_hash('admin123'),))
    examiners = [('examiner01', '王焊评', 'welding'), ('examiner02', '李厨评', 'cooking'),
                 ('examiner03', '张修评', 'auto_repair'), ('examiner04', '刘美评', 'beauty')]
    for username, real_name, code in examiners:
        cur = db.execute("INSERT INTO users (username, password_hash, role, real_name)"
                         " VALUES (?, ?, 'examiner', ?)",
                         (username, generate_password_hash('exam123'), real_name))
        db.execute('INSERT INTO examiner_skills (examiner_id, skill_id) VALUES (?,?)',
                   (cur.lastrowid, skill_ids[code]))
    candidates = [('candidate01', '陈考生', '110101200101011234'),
                  ('candidate02', '林考生', '110101200202022345')]
    for username, real_name, id_card in candidates:
        db.execute("INSERT INTO users (username, password_hash, role, real_name, id_card)"
                   " VALUES (?, ?, 'candidate', ?, ?)",
                   (username, generate_password_hash('cand123'), real_name, id_card))

    # 未来三天的场次：每天上午/下午各一场，覆盖四个工种
    today = datetime.date.today()
    slots = [('09:00', '11:00'), ('14:00', '16:00')]
    for day_offset in range(1, 4):
        d = (today + datetime.timedelta(days=day_offset)).isoformat()
        for i, (code, _) in enumerate(SKILLS):
            start, end = slots[i % 2]
            db.execute('INSERT INTO exam_sessions (skill_id, exam_date, start_time, end_time)'
                       ' VALUES (?,?,?,?)', (skill_ids[code], d, start, end))
    db.commit()
    print('数据库初始化完成，基础数据已写入。')
    print('账号：admin/admin123 | examiner01~04/exam123 | candidate01~02/cand123')
