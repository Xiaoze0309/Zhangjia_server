import os
import json
import random
import time
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect, url_for,
                   jsonify, send_from_directory, abort, flash, current_app)
from flask_login import login_user, logout_user, current_user

from config import Config
from models import db, User, CertOrder
from decorators import login_required, rater_required, admin_required

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# ============================================================
# Flask Blueprint：评级中心
# ============================================================
center_bp = Blueprint('center', __name__)

# ACME HTTP-01 验证目录
ACME_CHALLENGE_DIR = os.path.join(BASE_DIR, '.well-known', 'acme-challenge')
os.makedirs(ACME_CHALLENGE_DIR, exist_ok=True)


# ============================================================
# 工具函数
# ============================================================

def get_site_type(host):
    """根据 request.host 判断站点类型"""
    if not host:
        return 'main'
    host = host.lower()
    if host.startswith('intro.'):
        return 'intro'
    if host.startswith('talk.'):
        return 'talk'
    if host.startswith('beta.'):
        return 'beta'
    if 'zhangjiacenter' in host:
        return 'center'
    return 'main'


def generate_order_no():
    """生成订单号：CZ + 年月日时分秒 + 3位随机数"""
    now = datetime.now()
    ts = now.strftime('%Y%m%d%H%M%S')
    rand = ''.join([str(random.randint(0, 9)) for _ in range(3)])
    return f'CZ{ts}{rand}'


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def save_upload(file_storage, subfolder=''):
    """保存上传文件，返回相对路径"""
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename):
        return None
    ext = file_storage.filename.rsplit('.', 1)[1].lower()
    filename = f'{int(time.time() * 1000)}_{random.randint(1000, 9999)}.{ext}'
    folder = os.path.join(current_app.config['UPLOAD_FOLDER'], subfolder)
    os.makedirs(folder, exist_ok=True)
    filepath = os.path.join(folder, filename)
    file_storage.save(filepath)
    return f'uploads/{subfolder}/{filename}' if subfolder else f'uploads/{filename}'


# ============================================================
# 首页分流（根据 host）
# ============================================================

@center_bp.route('/')
def index():
    host = request.host
    site = get_site_type(host)

    if site == 'intro':
        return render_template('intro.html')
    if site == 'talk':
        return render_template('talk.html')
    if site == 'beta':
        return render_template('beta/index.html')
    if site == 'center':
        return render_template('center/index.html')
    return render_template('index.html')


@center_bp.route('/about')
def about():
    """关于我们 -> 跳转 intro 站"""
    return redirect('https://intro.zhangjiacoins.dpdns.org')


# ============================================================
# 用户认证（主站复用）
# ============================================================

@center_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username')
        password = data.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            if request.is_json:
                return jsonify({'success': True, 'message': '登录成功'})
            return redirect(url_for('center.index'))
        if request.is_json:
            return jsonify({'success': False, 'message': '用户名或密码错误'}), 401
        flash('用户名或密码错误', 'error')
    return render_template('login.html')


@center_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('center.index'))


@center_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json() if request.is_json else request.form
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        phone = data.get('phone', '')
        if not username or not email or not password:
            return jsonify({'success': False, 'message': '信息不完整'}), 400
        if User.query.filter_by(username=username).first():
            return jsonify({'success': False, 'message': '用户名已存在'}), 400
        if User.query.filter_by(email=email).first():
            return jsonify({'success': False, 'message': '邮箱已注册'}), 400
        user = User(username=username, email=email, phone=phone)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        if request.is_json:
            return jsonify({'success': True, 'message': '注册成功'})
        return redirect(url_for('center.index'))
    return render_template('register.html')


# ============================================================
# 评级中心 - 页面路由
# ============================================================

@center_bp.route('/center')
def center_index():
    return render_template('center/index.html')


@center_bp.route('/center/apply')
def center_apply():
    return render_template('center/apply.html')


@center_bp.route('/center/pay/<order_no>')
def center_pay(order_no):
    order = CertOrder.query.filter_by(order_no=order_no).first()
    if not order:
        abort(404)
    return render_template('center/pay.html', order=order)


@center_bp.route('/center/query/<cert_no>')
def center_query(cert_no):
    order = CertOrder.query.filter_by(cert_no=cert_no).first()
    if not order:
        # 订单号也可查
        order = CertOrder.query.filter_by(order_no=cert_no).first()
    return render_template('center/query.html', order=order, keyword=cert_no)


@center_bp.route('/center/rater')
@rater_required
def center_rater():
    return render_template('center/rater.html')


# ============================================================
# 评级中心 - API 端点
# ============================================================

@center_bp.route('/api/center/apply', methods=['POST'])
@login_required
def api_apply():
    """提交评级申请"""
    contact = request.form.get('contact', '').strip()
    coin_name = request.form.get('coin_name', '').strip()
    coin_era = request.form.get('coin_era', '').strip()
    coin_desc = request.form.get('coin_desc', '').strip()

    if not contact or not coin_name:
        return jsonify({'success': False, 'message': '联系方式和币种名称必填'}), 400

    # 处理图片上传
    images = []
    for key in request.files:
        file = request.files[key]
        if file and file.filename:
            path = save_upload(file, 'coins')
            if path:
                images.append(path)

    order = CertOrder(
        order_no=generate_order_no(),
        user_id=current_user.id,
        contact=contact,
        coin_name=coin_name,
        coin_era=coin_era,
        coin_desc=coin_desc,
        coin_images=json.dumps(images, ensure_ascii=False) if images else None,
        status='pending',
    )
    db.session.add(order)
    db.session.commit()

    return jsonify({
        'success': True,
        'message': '申请提交成功',
        'order_no': order.order_no,
        'redirect': url_for('center.center_pay', order_no=order.order_no),
    })


@center_bp.route('/api/center/query/<keyword>')
def api_query(keyword):
    """查询：订单号 / 证书号 / 手机号"""
    keyword = keyword.strip()
    if not keyword:
        return jsonify({'success': False, 'message': '请输入查询关键词'}), 400

    order = None
    # 优先按证书号查
    order = CertOrder.query.filter_by(cert_no=keyword).first()
    # 按订单号查
    if not order:
        order = CertOrder.query.filter_by(order_no=keyword).first()
    # 按手机号查（取最新一条）
    if not order:
        order = CertOrder.query.filter_by(contact=keyword).order_by(
            CertOrder.created_at.desc()).first()

    if not order:
        return jsonify({'success': False, 'message': '未找到相关记录'}), 404

    data = order.to_dict()
    # 解析 JSON 字段
    if data.get('coin_images'):
        try:
            data['coin_images'] = json.loads(data['coin_images'])
        except Exception:
            pass
    if data.get('cert_result'):
        try:
            data['cert_result'] = json.loads(data['cert_result'])
        except Exception:
            pass
    return jsonify({'success': True, 'data': data})


@center_bp.route('/api/center/upload_proof/<order_no>', methods=['POST'])
@login_required
def api_upload_proof(order_no):
    """上传支付凭证"""
    order = CertOrder.query.filter_by(order_no=order_no).first()
    if not order:
        return jsonify({'success': False, 'message': '订单不存在'}), 404
    if order.user_id != current_user.id and not current_user.is_admin_user:
        return jsonify({'success': False, 'message': '无权操作该订单'}), 403

    file = request.files.get('proof')
    if not file or not file.filename:
        return jsonify({'success': False, 'message': '请上传凭证图片'}), 400

    path = save_upload(file, 'proofs')
    if not path:
        return jsonify({'success': False, 'message': '文件格式不支持'}), 400

    order.pay_proof = path
    order.status = 'paid'  # 已支付待审核/评级
    db.session.commit()

    return jsonify({'success': True, 'message': '凭证上传成功，等待评级师审核', 'path': path})


@center_bp.route('/api/center/rater/list')
@rater_required
def api_rater_list():
    """评级师拉取订单列表"""
    status = request.args.get('status', 'paid')
    if status == 'all':
        orders = CertOrder.query.order_by(CertOrder.created_at.desc()).all()
    else:
        orders = CertOrder.query.filter_by(status=status).order_by(
            CertOrder.created_at.desc()).all()
    return jsonify({
        'success': True,
        'data': [o.to_dict() for o in orders],
    })


@center_bp.route('/api/center/rater/publish', methods=['POST'])
@rater_required
def api_rater_publish():
    """评级师发布评级结果"""
    data = request.get_json() if request.is_json else request.form
    order_no = data.get('order_no')
    cert_no = data.get('cert_no', '').strip()
    cert_result = data.get('cert_result')  # dict 或 JSON 字符串
    cert_images = data.get('cert_images')

    if not order_no or not cert_no:
        return jsonify({'success': False, 'message': '订单号和证书号必填'}), 400

    order = CertOrder.query.filter_by(order_no=order_no).first()
    if not order:
        return jsonify({'success': False, 'message': '订单不存在'}), 404

    order.cert_no = cert_no
    if cert_result:
        if isinstance(cert_result, dict):
            order.cert_result = json.dumps(cert_result, ensure_ascii=False)
        else:
            order.cert_result = cert_result
    if cert_images:
        if isinstance(cert_images, list):
            order.cert_images = json.dumps(cert_images, ensure_ascii=False)
        else:
            order.cert_images = cert_images
    order.rater_id = current_user.id
    order.status = 'done'
    db.session.commit()

    return jsonify({'success': True, 'message': '评级结果已发布'})


# ============================================================
# 静态资源
# ============================================================

@center_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@center_bp.route('/.well-known/acme-challenge/<token>')
def acme_challenge(token):
    """ACME HTTP-01 验证文件服务"""
    return send_from_directory(ACME_CHALLENGE_DIR, token)


# ============================================================
# 错误处理（Blueprint 级别，作用于整个 app）
# ============================================================

@center_bp.app_errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': '接口不存在'}), 404
    return render_template('404.html'), 404
