import os
import json
import random
import string
import time
from datetime import datetime
from flask import (Blueprint, render_template, request, redirect, url_for,
                   jsonify, send_from_directory, abort, flash, current_app)
from flask_login import login_user, logout_user, current_user

from config import Config
from models import db, User, CertOrder, Department, DepartmentPricing, Coupon, LotteryRecord
from decorators import login_required, rater_required, admin_required

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# ============================================================
# Flask Blueprint：评级中心
# ============================================================
center_bp = Blueprint('center', __name__)

# ACME HTTP-01 验证目录
ACME_CHALLENGE_DIR = os.path.join(BASE_DIR, '.well-known', 'acme-challenge')
os.makedirs(ACME_CHALLENGE_DIR, exist_ok=True)

# 收款码图片目录
PAY_QR_DIR = os.path.join(BASE_DIR, 'static', 'pay')
os.makedirs(PAY_QR_DIR, exist_ok=True)


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


def gen_epid():
    """生成 EPID：EP + 年月日时分秒 + 4位随机"""
    now = datetime.now()
    ts = now.strftime('%Y%m%d%H%M%S')
    rand = ''.join([str(random.randint(0, 9)) for _ in range(4)])
    return f'EP{ts}{rand}'


def gen_efid():
    """生成 EFID：EF + 年月日 + 6位随机字母数字"""
    now = datetime.now()
    ts = now.strftime('%Y%m%d')
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'EF{ts}{rand}'


def gen_euid():
    """生成 EUID：EU + 年月日 + 6位随机字母数字"""
    now = datetime.now()
    ts = now.strftime('%Y%m%d')
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'EU{ts}{rand}'


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


def get_price(department_slug, service_type, box_type, has_guarantee):
    """查询定价"""
    pricing = DepartmentPricing.query.filter_by(
        department_slug=department_slug,
        service_type=service_type,
        box_type=box_type,
        has_guarantee=has_guarantee
    ).first()
    if pricing:
        return pricing.price
    # 默认定价
    base = 50.0
    if box_type == 'JIN':
        base += 30.0
    if has_guarantee:
        base += 20.0
    if service_type == 'offline':
        base += 10.0
    return base


def get_departments():
    """获取所有活跃部门"""
    return Department.query.filter_by(is_active=1).order_by(Department.id).all()


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
    return redirect('https://intro.zhangjiacoins.dpdns.org')


# ============================================================
# 用户认证
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
    departments = get_departments()
    return render_template('center/apply.html', departments=departments)


@center_bp.route('/center/pay/<order_no>')
def center_pay(order_no):
    order = CertOrder.query.filter_by(order_no=order_no).first()
    if not order:
        abort(404)
    dept = Department.query.filter_by(slug=order.department).first()
    pay_qr = None
    if dept and dept.pay_qr:
        pay_qr = dept.pay_qr
    elif order.department:
        pay_qr = f'/static/pay/{order.department}.jpg'
    return render_template('center/pay.html', order=order, pay_qr=pay_qr)


@center_bp.route('/center/query/<keyword>')
def center_query(keyword):
    order = CertOrder.query.filter_by(order_no=keyword).first()
    if not order:
        order = CertOrder.query.filter_by(cert_no=keyword).first()
    if not order:
        order = CertOrder.query.filter_by(contact=keyword).order_by(
            CertOrder.created_at.desc()).first()
    return render_template('center/query.html', order=order, keyword=keyword)


@center_bp.route('/center/rater')
@rater_required
def center_rater():
    dept = Department.query.filter_by(slug=current_user.rater_department).first()
    return render_template('center/rater.html', rater_dept=dept)


# ============================================================
# 评级中心 - API 端点
# ============================================================

# --- 定价查询 ---

@center_bp.route('/api/center/pricing')
def api_pricing():
    """查询某部门某服务类型的价格"""
    dept_slug = request.args.get('department', '')
    service_type = request.args.get('service_type', 'online')
    box_type = request.args.get('box_type', 'PLA')
    has_guarantee = int(request.args.get('has_guarantee', 0))

    price = get_price(dept_slug, service_type, box_type, has_guarantee)
    return jsonify({'success': True, 'price': price})


@center_bp.route('/api/center/departments')
def api_departments():
    """获取所有活跃部门列表"""
    depts = get_departments()
    return jsonify({
        'success': True,
        'data': [{'slug': d.slug, 'name': d.name, 'euid_prefix': d.euid_prefix} for d in depts]
    })


# --- 优惠券 ---

@center_bp.route('/api/center/coupon/verify', methods=['POST'])
def api_coupon_verify():
    """验证优惠券码"""
    data = request.get_json() if request.is_json else request.form
    efid = (data.get('coupon_code') or data.get('efid') or '').strip()
    if not efid:
        return jsonify({'success': False, 'message': '请输入券码'}), 400

    coupon = Coupon.query.filter_by(efid=efid).first()
    if not coupon:
        return jsonify({'success': False, 'message': '券码无效'}), 404
    if coupon.is_used:
        return jsonify({'success': False, 'message': '该券码已被使用'}), 400

    return jsonify({
        'success': True,
        'discount_type': coupon.discount_type,
        'discount_value': coupon.discount_value,
        'message': '券码有效' if coupon.discount_type == 'full' else f'减免 ¥{coupon.discount_value}'
    })


# --- 申请评级 ---

@center_bp.route('/api/center/apply', methods=['POST'])
@login_required
def api_apply():
    """提交评级申请"""
    contact = request.form.get('contact', '').strip()
    coin_name = request.form.get('coin_name', '').strip()
    coin_era = request.form.get('coin_era', '').strip()
    coin_desc = request.form.get('coin_desc', '').strip()
    department = request.form.get('department', '').strip()
    service_type = request.form.get('service_type', 'online').strip()
    box_type = request.form.get('box_type', 'PLA').strip()
    has_guarantee = int(request.form.get('has_guarantee', 0))
    coupon_code = request.form.get('coupon_code', '').strip()

    if not contact or not coin_name:
        return jsonify({'success': False, 'message': '联系方式和币种名称必填'}), 400
    if not department:
        return jsonify({'success': False, 'message': '请选择评级部门'}), 400

    # 计算价格
    base_price = get_price(department, service_type, box_type, has_guarantee)
    final_price = base_price

    # 处理优惠券
    coupon = None
    if coupon_code:
        coupon = Coupon.query.filter_by(efid=coupon_code).first()
        if not coupon:
            return jsonify({'success': False, 'message': '券码无效'}), 400
        if coupon.is_used:
            return jsonify({'success': False, 'message': '该券码已被使用'}), 400
        if coupon.discount_type == 'full':
            final_price = 0.0
        else:
            final_price = max(0.0, base_price - coupon.discount_value)

    # 处理图片上传
    images = []
    for key in request.files:
        file = request.files[key]
        if file and file.filename:
            path = save_upload(file, 'coins')
            if path:
                images.append(path)

    order = CertOrder(
        order_no=gen_epid(),
        user_id=current_user.id,
        contact=contact,
        coin_name=coin_name,
        coin_era=coin_era,
        coin_desc=coin_desc,
        coin_images=json.dumps(images, ensure_ascii=False) if images else None,
        department=department,
        service_type=service_type,
        box_type=box_type,
        has_guarantee=has_guarantee,
        base_price=base_price,
        final_price=final_price,
        coupon_code=coupon_code if coupon else None,
        status='pending',
    )
    db.session.add(order)

    # 标记券码已使用
    if coupon:
        coupon.is_used = 1
        coupon.used_by = current_user.id
        coupon.used_order = order.order_no
        coupon.used_at = datetime.utcnow()

    db.session.commit()

    return jsonify({
        'success': True,
        'message': '申请提交成功',
        'order_no': order.order_no,
        'base_price': base_price,
        'final_price': final_price,
        'redirect': url_for('center.center_pay', order_no=order.order_no),
    })


# --- 查询 ---

@center_bp.route('/api/center/query/<keyword>')
def api_query(keyword):
    """查询：EPID / 证书号 / 手机号"""
    keyword = keyword.strip()
    if not keyword:
        return jsonify({'success': False, 'message': '请输入查询关键词'}), 400

    order = CertOrder.query.filter_by(order_no=keyword).first()
    if not order:
        order = CertOrder.query.filter_by(cert_no=keyword).first()
    if not order:
        order = CertOrder.query.filter_by(contact=keyword).order_by(
            CertOrder.created_at.desc()).first()

    if not order:
        return jsonify({'success': False, 'message': '未找到相关记录'}), 404

    data = order.to_dict()
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

    # 补充部门名称
    if order.department:
        dept = Department.query.filter_by(slug=order.department).first()
        if dept:
            data['department_name'] = dept.name

    return jsonify({'success': True, 'data': data})


# --- 支付凭证上传 ---

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
    order.status = 'paid'
    db.session.commit()

    return jsonify({'success': True, 'message': '凭证上传成功，等待评级师审核', 'path': path})


# --- 评级师接口 ---

@center_bp.route('/api/center/rater/list')
@rater_required
def api_rater_list():
    """评级师拉取本部门订单列表"""
    status = request.args.get('status', 'paid')
    dept_slug = current_user.rater_department

    query = CertOrder.query
    # 管理员可看全部，评级师只看本部门
    if not current_user.is_admin_user and dept_slug:
        query = query.filter_by(department=dept_slug)

    if status != 'all':
        query = query.filter_by(status=status)

    orders = query.order_by(CertOrder.created_at.desc()).all()
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
    cert_result = data.get('cert_result')
    cert_images = data.get('cert_images')
    tracking_no = data.get('tracking_no', '').strip()
    return_address = data.get('return_address', '').strip()

    if not order_no or not cert_no:
        return jsonify({'success': False, 'message': '订单号和证书号必填'}), 400

    order = CertOrder.query.filter_by(order_no=order_no).first()
    if not order:
        return jsonify({'success': False, 'message': '订单不存在'}), 404

    # 评级师只能发布本部门订单（管理员除外）
    if not current_user.is_admin_user and current_user.rater_department and \
       order.department != current_user.rater_department:
        return jsonify({'success': False, 'message': '无权操作其他部门订单'}), 403

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
    if tracking_no:
        order.tracking_no = tracking_no
    if return_address:
        order.return_address = return_address
    order.rater_id = current_user.id
    order.status = 'done'
    db.session.commit()

    return jsonify({'success': True, 'message': '评级结果已发布'})


@center_bp.route('/api/center/rater/grant', methods=['POST'])
@admin_required
def api_rater_grant():
    """管理员授予用户评级师身份 + 部门"""
    data = request.get_json() if request.is_json else request.form
    user_id = data.get('user_id')
    department = data.get('department', '').strip()
    rater_euid = data.get('rater_euid', '').strip()

    if not user_id:
        return jsonify({'success': False, 'message': '请指定用户'}), 400

    user = User.query.get(user_id)
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    user.is_rater = 1
    user.rater_department = department or None
    if rater_euid:
        user.rater_euid = rater_euid
    else:
        user.rater_euid = f'EUID-CE-{user.id:04d}'
    db.session.commit()

    return jsonify({
        'success': True,
        'message': f'已授予 {user.username} 评级师权限',
        'rater_euid': user.rater_euid,
    })


# --- 邮寄信息更新 ---

@center_bp.route('/api/center/rater/tracking', methods=['POST'])
@rater_required
def api_rater_tracking():
    """评级师填写邮寄单号和回寄地址"""
    data = request.get_json() if request.is_json else request.form
    order_no = data.get('order_no')
    tracking_no = data.get('tracking_no', '').strip()
    return_address = data.get('return_address', '').strip()

    order = CertOrder.query.filter_by(order_no=order_no).first()
    if not order:
        return jsonify({'success': False, 'message': '订单不存在'}), 404

    if tracking_no:
        order.tracking_no = tracking_no
    if return_address:
        order.return_address = return_address
    db.session.commit()

    return jsonify({'success': True, 'message': '邮寄信息已更新'})


# ============================================================
# 静态资源
# ============================================================

@center_bp.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)


@center_bp.route('/static/pay/<path:filename>')
def pay_qr_file(filename):
    return send_from_directory(PAY_QR_DIR, filename)


@center_bp.route('/.well-known/acme-challenge/<token>')
def acme_challenge(token):
    """ACME HTTP-01 验证文件服务"""
    return send_from_directory(ACME_CHALLENGE_DIR, token)


@center_bp.route('/download/<filename>')
def download_file(filename):
    """下载项目打包文件"""
    allowed = {'lanos2.5_blueprint.tar.gz', 'lanos2.5_qemu_transfer.tar.gz'}
    if filename not in allowed:
        abort(404)
    return send_from_directory(BASE_DIR, filename, as_attachment=True)


@center_bp.route('/downloads')
def downloads_page():
    return render_template('download.html')


# ============================================================
# 错误处理
# ============================================================

@center_bp.app_errorhandler(404)
def not_found(e):
    if request.path.startswith('/api/'):
        return jsonify({'success': False, 'message': '接口不存在'}), 404
    return render_template('404.html'), 404
