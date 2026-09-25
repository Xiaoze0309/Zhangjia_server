import os
from datetime import datetime, date
from flask import Flask
from flask.json.provider import DefaultJSONProvider
from flask_login import LoginManager

from config import Config
from db import get_db, init_app as init_db_app, init_db_schema
from models import User, get_user_by_id
from center_app import center_bp

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class ISODateJSONProvider(DefaultJSONProvider):
    """将 datetime/date 序列化为 ISO 格式字符串，与前端解析保持一致"""
    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat(sep=' ')
        return super().default(o)


app = Flask(__name__)
app.json = ISODateJSONProvider(app)
app.config.from_object(Config)

# 注册数据库连接管理（请求结束自动关闭）
init_db_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'center.login'

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    return get_user_by_id(db, user_id)


# 注册评级中心 Blueprint
app.register_blueprint(center_bp)


# ============================================================
# 数据库初始化
# ============================================================

def init_db():
    """创建表 + 默认管理员"""
    init_db_schema()
    with app.app_context():
        db = get_db()
        existing = db.execute(
            "SELECT id FROM users WHERE username = 'admin'"
        ).fetchone()
        if not existing:
            from werkzeug.security import generate_password_hash
            db.execute(
                "INSERT INTO users (username, email, password_hash, is_rater, is_admin, rater_department, rater_euid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                ('admin', 'admin@lanos.local', generate_password_hash('admin123'),
                 1, 1, 'jinan', 'EUID-CE-0001')
            )
            db.commit()
            print('默认管理员已创建: admin / admin123')


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
