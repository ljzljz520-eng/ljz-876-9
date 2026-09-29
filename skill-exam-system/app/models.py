"""数据模型：用户、工种、工位、耗材、场次、预约、评分"""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from . import db, login_manager

# 角色
ROLE_CANDIDATE = 'candidate'   # 考生
ROLE_EXAMINER = 'examiner'     # 考评员
ROLE_ADMIN = 'admin'           # 管理员

# 预约状态
ST_BOOKED = 'booked'       # 已预约
ST_SCORED = 'scored'       # 已评分
ST_CANCELLED = 'cancelled' # 已取消
ST_ABSENT = 'absent'       # 缺考

# 评分类别
CAT_STEP = 'step'          # 操作步骤
CAT_PRODUCT = 'product'    # 成品质量
CAT_SAFETY = 'safety'      # 安全行为
CATEGORY_NAMES = {CAT_STEP: '操作步骤', CAT_PRODUCT: '成品质量', CAT_SAFETY: '安全行为'}


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    role = db.Column(db.String(16), nullable=False, default=ROLE_CANDIDATE)
    phone = db.Column(db.String(32))
    # 考评员可评的工种
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    skill = db.relationship('Skill')

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

    def __repr__(self):
        return f'<User {self.username}({self.role})>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class Skill(db.Model):
    """工种：电焊/烹饪/汽修/美容"""
    __tablename__ = 'skills'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16), unique=True, nullable=False)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text)
    duration_minutes = db.Column(db.Integer, default=120)

    workstations = db.relationship('Workstation', backref='skill', lazy=True)
    consumables = db.relationship('Consumable', backref='skill', lazy=True)
    score_items = db.relationship('ScoreItem', backref='skill', lazy=True)


class Workstation(db.Model):
    """工位"""
    __tablename__ = 'workstations'
    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    location = db.Column(db.String(128))
    active = db.Column(db.Boolean, default=True)


class Consumable(db.Model):
    """耗材及库存"""
    __tablename__ = 'consumables'
    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    unit = db.Column(db.String(16), nullable=False)
    stock = db.Column(db.Float, nullable=False, default=0)
    per_exam = db.Column(db.Float, nullable=False, default=1)  # 每场考试用量


class TimeSlot(db.Model):
    """考试场次"""
    __tablename__ = 'time_slots'
    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    capacity = db.Column(db.Integer, nullable=False, default=4)
    status = db.Column(db.String(16), default='open')  # open / closed

    skill = db.relationship('Skill')
    bookings = db.relationship('Booking', backref='slot', lazy=True)

    def active_bookings(self):
        return [b for b in self.bookings if b.status != ST_CANCELLED]

    def remaining(self):
        return self.capacity - len(self.active_bookings())


class Booking(db.Model):
    """预约记录（含评分结果汇总）"""
    __tablename__ = 'bookings'
    id = db.Column(db.Integer, primary_key=True)
    booking_no = db.Column(db.String(32), unique=True, nullable=False)  # 准考证号
    candidate_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    slot_id = db.Column(db.Integer, db.ForeignKey('time_slots.id'), nullable=False)
    workstation_id = db.Column(db.Integer, db.ForeignKey('workstations.id'))
    examiner_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    status = db.Column(db.String(16), nullable=False, default=ST_BOOKED)
    total_score = db.Column(db.Float)
    examiner_comment = db.Column(db.Text)
    scored_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    candidate = db.relationship('User', foreign_keys=[candidate_id])
    examiner = db.relationship('User', foreign_keys=[examiner_id])
    workstation = db.relationship('Workstation')
    scores = db.relationship('Score', backref='booking', lazy=True,
                             cascade='all, delete-orphan')
    consumables_used = db.relationship('BookingConsumable', backref='booking',
                                       lazy=True, cascade='all, delete-orphan')

    def category_subtotal(self, category):
        return sum(s.score for s in self.scores if s.item.category == category)


class BookingConsumable(db.Model):
    """预约占用的耗材"""
    __tablename__ = 'booking_consumables'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    consumable_id = db.Column(db.Integer, db.ForeignKey('consumables.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)

    consumable = db.relationship('Consumable')


class ScoreItem(db.Model):
    """评分项（评分标准）"""
    __tablename__ = 'score_items'
    id = db.Column(db.Integer, primary_key=True)
    skill_id = db.Column(db.Integer, db.ForeignKey('skills.id'), nullable=False)
    category = db.Column(db.String(16), nullable=False)  # step/product/safety
    name = db.Column(db.String(128), nullable=False)
    max_score = db.Column(db.Float, nullable=False)
    sort_order = db.Column(db.Integer, default=0)


class Score(db.Model):
    """评分明细"""
    __tablename__ = 'scores'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey('bookings.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('score_items.id'), nullable=False)
    score = db.Column(db.Float, nullable=False)
    comment = db.Column(db.String(256))

    item = db.relationship('ScoreItem')
    __table_args__ = (db.UniqueConstraint('booking_id', 'item_id', name='uq_booking_item'),)
