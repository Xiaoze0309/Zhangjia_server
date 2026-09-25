"""
LanOS 2.5 - 原生 sqlite3 数据库模块
不使用 Flask-SQLAlchemy，使用标准库 sqlite3
"""
import os
import sqlite3
from datetime import datetime
from flask import g, current_app

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, 'lanos.db')


def _convert_timestamp(val):
    """将 sqlite 中的 TIMESTAMP 字符串转为 datetime 对象"""
    if val is None:
        return None
    if isinstance(val, bytes):
        val = val.decode('utf-8')
    val = val.strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S',
                '%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%d'):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return val


# 注册 TIMESTAMP 类型转换器（基于列声明类型）
sqlite3.register_converter("TIMESTAMP", _convert_timestamp)


def get_db():
    """获取数据库连接（基于 flask.g 的请求级连接）"""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row  # 让行可以用列名访问
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    """请求结束时关闭数据库连接"""
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_app(app):
    """注册到 Flask app：请求结束自动关闭连接"""
    app.teardown_appcontext(close_db)


# ============================================================
# 数据库 Schema
# ============================================================

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    phone TEXT,
    is_rater INTEGER DEFAULT 0,
    is_admin INTEGER DEFAULT 0,
    rater_department TEXT,
    rater_euid TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    euid_prefix TEXT,
    pay_qr TEXT,
    is_active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS department_pricing (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    department_slug TEXT NOT NULL,
    service_type TEXT NOT NULL,
    box_type TEXT NOT NULL,
    has_guarantee INTEGER DEFAULT 0,
    price REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_pricing_dept ON department_pricing(department_slug);

CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    efid TEXT UNIQUE NOT NULL,
    discount_type TEXT DEFAULT 'full',
    discount_value REAL DEFAULT 0,
    is_used INTEGER DEFAULT 0,
    used_by INTEGER,
    used_order TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lottery_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    euid TEXT UNIQUE NOT NULL,
    efid TEXT UNIQUE NOT NULL,
    username TEXT,
    prize_type TEXT DEFAULT 'free_rating',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    type TEXT DEFAULT 'info',
    is_read INTEGER DEFAULT 0,
    link TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS cert_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_no TEXT UNIQUE NOT NULL,
    user_id INTEGER,
    contact TEXT NOT NULL,
    coin_name TEXT NOT NULL,
    coin_era TEXT,
    coin_desc TEXT,
    coin_images TEXT,
    department TEXT,
    service_type TEXT DEFAULT 'online',
    box_type TEXT DEFAULT 'PLA',
    has_guarantee INTEGER DEFAULT 0,
    base_price REAL,
    final_price REAL,
    coupon_code TEXT,
    status TEXT DEFAULT 'pending',
    pay_proof TEXT,
    cert_no TEXT,
    cert_result TEXT,
    cert_images TEXT,
    rater_id INTEGER,
    tracking_no TEXT,
    return_address TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
CREATE INDEX IF NOT EXISTS idx_orders_order_no ON cert_orders(order_no);
CREATE INDEX IF NOT EXISTS idx_orders_cert_no ON cert_orders(cert_no);
CREATE INDEX IF NOT EXISTS idx_orders_contact ON cert_orders(contact);
CREATE INDEX IF NOT EXISTS idx_orders_dept ON cert_orders(department);
"""


def init_db_schema():
    """创建所有表（如果不存在）"""
    conn = sqlite3.connect(DATABASE)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# ============================================================
# 行转字典辅助函数
# ============================================================

def row_to_dict(row):
    """sqlite3.Row -> dict"""
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    """list of sqlite3.Row -> list of dict"""
    return [dict(r) for r in rows]
