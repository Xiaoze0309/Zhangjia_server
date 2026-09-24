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
    is_rater = db.Column(db.Integer, default=0)       # 0=普通用户, 1=评级师
    is_admin = db.Column(db.Integer, default=0)        # 0=普通, 1=管理员
    rater_department = db.Column(db.String(64))        # 归属部门 slug
    rater_euid = db.Column(db.String(64))              # EUID-CE 评级师编号
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


class Department(db.Model):
    __tablename__ = 'departments'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(64), unique=True, nullable=False)   # jinan/beihai/hechi/lingbao/moscow
    name = db.Column(db.String(128), nullable=False)               # 济南站/北海站...
    euid_prefix = db.Column(db.String(16))                          # EUID 前缀
    pay_qr = db.Column(db.String(256))                              # 收款码图片路径
    is_active = db.Column(db.Integer, default=1)
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)


class DepartmentPricing(db.Model):
    __tablename__ = 'department_pricing'

    id = db.Column(db.Integer, primary_key=True)
    department_slug = db.Column(db.String(64), nullable=False, index=True)
    service_type = db.Column(db.String(16), nullable=False)   # online / offline
    box_type = db.Column(db.String(16), nullable=False)       # PLA / JIN
    has_guarantee = db.Column(db.Integer, default=0)          # 0=不保真, 1=保真
    price = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)


class Coupon(db.Model):
    __tablename__ = 'coupons'

    id = db.Column(db.Integer, primary_key=True)
    efid = db.Column(db.String(64), unique=True, nullable=False)   # EFID 券码
    discount_type = db.Column(db.String(16), default='full')      # full=全免, fixed=减免
    discount_value = db.Column(db.Float, default=0)              # 减免金额（full 时忽略）
    is_used = db.Column(db.Integer, default=0)
    used_by = db.Column(db.Integer)                                # 使用者 user_id
    used_order = db.Column(db.String(64))                         # 使用的订单号
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)
    used_at = db.Column(db.TIMESTAMP)


class LotteryRecord(db.Model):
    __tablename__ = 'lottery_records'

    id = db.Column(db.Integer, primary_key=True)
    euid = db.Column(db.String(64), unique=True, nullable=False)  # EUID 中奖用户编号
    efid = db.Column(db.String(64), unique=True, nullable=False)  # EFID 优惠券码
    username = db.Column(db.String(64))
    prize_type = db.Column(db.String(32), default='free_rating')  # 奖品类型
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)


class CertOrder(db.Model):
    __tablename__ = 'cert_orders'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    order_no = db.Column(db.String(64), unique=True, nullable=False, index=True)  # EPID
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    contact = db.Column(db.String(64), nullable=False)
    coin_name = db.Column(db.String(128), nullable=False)
    coin_era = db.Column(db.String(128))
    coin_desc = db.Column(db.Text)
    coin_images = db.Column(db.Text)        # JSON 数组

    # 部门 & 定价
    department = db.Column(db.String(64))    # 归属部门 slug
    service_type = db.Column(db.String(16), default='online')   # online / offline
    box_type = db.Column(db.String(16), default='PLA')          # PLA / JIN
    has_guarantee = db.Column(db.Integer, default=0)            # 0=不保真, 1=保真
    base_price = db.Column(db.Float)                             # 下单时原价
    final_price = db.Column(db.Float)                           # 下单时实付
    coupon_code = db.Column(db.String(64))                      # 使用的券码

    status = db.Column(db.String(32), default='pending')
    # pending(待支付) / paid(已支付待评级) / rating(评级中) / done(已完成) / rejected(已驳回)

    pay_proof = db.Column(db.String(256))
    cert_no = db.Column(db.String(64))
    cert_result = db.Column(db.Text)        # JSON
    cert_images = db.Column(db.Text)        # JSON
    rater_id = db.Column(db.Integer)

    # 邮寄信息
    tracking_no = db.Column(db.String(128))         # 邮寄单号
    return_address = db.Column(db.Text)             # 回寄地址

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
            'department': self.department,
            'service_type': self.service_type,
            'box_type': self.box_type,
            'has_guarantee': self.has_guarantee,
            'base_price': self.base_price,
            'final_price': self.final_price,
            'coupon_code': self.coupon_code,
            'status': self.status,
            'pay_proof': self.pay_proof,
            'cert_no': self.cert_no,
            'cert_result': self.cert_result,
            'cert_images': self.cert_images,
            'rater_id': self.rater_id,
            'tracking_no': self.tracking_no,
            'return_address': self.return_address,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
