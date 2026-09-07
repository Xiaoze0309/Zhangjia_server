-- ========== 现有表新增字段 ==========

-- users 表
ALTER TABLE users ADD COLUMN activation_errors INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN activation_first_error TIMESTAMP;
ALTER TABLE users ADD COLUMN icelocker_triggered INTEGER DEFAULT 0;
ALTER TABLE users ADD COLUMN illegal_report_tag INTEGER DEFAULT 0;

-- messages 表
ALTER TABLE messages ADD COLUMN is_system INTEGER DEFAULT 0;

-- ========== 新增表 ==========

-- 管理员激活码表（动态，非固定）
CREATE TABLE IF NOT EXISTS admin_activation_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    target_euid TEXT NOT NULL,
    target_email TEXT NOT NULL,
    generated_by INTEGER NOT NULL,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0,
    used_at TIMESTAMP,
    FOREIGN KEY (generated_by) REFERENCES users(id)
);

-- SUkey 表（Warnlocker 解冻用）
CREATE TABLE IF NOT EXISTS sukeys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sukey TEXT NOT NULL UNIQUE,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    used INTEGER DEFAULT 0,
    used_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- OEM 解锁记录
CREATE TABLE IF NOT EXISTS oem_unlock_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    oem_type TEXT NOT NULL,
    token TEXT,
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    used INTEGER DEFAULT 0,
    used_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- XZlocker-s 投票记录
CREATE TABLE IF NOT EXISTS xzlocker_s_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_admin_id INTEGER NOT NULL,
    trigger_reason TEXT NOT NULL,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'active',
    result TEXT,
    FOREIGN KEY (target_admin_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS xzlocker_s_vote_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vote_id INTEGER NOT NULL,
    voter_id INTEGER NOT NULL,
    choice TEXT NOT NULL,
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vote_id, voter_id),
    FOREIGN KEY (vote_id) REFERENCES xzlocker_s_votes(id),
    FOREIGN KEY (voter_id) REFERENCES users(id)
);

-- 议会投票记录（Warnlocker 软冻用）
CREATE TABLE IF NOT EXISTS parliament_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vote_id TEXT NOT NULL,
    initiated_by INTEGER,
    trigger_reason TEXT NOT NULL,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'active',
    result TEXT
);

CREATE TABLE IF NOT EXISTS parliament_vote_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vote_id TEXT NOT NULL,
    voter_id INTEGER NOT NULL,
    choice TEXT NOT NULL,
    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(vote_id, voter_id),
    FOREIGN KEY (voter_id) REFERENCES users(id)
);

-- XZlocker 状态
CREATE TABLE IF NOT EXISTS xzlocker_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    locked INTEGER DEFAULT 0,
    triggered_at TIMESTAMP,
    triggered_by TEXT,
    unlock_attempts INTEGER DEFAULT 0,
    last_attempt_at TIMESTAMP,
    recovery_token TEXT,
    recovery_expires_at TIMESTAMP,
    recovery_used INTEGER DEFAULT 0
);
INSERT OR IGNORE INTO xzlocker_state (id, locked) VALUES (1, 0);

-- Windlocker 状态
CREATE TABLE IF NOT EXISTS windlocker_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    locked INTEGER DEFAULT 0,
    triggered_at TIMESTAMP,
    triggered_by TEXT,
    reason TEXT,
    unlock_attempts INTEGER DEFAULT 0,
    last_attempt_at TIMESTAMP
);
INSERT OR IGNORE INTO windlocker_state (id, locked) VALUES (1, 0);

-- Icelocker 记录
CREATE TABLE IF NOT EXISTS icelocker_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reason TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    released_at TIMESTAMP,
    released_by INTEGER,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (released_by) REFERENCES users(id)
);

-- ========== 系统设置表 ==========
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
INSERT OR IGNORE INTO settings (key, value) VALUES ('app_version', 'V2.7');
INSERT OR IGNORE INTO settings (key, value) VALUES ('max_admin_level_3', '10');
