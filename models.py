"""
LanOS 2.5 - 数据模型（原生 sqlite3 版）
不使用 SQLAlchemy，User 类仅供 Flask-Login 使用
"""
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash


class User:
    """Flask-Login 用户对象（从数据库行构建）"""

    def __init__(self, row):
        # row 可以是 sqlite3.Row 或 dict
        data = dict(row) if row else {}
        self.id = data.get('id')
        self.username = data.get('username')
        self.email = data.get('email')
        self.password_hash = data.get('password_hash')
        self.phone = data.get('phone')
        self.is_rater = data.get('is_rater', 0) or 0
        self.is_admin = data.get('is_admin', 0) or 0
        self.rater_department = data.get('rater_department')
        self.rater_euid = data.get('rater_euid')
        self.created_at = data.get('created_at')

    # ---- Flask-Login 必需属性/方法 ----
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

    # ---- 密码 ----
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

    # ---- 角色快捷属性 ----
    @property
    def is_rater_user(self):
        return self.is_rater == 1

    @property
    def is_admin_user(self):
        return self.is_admin == 1


def get_user_by_id(db, user_id):
    """根据 id 查询用户，返回 User 对象或 None"""
    row = db.execute("SELECT * FROM users WHERE id = ?", (int(user_id),)).fetchone()
    return User(row) if row else None


def get_user_by_username(db, username):
    row = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return User(row) if row else None


# ============================================================
# CertOrder 行转字典
# ============================================================

def order_to_dict(row):
    if row is None:
        return None
    d = dict(row)
    # 时间字段保持字符串，不做特殊处理（前端按 ISO 解析）
    return d


# 订单状态映射
STATUS_MAP = {
    'pending': '待支付',
    'paid': '已支付',
    'rating': '评级中',
    'done': '已完成',
    'rejected': '已驳回',
}
