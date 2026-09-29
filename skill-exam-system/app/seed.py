"""初始化数据库与种子数据"""
from datetime import datetime, timedelta
from . import db
from .models import (User, Skill, Workstation, Consumable, TimeSlot, ScoreItem,
                     ROLE_ADMIN, ROLE_EXAMINER, ROLE_CANDIDATE,
                     CAT_STEP, CAT_PRODUCT, CAT_SAFETY)

# 各工种评分标准：(类别, 评分项, 满分)
RUBRICS = {
    'WELD': [  # 电焊
        (CAT_STEP, '焊前准备与设备检查', 10),
        (CAT_STEP, '引弧与运条操作规范', 15),
        (CAT_STEP, '焊接参数控制', 10),
        (CAT_STEP, '焊后清理与自检', 5),
        (CAT_PRODUCT, '焊缝外观成型', 15),
        (CAT_PRODUCT, '焊缝尺寸精度', 10),
        (CAT_PRODUCT, '无气孔夹渣裂纹等缺陷', 15),
        (CAT_SAFETY, '防护用品佩戴', 8),
        (CAT_SAFETY, '用电与防火安全', 8),
        (CAT_SAFETY, '场地整理与设备归位', 4),
    ],
    'COOK': [  # 烹饪
        (CAT_STEP, '原料准备与初加工', 10),
        (CAT_STEP, '刀工与切配规范', 10),
        (CAT_STEP, '火候与烹调过程控制', 15),
        (CAT_STEP, '调味与出锅装盘', 5),
        (CAT_PRODUCT, '色泽与形态', 10),
        (CAT_PRODUCT, '口味与质感', 20),
        (CAT_PRODUCT, '卫生与装盘美观', 10),
        (CAT_SAFETY, '食品卫生操作', 8),
        (CAT_SAFETY, '用火用气安全', 8),
        (CAT_SAFETY, '刀具规范使用', 4),
    ],
    'AUTO': [  # 汽修
        (CAT_STEP, '故障问诊与诊断流程', 12),
        (CAT_STEP, '规范拆卸与部件保护', 10),
        (CAT_STEP, '维修/更换操作规范', 13),
        (CAT_STEP, '装复与功能测试', 5),
        (CAT_PRODUCT, '故障彻底排除', 20),
        (CAT_PRODUCT, '装配质量与扭矩规范', 10),
        (CAT_PRODUCT, '维修后清洁度', 10),
        (CAT_SAFETY, '车辆举升与固定安全', 8),
        (CAT_SAFETY, '工具设备规范使用', 8),
        (CAT_SAFETY, '用电与油液安全', 4),
    ],
    'BEAUTY': [  # 美容
        (CAT_STEP, '皮肤分析与方案设计', 10),
        (CAT_STEP, '清洁与准备工作', 10),
        (CAT_STEP, '护理手法规范操作', 15),
        (CAT_STEP, '仪器规范使用', 5),
        (CAT_PRODUCT, '护理效果呈现', 20),
        (CAT_PRODUCT, '流程完整与时长控制', 10),
        (CAT_PRODUCT, '顾客舒适度体验', 10),
        (CAT_SAFETY, '卫生消毒规范', 8),
        (CAT_SAFETY, '产品安全与过敏防护', 8),
        (CAT_SAFETY, '操作力度与安全意识', 4),
    ],
}

SKILLS = [
    ('WELD', '电焊', '熔化焊接与热切割作业实操考核', 120),
    ('COOK', '烹饪', '中式烹调实操考核', 90),
    ('AUTO', '汽修', '汽车维修工实操考核', 120),
    ('BEAUTY', '美容', '美容师实操考核', 90),
]

WORKSTATIONS = {
    'WELD': [('电焊工位1号', '实训楼A区101'), ('电焊工位2号', '实训楼A区101'),
             ('电焊工位3号', '实训楼A区102'), ('电焊工位4号', '实训楼A区102')],
    'COOK': [('烹饪工位1号', '实训楼B区201'), ('烹饪工位2号', '实训楼B区201'),
             ('烹饪工位3号', '实训楼B区202'), ('烹饪工位4号', '实训楼B区202')],
    'AUTO': [('汽修工位1号', '实训楼C区301'), ('汽修工位2号', '实训楼C区301'),
             ('汽修工位3号', '实训楼C区302'), ('汽修工位4号', '实训楼C区302')],
    'BEAUTY': [('美容工位1号', '实训楼D区401'), ('美容工位2号', '实训楼D区401'),
               ('美容工位3号', '实训楼D区402'), ('美容工位4号', '实训楼D区402')],
}

# (名称, 单位, 初始库存, 每场用量)
CONSUMABLES = {
    'WELD': [('焊条', '根', 500, 10), ('钢板试件', '块', 100, 2),
             ('防护面罩耗材', '套', 50, 1)],
    'COOK': [('食材原料包', '份', 80, 1), ('调味料套装', '套', 60, 1),
             ('一次性手套', '双', 200, 2)],
    'AUTO': [('机油', '升', 100, 4), ('滤清器', '个', 50, 1),
             ('常用易损件包', '套', 40, 1)],
    'BEAUTY': [('护理产品套装', '套', 60, 1), ('一次性床单', '张', 120, 1),
               ('消毒用品包', '包', 100, 1)],
}

EXAMINERS = {
    'WELD': [('exam_weld1', '王焊明'), ('exam_weld2', '李接华'),
             ('exam_weld3', '张熔坚'), ('exam_weld4', '刘弧光')],
    'COOK': [('exam_cook1', '张厨神'), ('exam_cook2', '刘味鲜'),
             ('exam_cook3', '陈火候'), ('exam_cook4', '杨刀工')],
    'AUTO': [('exam_auto1', '陈机修'), ('exam_auto2', '赵诊断'),
             ('exam_auto3', '孙电路'), ('exam_auto4', '周底盘')],
    'BEAUTY': [('exam_beauty1', '孙美颜'), ('exam_beauty2', '周护肤'),
               ('exam_beauty3', '吴调理'), ('exam_beauty4', '郑仪器')],
}


def init_db(app, with_seed=True):
    with app.app_context():
        db.drop_all()
        db.create_all()
        if with_seed:
            seed()


def seed():
    # 管理员
    admin = User(username='admin', name='系统管理员', role=ROLE_ADMIN)
    admin.set_password('admin123')
    db.session.add(admin)

    # 工种
    skill_map = {}
    for code, name, desc, dur in SKILLS:
        s = Skill(code=code, name=name, description=desc, duration_minutes=dur)
        db.session.add(s)
        skill_map[code] = s
    db.session.flush()

    # 评分标准
    for code, items in RUBRICS.items():
        for i, (cat, name, max_score) in enumerate(items):
            db.session.add(ScoreItem(skill_id=skill_map[code].id, category=cat,
                                     name=name, max_score=max_score, sort_order=i))

    # 工位
    for code, ws_list in WORKSTATIONS.items():
        for name, loc in ws_list:
            db.session.add(Workstation(skill_id=skill_map[code].id,
                                       name=name, location=loc))

    # 耗材
    for code, cs_list in CONSUMABLES.items():
        for name, unit, stock, per_exam in cs_list:
            db.session.add(Consumable(skill_id=skill_map[code].id, name=name,
                                      unit=unit, stock=stock, per_exam=per_exam))

    # 考评员
    for code, ex_list in EXAMINERS.items():
        for username, name in ex_list:
            u = User(username=username, name=name, role=ROLE_EXAMINER,
                     skill_id=skill_map[code].id)
            u.set_password('exam123')
            db.session.add(u)

    # 演示考生
    for i in range(1, 4):
        u = User(username=f'student{i}', name=f'考生{i}号', role=ROLE_CANDIDATE,
                 phone=f'1380000000{i}')
        u.set_password('123456')
        db.session.add(u)

    # 未来 7 天的场次（每工种每天上午/下午各一场）
    base = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    for day in range(1, 8):
        for code, skill in skill_map.items():
            for hour in (9, 14):
                start = base + timedelta(days=day, hours=hour)
                end = start + timedelta(minutes=skill.duration_minutes)
                db.session.add(TimeSlot(skill_id=skill.id, start_time=start,
                                        end_time=end, capacity=4))

    db.session.commit()
    print('数据库初始化完成，种子数据已写入。')
    print('  管理员: admin / admin123')
    print('  考评员: exam_weld1 等 / exam123')
    print('  考生:   student1~3 / 123456')
