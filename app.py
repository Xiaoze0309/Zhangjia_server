import os
from flask import Flask
from flask_login import LoginManager

from config import Config
from models import db, User
from center_app import center_bp

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'center.login'

# 确保上传目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# 注册评级中心 Blueprint
app.register_blueprint(center_bp)


# ============================================================
# 数据库初始化
# ============================================================

def init_db():
    with app.app_context():
        db.create_all()
        # 创建默认管理员（如果不存在）
        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@lanos.local', is_admin=1, is_rater=1)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print('默认管理员已创建: admin / admin123')


if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
