from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model, UserMixin):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    phone = db.Column(db.String(20))
    is_rater = db.Column(db.Integer, default=0)  # 0=普通用户, 1=评级师
    is_admin = db.Column(db.Integer, default=0)  # 0=普通, 1=管理员
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)

    orders = db.relationship('CertOrder', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_rater_user(self):
        return self.is_rater == 1

    @property
    def is_admin_user(self):
        return self.is_admin == 1


class CertOrder(db.Model):
    __tablename__ = 'cert_orders'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_no = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    contact = db.Column(db.String(64), nullable=False)  # 手机号/联系方式
    coin_name = db.Column(db.String(128), nullable=False)
    coin_era = db.Column(db.String(128))
    coin_desc = db.Column(db.Text)
    coin_images = db.Column(db.Text)  # JSON 数组存储图片路径
    status = db.Column(db.String(32), default='pending')
    # pending(待支付) / paid(已支付待评级) / rating(评级中) / done(已完成) / rejected(已驳回)
    pay_proof = db.Column(db.String(256))  # 支付凭证图片路径
    cert_no = db.Column(db.String(64))  # 证书号
    cert_result = db.Column(db.Text)  # 评级结果 JSON
    cert_images = db.Column(db.Text)  # 评级结果图片
    rater_id = db.Column(db.Integer)
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)
    updated_at = db.Column(db.TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'order_no': self.order_no,
            'user_id': self.user_id,
            'contact': self.contact,
            'coin_name': self.coin_name,
            'coin_era': self.coin_era,
            'coin_desc': self.coin_desc,
            'coin_images': self.coin_images,
            'status': self.status,
            'pay_proof': self.pay_proof,
            'cert_no': self.cert_no,
            'cert_result': self.cert_result,
            'cert_images': self.cert_images,
            'rater_id': self.rater_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
