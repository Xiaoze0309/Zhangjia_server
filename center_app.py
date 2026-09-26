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
from db import get_db
from models import User, get_user_by_username, order_to_dict
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
    now = datetime.now()
    ts = now.strftime('%Y%m%d%H%M%S')
    rand = ''.join([str(random.randint(0, 9)) for _ in range(4)])
    return f'EP{ts}{rand}'


def gen_efid():
    now = datetime.now()
    ts = now.strftime('%Y%m%d')
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'EF{ts}{rand}'


def gen_euid():
    now = datetime.now()
    ts = now.strftime('%Y%m%d')
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'EU{ts}{rand}'


def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']


def save_upload(file_storage, subfolder=''):
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


def get_price(db, department_slug, service_type, box_type, has_guarantee):
    row = db.execute(
        "SELECT price FROM department_pricing "
        "WHERE department_slug=? AND service_type=? AND box_type=? AND has_guarantee=?",
        (department_slug, service_type, box_type, has_guarantee)
    ).fetchone()
    if row:
        return row['price']
    base = 50.0
    if box_type == 'JIN':
        base += 30.0
    if has_guarantee:
        base += 20.0
    if service_type == 'offline':
        base += 10.0
    return base


def get_departments(db):
    return db.execute(
        "SELECT * FROM departments WHERE is_active=1 ORDER BY id"
    ).fetchall()


# ============================================================
# 首页分流
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
        db = get_db()
        user = get_user_by_username(db, username)
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
        db = get_db()
        if db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone():
            return jsonify({'success': False, 'message': '用户名已存在'}), 400
        if db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
            return jsonify({'success': False, 'message': '邮箱已注册'}), 400
        from werkzeug.security import generate_password_hash
        cur = db.execute(
            "INSERT INTO users (username, email, password_hash, phone) VALUES (?, ?, ?, ?)",
            (username, email, generate_password_hash(password), phone)
        )
        db.commit()
        user = get_user_by_id_from_db(db, cur.lastrowid)
        login_user(user)
        if request.is_json:
            return jsonify({'success': True, 'message': '注册成功'})
        return redirect(url_for('center.index'))
    return render_template('register.html')


def get_user_by_id_from_db(db, uid):
    row = db.execute("SELECT * FROM users WHERE id=?", (int(uid),)).fetchone()
    return User(row) if row else None


# ============================================================
# 评级中心 - 页面路由
# ============================================================

@center_bp.route('/center')
def center_index():
    return render_template('center/index.html')


@center_bp.route('/center/apply')
def center_apply():
    db = get_db()
    departments = get_departments(db)
    return render_template('center/apply.html', departments=departments)


@center_bp.route('/center/pay/<order_no>')
def center_pay(order_no):
    db = get_db()
    order = db.execute("SELECT * FROM cert_orders WHERE order_no=?", (order_no,)).fetchone()
    if not order:
        abort(404)
    pay_qr = None
    if order['department']:
        dept = db.execute("SELECT pay_qr FROM departments WHERE slug=?", (order['department'],)).fetchone()
        if dept and dept['pay_qr']:
            pay_qr = dept['pay_qr']
        else:
            pay_qr = f'/static/pay/{order["department"]}.jpg'
    return render_template('center/pay.html', order=order, pay_qr=pay_qr)


@center_bp.route('/center/query/<keyword>')
def center_query(keyword):
    db = get_db()
    order = db.execute("SELECT * FROM cert_orders WHERE order_no=?", (keyword,)).fetchone()
    if not order:
        order = db.execute("SELECT * FROM cert_orders WHERE cert_no=?", (keyword,)).fetchone()
    if not order:
        order = db.execute(
            "SELECT * FROM cert_orders WHERE contact=? ORDER BY created_at DESC LIMIT 1",
            (keyword,)
        ).fetchone()
    return render_template('center/query.html', order=order, keyword=keyword)


@center_bp.route('/center/rater')
@rater_required
def center_rater():
    db = get_db()
    dept = None
    if current_user.rater_department:
        dept = db.execute("SELECT * FROM departments WHERE slug=?", (current_user.rater_department,)).fetchone()
    return render_template('center/rater.html', rater_dept=dept)


# ============================================================
# 评级中心 - API 端点
# ============================================================

# --- 定价查询 ---

@center_bp.route('/api/center/pricing')
def api_pricing():
    dept_slug = request.args.get('department', '')
    service_type = request.args.get('service_type', 'online')
    box_type = request.args.get('box_type', 'PLA')
    has_guarantee = int(request.args.get('has_guarantee', 0))
    price = get_price(get_db(), dept_slug, service_type, box_type, has_guarantee)
    return jsonify({'success': True, 'price': price})


@center_bp.route('/api/center/departments')
def api_departments():
    db = get_db()
    rows = get_departments(db)
    return jsonify({
        'success': True,
        'data': [{'slug': r['slug'], 'name': r['name'], 'euid_prefix': r['euid_prefix']} for r in rows]
    })


# --- 优惠券 ---

@center_bp.route('/api/center/coupon/verify', methods=['POST'])
def api_coupon_verify():
    data = request.get_json() if request.is_json else request.form
    efid = (data.get('coupon_code') or data.get('efid') or '').strip()
    if not efid:
        return jsonify({'success': False, 'message': '请输入券码'}), 400
    db = get_db()
    coupon = db.execute("SELECT * FROM coupons WHERE efid=?", (efid,)).fetchone()
    if not coupon:
        return jsonify({'success': False, 'message': '券码无效'}), 404
    if coupon['is_used']:
        return jsonify({'success': False, 'message': '该券码已被使用'}), 400
    return jsonify({
        'success': True,
        'discount_type': coupon['discount_type'],
        'discount_value': coupon['discount_value'],
        'message': '券码有效' if coupon['discount_type'] == 'full' else f'减免 ¥{coupon["discount_value"]}'
    })


# --- 申请评级 ---

@center_bp.route('/api/center/apply', methods=['POST'])
@login_required
def api_apply():
    contact = request.form.get('contact', '').strip()
    coin_name = request.form.get('coin_name', '').strip()
    coin_era = request.form.get('coin_era', '').strip()
    coin_desc = request.form.get('coin_desc', '').strip()
    department = request.form.get('department', '').strip()
    service_type = request.form.get('service_type', 'online').strip()
    box_type = request.form.get('box_type', 'PLA').strip()
    has_guarantee = int(request.form.get('has_guarantee', 0))
    coupon_code = request.form.get('coupon_code', '').strip()
    test_mode = request.form.get('test_mode', '0') == '1'

    if not contact or not coin_name:
        return jsonify({'success': False, 'message': '联系方式和币种名称必填'}), 400
    if not department:
        return jsonify({'success': False, 'message': '请选择评级部门'}), 400

    db = get_db()
    base_price = get_price(db, department, service_type, box_type, has_guarantee)
    final_price = base_price

    coupon = None
    if coupon_code:
        coupon = db.execute("SELECT * FROM coupons WHERE efid=?", (coupon_code,)).fetchone()
        if not coupon:
            return jsonify({'success': False, 'message': '券码无效'}), 400
        if coupon['is_used']:
            return jsonify({'success': False, 'message': '该券码已被使用'}), 400
        if coupon['discount_type'] == 'full':
            final_price = 0.0
        else:
            final_price = max(0.0, base_price - coupon['discount_value'])

    images = []
    for key in request.files:
        file = request.files[key]
        if file and file.filename:
            path = save_upload(file, 'coins')
            if path:
                images.append(path)

    # 测试模式：仅管理员可用，跳过支付
    is_test = 0
    if test_mode and (getattr(current_user, 'admin_level', 0) or 0) >= 1:
        import secrets as _sec
        while True:
            code = ''.join(str(_sec.randbelow(10)) for _ in range(6))
            order_no = f"EPID-TEXT-{code}"
            if not db.execute("SELECT id FROM cert_orders WHERE order_no=?", (order_no,)).fetchone():
                break
        base_price = 0
        final_price = 0
        init_status = 'paid'
        is_test = 1
        print(f"[TEST] 测试单生成：{order_no}")
    else:
        order_no = gen_epid()
        init_status = 'pending'

    db.execute(
        "INSERT INTO cert_orders (order_no, user_id, contact, coin_name, coin_era, coin_desc, "
        "coin_images, department, service_type, box_type, has_guarantee, base_price, final_price, "
        "coupon_code, status, is_test) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (order_no, current_user.id, contact, coin_name, coin_era, coin_desc,
         json.dumps(images, ensure_ascii=False) if images else None,
         department, service_type, box_type, has_guarantee, base_price, final_price,
         coupon_code if coupon else None, init_status, is_test)
    )

    if coupon and not is_test:
        db.execute(
            "UPDATE coupons SET is_used=1, used_by=?, used_order=?, used_at=? WHERE id=?",
            (current_user.id, order_no, datetime.utcnow().isoformat(), coupon['id'])
        )
    db.commit()

    return jsonify({
        'success': True,
        'message': '测试单已提交（已跳过支付）' if is_test else '申请提交成功',
        'order_no': order_no,
        'base_price': base_price,
        'final_price': final_price,
        'is_test': is_test,
        'redirect': url_for('center.center_pay', order_no=order_no),
    })


# --- 查询 ---

@center_bp.route('/api/center/query/<keyword>')
def api_query(keyword):
    keyword = keyword.strip()
    if not keyword:
        return jsonify({'success': False, 'message': '请输入查询关键词'}), 400
    db = get_db()
    order = db.execute("SELECT * FROM cert_orders WHERE order_no=?", (keyword,)).fetchone()
    if not order:
        order = db.execute("SELECT * FROM cert_orders WHERE cert_no=?", (keyword,)).fetchone()
    if not order:
        order = db.execute(
            "SELECT * FROM cert_orders WHERE contact=? ORDER BY created_at DESC LIMIT 1",
            (keyword,)
        ).fetchone()
    if not order:
        return jsonify({'success': False, 'message': '未找到相关记录'}), 404

    data = order_to_dict(order)
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
    if order['department']:
        dept = db.execute("SELECT name FROM departments WHERE slug=?", (order['department'],)).fetchone()
        if dept:
            data['department_name'] = dept['name']
    return jsonify({'success': True, 'data': data})


# --- 支付凭证上传 ---

@center_bp.route('/api/center/upload_proof/<order_no>', methods=['POST'])
@login_required
def api_upload_proof(order_no):
    db = get_db()
    order = db.execute("SELECT * FROM cert_orders WHERE order_no=?", (order_no,)).fetchone()
    if not order:
        return jsonify({'success': False, 'message': '订单不存在'}), 404
    if order['user_id'] != current_user.id and not current_user.is_admin_user:
        return jsonify({'success': False, 'message': '无权操作该订单'}), 403

    file = request.files.get('proof')
    if not file or not file.filename:
        return jsonify({'success': False, 'message': '请上传凭证图片'}), 400
    path = save_upload(file, 'proofs')
    if not path:
        return jsonify({'success': False, 'message': '文件格式不支持'}), 400

    db.execute(
        "UPDATE cert_orders SET pay_proof=?, status='paid', updated_at=? WHERE order_no=?",
        (path, datetime.utcnow().isoformat(), order_no)
    )
    db.commit()
    return jsonify({'success': True, 'message': '凭证上传成功，等待评级师审核', 'path': path})


# --- 评级师接口 ---

@center_bp.route('/api/center/rater/list')
@rater_required
def api_rater_list():
    status = request.args.get('status', 'paid')
    db = get_db()
    sql = "SELECT * FROM cert_orders"
    conds = []
    params = []
    if not current_user.is_admin_user and current_user.rater_department:
        conds.append("department=?")
        params.append(current_user.rater_department)
    if status != 'all':
        conds.append("status=?")
        params.append(status)
    if conds:
        sql += " WHERE " + " AND ".join(conds)
    sql += " ORDER BY created_at DESC"
    rows = db.execute(sql, params).fetchall()
    return jsonify({'success': True, 'data': [order_to_dict(r) for r in rows]})


@center_bp.route('/api/center/rater/publish', methods=['POST'])
@rater_required
def api_rater_publish():
    data = request.get_json() if request.is_json else request.form
    order_no = data.get('order_no')
    cert_no = data.get('cert_no', '').strip()
    cert_result = data.get('cert_result')
    cert_images = data.get('cert_images')
    tracking_no = data.get('tracking_no', '').strip()
    return_address = data.get('return_address', '').strip()

    if not order_no or not cert_no:
        return jsonify({'success': False, 'message': '订单号和证书号必填'}), 400

    db = get_db()
    order = db.execute("SELECT * FROM cert_orders WHERE order_no=?", (order_no,)).fetchone()
    if not order:
        return jsonify({'success': False, 'message': '订单不存在'}), 404
    if not current_user.is_admin_user and current_user.rater_department and \
       order['department'] != current_user.rater_department:
        return jsonify({'success': False, 'message': '无权操作其他部门订单'}), 403

    if cert_result and isinstance(cert_result, dict):
        cert_result = json.dumps(cert_result, ensure_ascii=False)
    if cert_images and isinstance(cert_images, list):
        cert_images = json.dumps(cert_images, ensure_ascii=False)

    db.execute(
        "UPDATE cert_orders SET cert_no=?, cert_result=?, cert_images=?, tracking_no=?, "
        "return_address=?, rater_id=?, status='done', updated_at=? WHERE order_no=?",
        (cert_no, cert_result, cert_images, tracking_no or None,
         return_address or None, current_user.id, datetime.utcnow().isoformat(), order_no)
    )
    db.commit()

    if order['user_id']:
        send_notification(
            user_id=order['user_id'],
            title='评级结果已发布',
            content=f'您的订单 {order_no}（{order["coin_name"]}）评级已完成，证书号：{cert_no}',
            notif_type='order',
            link=url_for('center.center_query', keyword=order_no),
        )
    return jsonify({'success': True, 'message': '评级结果已发布'})


@center_bp.route('/api/center/rater/grant', methods=['POST'])
@admin_required
def api_rater_grant():
    data = request.get_json() if request.is_json else request.form
    user_id = data.get('user_id')
    department = data.get('department', '').strip()
    rater_euid = data.get('rater_euid', '').strip()
    if not user_id:
        return jsonify({'success': False, 'message': '请指定用户'}), 400
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (int(user_id),)).fetchone()
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404
    euid = rater_euid or f'EUID-CE-{int(user_id):04d}'
    db.execute(
        "UPDATE users SET is_rater=1, rater_department=?, rater_euid=? WHERE id=?",
        (department or None, euid, int(user_id))
    )
    db.commit()
    return jsonify({
        'success': True,
        'message': f'已授予 {user["username"]} 评级师权限',
        'rater_euid': euid,
    })


@center_bp.route('/api/center/rater/tracking', methods=['POST'])
@rater_required
def api_rater_tracking():
    data = request.get_json() if request.is_json else request.form
    order_no = data.get('order_no')
    tracking_no = data.get('tracking_no', '').strip()
    return_address = data.get('return_address', '').strip()
    db = get_db()
    order = db.execute("SELECT id FROM cert_orders WHERE order_no=?", (order_no,)).fetchone()
    if not order:
        return jsonify({'success': False, 'message': '订单不存在'}), 404
    if tracking_no:
        db.execute("UPDATE cert_orders SET tracking_no=? WHERE order_no=?", (tracking_no, order_no))
    if return_address:
        db.execute("UPDATE cert_orders SET return_address=? WHERE order_no=?", (return_address, order_no))
    db.commit()
    return jsonify({'success': True, 'message': '邮寄信息已更新'})


# ============================================================
# 个人主页 + 评级记录
# ============================================================

@center_bp.route('/center/profile')
@login_required
def center_profile():
    db = get_db()
    orders = db.execute(
        "SELECT * FROM cert_orders WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
        (current_user.id,)
    ).fetchall()
    notifications = db.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
        (current_user.id,)
    ).fetchall()
    return render_template('center/profile.html', orders=orders, notifications=notifications)


@center_bp.route('/api/center/notifications')
@login_required
def api_notifications():
    db = get_db()
    notifs = db.execute(
        "SELECT * FROM notifications WHERE user_id=? ORDER BY created_at DESC LIMIT 20",
        (current_user.id,)
    ).fetchall()
    unread = db.execute(
        "SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0",
        (current_user.id,)
    ).fetchone()['c']
    return jsonify({
        'success': True,
        'unread_count': unread,
        'data': [dict(n) for n in notifs],
    })


@center_bp.route('/api/center/notifications/<int:nid>/read', methods=['POST'])
@login_required
def api_notification_read(nid):
    db = get_db()
    db.execute(
        "UPDATE notifications SET is_read=1 WHERE id=? AND user_id=?",
        (nid, current_user.id)
    )
    db.commit()
    return jsonify({'success': True})


@center_bp.route('/api/center/notifications/read_all', methods=['POST'])
@login_required
def api_notification_read_all():
    db = get_db()
    db.execute(
        "UPDATE notifications SET is_read=1 WHERE user_id=? AND is_read=0",
        (current_user.id,)
    )
    db.commit()
    return jsonify({'success': True})


def send_notification(user_id, title, content='', notif_type='info', link=None):
    db = get_db()
    db.execute(
        "INSERT INTO notifications (user_id, title, content, type, link) VALUES (?, ?, ?, ?, ?)",
        (user_id, title, content, notif_type, link)
    )
    db.commit()


# ============================================================
# 动态定价管理
# ============================================================

@center_bp.route('/api/center/pricing/list')
@rater_required
def api_pricing_list():
    db = get_db()
    dept_slug = current_user.rater_department
    if current_user.is_admin_user:
        dept_slug = request.args.get('department', dept_slug or '')
    sql = "SELECT * FROM department_pricing"
    params = []
    if dept_slug:
        sql += " WHERE department_slug=?"
        params.append(dept_slug)
    sql += " ORDER BY service_type, box_type, has_guarantee"
    rows = db.execute(sql, params).fetchall()
    return jsonify({
        'success': True,
        'department': dept_slug,
        'data': [dict(r) for r in rows],
    })


@center_bp.route('/api/center/pricing/update', methods=['POST'])
@rater_required
def api_pricing_update():
    data = request.get_json() if request.is_json else request.form
    pricing_id = data.get('id')
    dept_slug = current_user.rater_department
    if current_user.is_admin_user:
        dept_slug = data.get('department', dept_slug)
    service_type = data.get('service_type', 'online')
    box_type = data.get('box_type', 'PLA')
    has_guarantee = int(data.get('has_guarantee', 0))
    price = float(data.get('price', 0))
    if not dept_slug:
        return jsonify({'success': False, 'message': '请先分配评级部门'}), 400

    db = get_db()
    if pricing_id:
        db.execute("UPDATE department_pricing SET price=? WHERE id=?", (price, pricing_id))
    else:
        existing = db.execute(
            "SELECT id FROM department_pricing WHERE department_slug=? AND service_type=? AND box_type=? AND has_guarantee=?",
            (dept_slug, service_type, box_type, has_guarantee)
        ).fetchone()
        if existing:
            db.execute("UPDATE department_pricing SET price=? WHERE id=?", (price, existing['id']))
        else:
            db.execute(
                "INSERT INTO department_pricing (department_slug, service_type, box_type, has_guarantee, price) "
                "VALUES (?, ?, ?, ?, ?)",
                (dept_slug, service_type, box_type, has_guarantee, price)
            )
    db.commit()
    return jsonify({'success': True, 'message': '定价已更新'})


@center_bp.route('/api/center/pricing/daily', methods=['POST'])
@rater_required
def api_pricing_daily():
    data = request.get_json() if request.is_json else request.form
    count = int(data.get('count', 5))
    discount_type = data.get('discount_type', 'fixed')
    discount_value = float(data.get('discount_value', 10))
    db = get_db()
    created = []
    for _ in range(count):
        efid = gen_efid()
        while db.execute("SELECT id FROM coupons WHERE efid=?", (efid,)).fetchone():
            efid = gen_efid()
        db.execute(
            "INSERT INTO coupons (efid, discount_type, discount_value, is_used) VALUES (?, ?, ?, 0)",
            (efid, discount_type, discount_value)
        )
        created.append(efid)
    db.commit()
    return jsonify({
        'success': True,
        'message': f'已生成 {count} 张每日优惠券',
        'coupons': created,
    })


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
    return send_from_directory(ACME_CHALLENGE_DIR, token)


@center_bp.route('/download/<filename>')
def download_file(filename):
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
