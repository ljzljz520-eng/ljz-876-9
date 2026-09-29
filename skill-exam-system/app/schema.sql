-- 职业技能实操预约评分系统 数据库结构
DROP TABLE IF EXISTS scores;
DROP TABLE IF EXISTS results;
DROP TABLE IF EXISTS booking_consumables;
DROP TABLE IF EXISTS bookings;
DROP TABLE IF EXISTS exam_sessions;
DROP TABLE IF EXISTS rubric_items;
DROP TABLE IF EXISTS consumables;
DROP TABLE IF EXISTS workstations;
DROP TABLE IF EXISTS examiner_skills;
DROP TABLE IF EXISTS skills;
DROP TABLE IF EXISTS users;

-- 用户表：考生 candidate / 考评员 examiner / 管理员 admin
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('candidate','examiner','admin')),
    real_name     TEXT NOT NULL,
    id_card       TEXT,               -- 考生身份证号（成绩表用）
    phone         TEXT,
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 工种：电焊 / 烹饪 / 汽修 / 美容
CREATE TABLE skills (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL
);

-- 工位（隶属于某工种）
CREATE TABLE workstations (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id INTEGER NOT NULL REFERENCES skills(id),
    name     TEXT NOT NULL,
    location TEXT,
    status   TEXT NOT NULL DEFAULT 'available' CHECK (status IN ('available','maintenance'))
);

-- 耗材（按工种配置，每场考试固定消耗）
CREATE TABLE consumables (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id     INTEGER NOT NULL REFERENCES skills(id),
    name         TEXT NOT NULL,
    unit         TEXT NOT NULL DEFAULT '份',
    stock        INTEGER NOT NULL DEFAULT 0,
    qty_per_exam INTEGER NOT NULL DEFAULT 1
);

-- 考评员资质（可考评哪些工种）
CREATE TABLE examiner_skills (
    examiner_id INTEGER NOT NULL REFERENCES users(id),
    skill_id    INTEGER NOT NULL REFERENCES skills(id),
    PRIMARY KEY (examiner_id, skill_id)
);

-- 考试场次
CREATE TABLE exam_sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id   INTEGER NOT NULL REFERENCES skills(id),
    exam_date  DATE NOT NULL,
    start_time TEXT NOT NULL,
    end_time   TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','finished')),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 预约记录：同一场次同一工位只能有一条有效预约
CREATE TABLE bookings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_no     TEXT UNIQUE NOT NULL,          -- 预约编号
    candidate_id   INTEGER NOT NULL REFERENCES users(id),
    session_id     INTEGER NOT NULL REFERENCES exam_sessions(id),
    workstation_id INTEGER NOT NULL REFERENCES workstations(id),
    examiner_id    INTEGER NOT NULL REFERENCES users(id),
    status         TEXT NOT NULL DEFAULT 'booked'
                   CHECK (status IN ('booked','completed','cancelled')),
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- 部分唯一索引：取消的预约不占工位
CREATE UNIQUE INDEX idx_booking_session_ws_active
    ON bookings(session_id, workstation_id) WHERE status != 'cancelled';

-- 预约时分配的耗材明细
CREATE TABLE booking_consumables (
    booking_id     INTEGER NOT NULL REFERENCES bookings(id),
    consumable_id  INTEGER NOT NULL REFERENCES consumables(id),
    qty            INTEGER NOT NULL,
    PRIMARY KEY (booking_id, consumable_id)
);

-- 评分标准：category = step(操作步骤) / product(成品质量) / safety(安全行为)
CREATE TABLE rubric_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id    INTEGER NOT NULL REFERENCES skills(id),
    category    TEXT NOT NULL CHECK (category IN ('step','product','safety')),
    seq         INTEGER NOT NULL DEFAULT 0,
    name        TEXT NOT NULL,
    description TEXT,
    max_score   REAL NOT NULL
);

-- 评分记录（每预约每项一条）
CREATE TABLE scores (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id    INTEGER NOT NULL REFERENCES bookings(id),
    rubric_item_id INTEGER NOT NULL REFERENCES rubric_items(id),
    score         REAL NOT NULL,
    comment       TEXT,
    scored_by     INTEGER NOT NULL REFERENCES users(id),
    scored_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (booking_id, rubric_item_id)
);

-- 成绩结果：published 控制考生是否可见
CREATE TABLE results (
    booking_id   INTEGER PRIMARY KEY REFERENCES bookings(id),
    total_score  REAL NOT NULL,
    max_score    REAL NOT NULL,
    passed       INTEGER NOT NULL DEFAULT 0,
    published    INTEGER NOT NULL DEFAULT 0,
    published_at TIMESTAMP
);
