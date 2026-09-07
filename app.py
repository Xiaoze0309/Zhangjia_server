from flask import Flask, request, jsonify, render_template, send_from_directory, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import datetime
import re
import json
import hashlib
import base64
import io
import requests
import random
import secrets
from werkzeug.utils import secure_filename
from PIL import Image
from functools import wraps

app = Flask(__name__)
app.secret_key = 'zhangjia-2026-fixed-secret-key'
app.config['REMEMBER_COOKIE_DURATION'] = datetime.timedelta(days=30)
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=30)
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# ========== 罗马数字映射 ==========
ROMAN_MAP = {
    0: '', 1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V',
    6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X',
    11: 'XI', 12: 'XII', 13: 'XIII', 14: 'XIV', 15: 'XV',
    16: 'XVI', 17: 'XVII', 18: 'XVIII'
}

def encrypt_random(raw: str) -> str:
    num = int(raw)
    bin_str = bin(num)[2:]
    while len(bin_str) % 4 != 0:
        bin_str = '0' + bin_str
    hex_str = ''
    for i in range(0, len(bin_str), 4):
        hex_str += hex(int(bin_str[i:i+4], 2))[2:].upper()
    encrypted = int(hex_str, 16)
    enc_str = str(encrypted)
    if len(enc_str) > 9:
        enc_str = enc_str[-9:]
    else:
        enc_str = enc_str.zfill(9)
    return enc_str

def generate_display_id():
    date_str = datetime.datetime.now().strftime("%y%m%d")
    while True:
        raw = str(random.randint(100000000, 999999999))
        if raw[0] != '0':
            break
    enc_num = encrypt_random(raw)
    last_two_sum = int(enc_num[-2]) + int(enc_num[-1])
    roman = ROMAN_MAP.get(last_two_sum, '')
    return f"{date_str}-{enc_num}{roman}"

class User(UserMixin):
    def __init__(self, row):
        row = dict(row)
        self.id = row['id']
        self.username = row['username']
        self.password_hash = row['password_hash']
        self.email = row['email']
        self.exp = row.get('exp', 0)
        self.is_admin = row.get('is_admin', 0)
        self.admin_level = row.get('admin_level', 0)
        self.credit_score = row.get('credit_score', 120)
        self.bio = row.get('bio', '这个人很懒，什么都没写。')
        self.avatar = row.get('avatar', None)
        self.is_realname = row.get('is_realname', 0)
        self.real_name = row.get('real_name', '')
        self.id_number_hash = row.get('id_number_hash', '')
        self.age_group = row.get('age_group', None)
        self.phone = row.get('phone', None)
        self.phone_verified = row.get('phone_verified', 0)
        self.display_id = row.get('display_id', '')
        earned = row.get('earned_achievements')
        self.earned_achievements = json.loads(earned) if earned else []
        self.login_days = row.get('login_days', 0)
        self.bans_issued = row.get('bans_issued', 0)
        self.valid_reports = row.get('valid_reports', 0)
        self.is_boss = row.get('is_boss', 0)
        self.is_webmaster = row.get('is_webmaster', 0)
        self.is_alpha = row.get('is_alpha', 0)
        self.is_beta = row.get('is_beta', 0)
        self.location = row.get('location', '未知地区')
        self.mute_until = row.get('mute_until', None)
        self.post_ban_until = row.get('post_ban_until', None)
        self.comment_ban_until = row.get('comment_ban_until', None)
        self.dm_ban_until = row.get('dm_ban_until', None)
        self.admin_ban_until = row.get('admin_ban_until', None)
        self.ban_until = row.get('ban_until', None)
        self.is_owner = row.get('is_owner', 0)
        # 新增冻结字段
        self.freeze_level = row.get('freeze_level', None)
        self.freeze_until = row.get('freeze_until', None)
        self.freeze_mark = row.get('freeze_mark', None)
        su_timestamps_raw = row.get('su_timestamps')
        self.su_timestamps = json.loads(su_timestamps_raw) if su_timestamps_raw else []
        self.last_device_handshake = row.get('last_device_handshake', None)

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        return User(row)
    return None

def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        for col in ['avatar', 'bio', 'phone', 'phone_verified', 'credit_score', 'growth_level', 'is_realname', 'age_group', 'is_alpha', 'is_beta', 'is_boss', 'is_webmaster', 'admin_level', 'earned_achievements', 'login_days', 'last_login_date', 'bans_issued', 'valid_reports', 'location', 'mute_until', 'post_ban_until', 'comment_ban_until', 'dm_ban_until', 'admin_ban_until', 'ban_until', 'real_name', 'id_number_hash', 'display_id', 'is_owner', 'freeze_level', 'freeze_until', 'freeze_mark', 'su_timestamps', 'last_device_handshake']:
            try: conn.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except: pass
        conn.execute('''CREATE TABLE IF NOT EXISTS achievements (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT NOT NULL, type TEXT NOT NULL, icon TEXT, points INTEGER DEFAULT 10)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS titles (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS achievement_titles (achievement_id INTEGER NOT NULL, title_id INTEGER NOT NULL, FOREIGN KEY(achievement_id) REFERENCES achievements(id), FOREIGN KEY(title_id) REFERENCES titles(id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS user_achievements (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, achievement_id INTEGER NOT NULL, unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, achievement_id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS user_titles (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title_id INTEGER NOT NULL, unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, title_id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS user_displayed_titles (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, title_id INTEGER NOT NULL, display_order INTEGER NOT NULL, UNIQUE(user_id, title_id), UNIQUE(user_id, display_order))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, reporter_id INTEGER NOT NULL, target_type TEXT NOT NULL, target_id INTEGER NOT NULL, reason TEXT NOT NULL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS appeals (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, reason TEXT NOT NULL, evidence TEXT, status TEXT DEFAULT 'pending', reviewed_by INTEGER, reviewer_comment TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS ban_votes (id INTEGER PRIMARY KEY AUTOINCREMENT, target_user_id INTEGER NOT NULL, initiator_id INTEGER NOT NULL, reason TEXT NOT NULL, vote_end_at TIMESTAMP NOT NULL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS ban_vote_records (id INTEGER PRIMARY KEY AUTOINCREMENT, vote_id INTEGER NOT NULL, voter_id INTEGER NOT NULL, choice TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(vote_id) REFERENCES ban_votes(id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id INTEGER NOT NULL, receiver_id INTEGER NOT NULL, content TEXT NOT NULL, is_read INTEGER DEFAULT 0, read_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (sender_id) REFERENCES users(id), FOREIGN KEY (receiver_id) REFERENCES users(id))''')
        try: conn.execute("ALTER TABLE messages ADD COLUMN is_system INTEGER DEFAULT 0")
        except: pass
        try: conn.execute("ALTER TABLE posts ADD COLUMN grade_code TEXT")
        except: pass
        try: conn.execute("ALTER TABLE posts ADD COLUMN status TEXT DEFAULT 'pending'")
        except: pass
        try: conn.execute("ALTER TABLE posts ADD COLUMN reject_reason TEXT")
        except: pass
        try: conn.execute("ALTER TABLE posts ADD COLUMN post_type TEXT DEFAULT 'grade'")
        except: pass
        try: conn.execute("ALTER TABLE posts ADD COLUMN report_code TEXT")
        except: pass
        conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_grade_code ON posts(grade_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_status ON posts(status)")

        if not conn.execute("SELECT id FROM achievements LIMIT 1").fetchone():
            for a in [('表里如一','信誉分达到300','credit','🏆',10), ('信守不渝','信誉分达到400','credit','🏆',20), ('言必行行必果','信誉分达到500','credit','🏆',30), ('开诚布公','信誉分达到600','credit','🏆',50), ('Alpha测试参与者','V1.0-1.9注册','identity','🔰',10), ('Beta测试参与者','V2.0-3.9注册','identity','🔰',10), ('站长','认证站长','identity','👑',30), ('老大！！！','认证老大','identity','👑',30), ('高级管理员','认证高级管理员','identity','⚜️',20), ('管理员','认证管理员','identity','🔱',10), ('包拯','封禁20个无误封','action','⚖️',10), ('遵法守法','有效举报20次','action','🛡️',10), ('每日达','累计登录60天','login','📅',20), ('日复一日，年复一年','累计登录365天','login','📅',50)]:
                conn.execute("INSERT INTO achievements (name, description, type, icon, points) VALUES (?,?,?,?,?)", a)
        if not conn.execute("SELECT id FROM titles LIMIT 1").fetchone():
            for t in [('表里如一','信誉分达到300','通用'), ('信守不渝','信誉分达到400','稀有'), ('言必行','信誉分达到500','史诗'), ('开诚布公','信誉分达到600','传说'), ('Alpha先锋','Alpha测试参与者','稀有'), ('Beta开拓者','Beta测试参与者','稀有'), ('樟嘉站长','认证站长','传说'), ('樟嘉元老','认证老大','传说'), ('高级管理员','认证高级管理员','史诗'), ('管理员','认证管理员','稀有'), ('包拯','封禁20个无误封','史诗'), ('遵法守法','有效举报20次','稀有'), ('每日达','累计登录60天','通用'), ('日复一日','累计登录365天','史诗')]:
                conn.execute("INSERT INTO titles (name, description, category) VALUES (?,?,?)", t)
            for i in range(1,15): conn.execute("INSERT INTO achievement_titles (achievement_id, title_id) VALUES (?,?)", (i,i))
        conn.execute("UPDATE posts SET status = 'approved' WHERE status IS NULL")

        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('app_version', 'V2.8.30s')")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                admin_name TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT,
                target_id INTEGER,
                detail TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parliament_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vote_id TEXT NOT NULL UNIQUE,
                initiated_by INTEGER,
                trigger_reason TEXT NOT NULL,
                triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'active',
                result TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS parliament_vote_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vote_id TEXT NOT NULL,
                voter_id INTEGER NOT NULL,
                choice TEXT NOT NULL,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(vote_id, voter_id)
            )
        """)
        conn.commit()
init_db()

def hash_password(pwd): return generate_password_hash(pwd)
def check_password(pwd, hashed): return check_password_hash(hashed, pwd)
def is_valid_email(email): return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) is not None

def get_credit_level(score):
    if score is None: score = 0
    if score >= 250: return 'G5 · 信誉大师'
    if score >= 200: return 'G4 · 信誉典范'
    if score >= 180: return 'G3 · 信誉卓越'
    if score >= 160: return 'G2 · 诚信可靠'
    if score >= 140: return 'G1 · 值得信赖'
    if score >= 120: return 'G0 · 信誉良好'
    if score >= 100: return 'B1 · 信誉偏低'
    if score >= 80: return 'B2 · 信誉较低'
    if score >= 70: return 'B3 · 信誉低'
    if score >= 60: return 'B4 · 信誉极低'
    if score >= 50: return 'B5 · 信誉危险'
    if score >= 40: return 'B6 · 信誉严重危险'
    if score >= 30: return 'B7 · 信誉极危'
    if score >= 20: return 'B8 · 信誉濒危'
    return 'B9 · 信誉归零'

def get_growth_level(exp): return max(1, exp // 50 + 1)

def get_ip_location(ip):
    if ip.startswith('127.') or ip.startswith('192.168.') or ip == '::1': return '本地'
    try:
        r = requests.get(f'http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,regionName,city', timeout=2)
        data = r.json()
        if data.get('status') == 'success': return f"{data.get('regionName','')}·{data.get('city','')}"
    except: pass
    return '未知地区'

# ========== 设备握手中间件 ==========
def device_handshake_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': '未登录'}), 401

        if current_user.admin_level >= 2:
            max_interval = 3
        elif current_user.admin_level == 1:
            max_interval = 6
        else:
            return f(*args, **kwargs)

        last = current_user.last_device_handshake
        if last:
            try:
                last_time = datetime.datetime.fromisoformat(last)
                if (datetime.datetime.now() - last_time) > datetime.timedelta(hours=max_interval):
                    return jsonify({
                        'error': 'DEVICE_HANDSHAKE_EXPIRED',
                        'message': f'设备验证已过期（>{max_interval}h），请重新握手',
                        'interval_hours': max_interval
                    }), 403
            except:
                return jsonify({'error': '设备验证异常'}), 403
        else:
            return jsonify({
                'error': 'DEVICE_HANDSHAKE_REQUIRED',
                'message': '首次使用请完成设备绑定握手'
            }), 403

        return f(*args, **kwargs)
    return decorated

@app.route('/api/device/handshake', methods=['POST'])
@login_required
def device_handshake():
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET last_device_handshake = ? WHERE id = ?",
            (datetime.datetime.now().isoformat(), current_user.id)
        )
    return jsonify({'status': 'ok', 'message': f'握手成功，下次验证时间：{datetime.datetime.now() + datetime.timedelta(hours=3)}'})

# ========== 路由 ==========
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/a2aae0b59de7ff1597da24521d9f3b7f.txt')
def wechat_verify():
    return send_from_directory('.', 'a2aae0b59de7ff1597da24521d9f3b7f.txt')

@app.route('/.well-known/acme-challenge/<path:filename>')
def acme_challenge(filename):
    return send_from_directory('.well-known/acme-challenge', filename)

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/privacy-realname')
def privacy_realname():
    return render_template('privacy-realname.html')

@app.route('/privacy-ip')
def privacy_ip():
    return render_template('privacy-ip.html')

@app.route('/privacy-dm')
def privacy_dm():
    return render_template('privacy-dm.html')

@app.route('/privacy-phone')
def privacy_phone():
    return render_template('privacy-phone.html')

@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username','').strip()
    password = data.get('password','').strip()
    email = data.get('email','').strip()
    if not username or not password: return jsonify({'error':'用户名和密码不能为空'}),400
    if len(username)<3: return jsonify({'error':'用户名至少3个字符'}),400
    if len(password)<4: return jsonify({'error':'密码至少4个字符'}),400
    if email and not is_valid_email(email): return jsonify({'error':'邮箱格式不正确'}),400
    try:
        with get_db() as conn:
            cursor = conn.execute("INSERT INTO users (username, password_hash, email) VALUES (?,?,?)", (username, hash_password(password), email if email else None))
            new_id = cursor.lastrowid
            display_id = generate_display_id()
            while True:
                existing = conn.execute("SELECT id FROM users WHERE display_id = ?", (display_id,)).fetchone()
                if not existing:
                    break
                display_id = generate_display_id()
            conn.execute("UPDATE users SET display_id = ? WHERE id = ?", (display_id, new_id))
        return jsonify({'status':'ok','message':'注册成功'}),201
    except sqlite3.IntegrityError:
        return jsonify({'error':'用户名已存在'}),400

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username','').strip()
    password = data.get('password','').strip()
    if not username or not password: return jsonify({'error':'请输入用户名和密码'}),400
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row or not check_password(password, row['password_hash']): return jsonify({'error':'用户名或密码错误'}),401
        session.pop('_su_original_user_id', None)
        user = User(row)
        login_user(user, remember=True, duration=datetime.timedelta(days=30))
        today = datetime.date.today().isoformat()
        if row['last_login_date'] != today:
            conn.execute("UPDATE users SET login_days = login_days + 1, last_login_date = ? WHERE id = ?", (today, user.id))
        ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        loc = get_ip_location(ip)
        if loc not in ['本地','未知地区']:
            conn.execute("UPDATE users SET location = ? WHERE id = ?", (loc, user.id))
        return jsonify({'status':'ok','user':{
            'id':row['id'],'username':row['username'],'email':row['email'],
            'exp':row['exp'],'credit_score':row['credit_score'],
            'is_admin':row['is_admin'],'admin_level':row['admin_level'],
            'display_id':row['display_id']
        }})

@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    original_id = session.get('_su_original_user_id')
    if original_id:
        session.pop('_su_original_user_id', None)
        with get_db() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (original_id,)).fetchone()
            if row:
                original_user = User(row)
                login_user(original_user, remember=True, duration=datetime.timedelta(days=30))
                return jsonify({'status': 'ok', 'message': '已退出模拟登录'})
    logout_user()
    return jsonify({'status':'ok'})

@app.route('/api/me')
def me():
    if current_user.is_authenticated:
        is_su = session.get('_su_original_user_id') is not None
        return jsonify({
            'id':current_user.id,
            'username':current_user.username,
            'email':current_user.email,
            'exp':current_user.exp,
            'credit_score':current_user.credit_score,
            'is_admin':current_user.is_admin,
            'admin_level':current_user.admin_level,
            'bio':current_user.bio,
            'avatar':current_user.avatar,
            'is_realname':current_user.is_realname,
            'age_group':current_user.age_group,
            'phone':current_user.phone,
            'phone_verified':current_user.phone_verified,
            'display_id':current_user.display_id,
            'earned_achievements':current_user.earned_achievements,
            'login_days':current_user.login_days,
            'location':current_user.location,
            'is_webmaster':current_user.is_webmaster,
            'is_boss':current_user.is_boss,
            'is_alpha':current_user.is_alpha,
            'is_beta':current_user.is_beta,
            'is_owner':current_user.is_owner,
            'is_su_mode': is_su
        })
    return jsonify({'error':'未登录'}),401

@app.route('/api/user/<int:user_id>')
def get_user_profile(user_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row: return jsonify({'error':'用户不存在'}),404
        user = dict(row)
        user['credit_level'] = get_credit_level(user['credit_score'])
        user['growth_level'] = get_growth_level(user['exp'])
        user['post_count'] = conn.execute("SELECT COUNT(*) FROM posts WHERE user_id = ?", (user_id,)).fetchone()[0]
        user['like_count'] = conn.execute("SELECT COUNT(*) FROM likes WHERE user_id = ?", (user_id,)).fetchone()[0]
        titles = conn.execute("SELECT t.name FROM user_displayed_titles dt JOIN titles t ON dt.title_id = t.id WHERE dt.user_id = ? ORDER BY dt.display_order", (user_id,)).fetchall()
        user['display_titles'] = [t['name'] for t in titles]
        credit = user.get('credit_score') or 0
        user['is_gold'] = credit >= 200 or user.get('is_webmaster',0) or user.get('is_boss',0) or user.get('is_alpha',0) or user.get('is_beta',0)
        user['is_blocked'] = False
        # 显示冻结标记
        if user.get('freeze_mark'):
            user['freeze_mark'] = user['freeze_mark']
    return jsonify(user)

@app.route('/api/user/display/<display_id>')
def get_user_by_display_id(display_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE display_id = ?", (display_id,)).fetchone()
        if not row: return jsonify({'error':'用户不存在'}),404
        return jsonify({'id': row['id'], 'username': row['username'], 'display_id': row['display_id']})

@app.route('/api/posts')
def get_posts():
    search = request.args.get('search','').strip()
    tag = request.args.get('tag','').strip()
    user_id = request.args.get('user_id','')
    sql = """SELECT posts.*, users.username, users.credit_score, users.is_webmaster, users.is_boss, users.is_alpha, users.is_beta, users.avatar, users.display_id
             FROM posts LEFT JOIN users ON posts.user_id = users.id WHERE 1=1"""
    params = []
    if not current_user.is_authenticated or current_user.admin_level < 1:
        sql += " AND posts.status = 'approved'"
    if search:
        sql += " AND (posts.title LIKE ? OR posts.content LIKE ? OR posts.tag LIKE ? OR posts.grade_code = ?)"
        like = '%'+search+'%'
        params.extend([like, like, like, search])
    if tag:
        sql += " AND posts.tag LIKE ?"
        params.append('%'+tag+'%')
    if user_id and user_id.isdigit():
        sql += " AND posts.user_id = ?"
        params.append(int(user_id))
    sql += " ORDER BY posts.id DESC"
    with get_db() as conn:
        cursor = conn.execute(sql, params)
        posts = [dict(row) for row in cursor.fetchall()]
        for p in posts:
            p['like_count'] = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", (p['id'],)).fetchone()[0]
            p['comment_count'] = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", (p['id'],)).fetchone()[0]
            if current_user.is_authenticated:
                liked = conn.execute("SELECT id FROM likes WHERE post_id = ? AND user_id = ?", (p['id'], current_user.id)).fetchone()
                p['liked'] = 1 if liked else 0
            else:
                p['liked'] = 0
            credit = p.get('credit_score') or 0
            p['is_gold'] = credit >= 200 or p.get('is_webmaster',0) or p.get('is_boss',0) or p.get('is_alpha',0) or p.get('is_beta',0)
    return jsonify(posts)

@app.route('/api/posts', methods=['POST'])
@login_required
def add_post():
    if current_user.admin_level < 1: return jsonify({'error':'只有管理员可以发帖'}),403
    if current_user.post_ban_until:
        try:
            if datetime.datetime.now() < datetime.datetime.strptime(current_user.post_ban_until, '%Y-%m-%d %H:%M:%S'):
                return jsonify({'error':'您当前被禁帖'}),403
        except: pass
    title = request.form.get('title','').strip()
    content = request.form.get('content','').strip()
    tag = request.form.get('tag','').strip()
    post_type = request.form.get('type', 'grade')
    grade_code = request.form.get('grade_code', '').strip()

    if not title: return jsonify({'error':'标题不能为空'}),400
    if not tag: return jsonify({'error':'请选择分类'}),400
    sensitive = ['涉黄','涉黑','违法']
    for w in sensitive:
        if w in title or w in content: return jsonify({'error':'内容包含敏感词'}),400

    if grade_code:
        if post_type == 'grade':
            if not re.match(r'^\d{8,12}$', grade_code):
                return jsonify({'error':'评级码需为8-12位纯数字'}),400
        else:
            if not re.match(r'^\d{6}-\d{5}-\d{8}$', grade_code):
                return jsonify({'error':'综合报格式：部门代码-第几报-日期'}),400

    with get_db() as conn:
        recent = conn.execute("SELECT id FROM posts WHERE user_id=? AND title=? AND created_at > datetime('now','-5 seconds')", (current_user.id, title)).fetchone()
        if recent: return jsonify({'error':'请勿重复提交'}),429

    files = request.files.getlist('images')
    saved = []
    for f in files:
        if f and f.filename and '.' in f.filename and f.filename.rsplit('.',1)[1].lower() in ALLOWED_EXTENSIONS:
            ext = f.filename.rsplit('.',1)[1].lower()
            name = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(f.filename)}"
            img = Image.open(f.stream)
            if img.mode in ('RGBA','LA'): img = img.convert('RGB')
            img.thumbnail((800,800))
            buf = io.BytesIO()
            img.save(buf, format='JPEG', quality=75, optimize=True)
            buf.seek(0)
            with open(os.path.join(app.config['UPLOAD_FOLDER'], name), 'wb') as out: out.write(buf.read())
            saved.append(name)

    with get_db() as conn:
        conn.execute("""
            INSERT INTO posts (user_id, title, content, images, tag, grade_code, status, post_type)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (current_user.id, title, content, ','.join(saved) if saved else None, tag, grade_code if grade_code else None, post_type))
        conn.execute("UPDATE users SET exp = exp + 3 WHERE id = ?", (current_user.id,))
    return jsonify({'status':'ok'}),201

@app.route('/api/posts/<int:post_id>')
def get_post(post_id):
    with get_db() as conn:
        post = conn.execute("SELECT posts.*, users.username, users.credit_score, users.is_webmaster, users.is_boss, users.is_alpha, users.is_beta, users.avatar, users.display_id FROM posts LEFT JOIN users ON posts.user_id = users.id WHERE posts.id = ?", (post_id,)).fetchone()
        if not post: return jsonify({'error':'帖子不存在'}),404
        if post['status'] != 'approved' and (not current_user.is_authenticated or current_user.admin_level < 1):
            return jsonify({'error':'该帖子未通过审核'}),403
        p = dict(post)
        p['like_count'] = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", (post_id,)).fetchone()[0]
        p['comment_count'] = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", (post_id,)).fetchone()[0]
        if current_user.is_authenticated:
            liked = conn.execute("SELECT id FROM likes WHERE post_id = ? AND user_id = ?", (post_id, current_user.id)).fetchone()
            p['liked'] = 1 if liked else 0
        else: p['liked'] = 0
        comments = conn.execute("SELECT comments.*, users.username, users.credit_score, users.is_webmaster, users.is_boss, users.is_alpha, users.is_beta, users.avatar, users.display_id FROM comments LEFT JOIN users ON comments.user_id = users.id WHERE post_id = ? ORDER BY comments.id ASC", (post_id,)).fetchall()
        p['comments'] = []
        for c in comments:
            d = dict(c)
            d['is_gold'] = d.get('credit_score',0) >= 200 or d.get('is_webmaster') or d.get('is_boss') or d.get('is_alpha') or d.get('is_beta')
            p['comments'].append(d)
        p['is_gold'] = p.get('credit_score',0) >= 200 or p.get('is_webmaster') or p.get('is_boss') or p.get('is_alpha') or p.get('is_beta')
    return jsonify(p)

@app.route('/api/posts/<int:post_id>/like', methods=['POST'])
@login_required
def toggle_like(post_id):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM likes WHERE post_id = ? AND user_id = ?", (post_id, current_user.id)).fetchone()
        if existing:
            conn.execute("DELETE FROM likes WHERE id = ?", (existing['id'],))
            return jsonify({'status':'unliked'})
        else:
            conn.execute("INSERT INTO likes (post_id, user_id) VALUES (?,?)", (post_id, current_user.id))
            author = conn.execute("SELECT user_id FROM posts WHERE id = ?", (post_id,)).fetchone()
            if author: conn.execute("UPDATE users SET credit_score = credit_score + 2 WHERE id = ?", (author['user_id'],))
            return jsonify({'status':'liked'})

@app.route('/api/posts/<int:post_id>/comments', methods=['POST'])
@login_required
def add_comment(post_id):
    with get_db() as conn:
        post = conn.execute("SELECT status FROM posts WHERE id = ?", (post_id,)).fetchone()
        if post and post['status'] != 'approved':
            return jsonify({'error':'该帖子未通过审核，暂不可评论'}),403

    if current_user.comment_ban_until:
        try:
            if datetime.datetime.now() < datetime.datetime.strptime(current_user.comment_ban_until, '%Y-%m-%d %H:%M:%S'):
                return jsonify({'error':'您当前被禁评'}),403
        except: pass
    data = request.get_json()
    content = data.get('content','').strip()
    if not content: return jsonify({'error':'评论不能为空'}),400
    sensitive = ['涉黄','涉黑','违法']
    for w in sensitive:
        if w in content: return jsonify({'error':'评论包含敏感词'}),400
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO comments (post_id, user_id, content) VALUES (?,?,?)", (post_id, current_user.id, content))
        conn.execute("UPDATE users SET exp = exp + 1 WHERE id = ?", (current_user.id,))
        new_id = cursor.lastrowid
        row = conn.execute("SELECT comments.*, users.username, users.credit_score, users.is_webmaster, users.is_boss, users.is_alpha, users.is_beta, users.avatar, users.display_id FROM comments LEFT JOIN users ON comments.user_id = users.id WHERE comments.id = ?", (new_id,)).fetchone()
        d = dict(row)
        d['is_gold'] = d.get('credit_score',0) >= 200 or d.get('is_webmaster') or d.get('is_boss') or d.get('is_alpha') or d.get('is_beta')
    return jsonify(d),201

@app.route('/api/admin/delete_post', methods=['POST'])
@login_required
def admin_delete_post():
    if current_user.admin_level < 1: return jsonify({'error':'权限不足'}),403
    data = request.get_json()
    post_id = data.get('post_id')
    if not post_id: return jsonify({'error':'缺少帖子ID'}),400
    with get_db() as conn:
        conn.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM likes WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    return jsonify({'status':'ok'})

@app.route('/api/admin/delete_comment', methods=['POST'])
@login_required
def admin_delete_comment():
    if current_user.admin_level < 1: return jsonify({'error':'权限不足'}),403
    data = request.get_json()
    comment_id = data.get('comment_id')
    if not comment_id: return jsonify({'error':'缺少评论ID'}),400
    with get_db() as conn:
        conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    return jsonify({'status':'ok'})

@app.route('/api/user/avatar', methods=['POST'])
@login_required
def upload_avatar():
    file = request.files.get('avatar')
    if not file:
        return jsonify({'error': '未选择图片'}), 400
    if file.filename.rsplit('.', 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return jsonify({'error': '不支持的图片格式'}), 400
    try:
        img = Image.open(file.stream)
        if img.mode in ('RGBA', 'LA'):
            img = img.convert('RGB')
        img.thumbnail((200, 200))
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=80, optimize=True)
        buf.seek(0)
        avatar_data = base64.b64encode(buf.read()).decode('utf-8')
        avatar_url = f"data:image/jpeg;base64,{avatar_data}"
        with get_db() as conn:
            conn.execute("UPDATE users SET avatar = ? WHERE id = ?", (avatar_url, current_user.id))
        return jsonify({'status': 'ok', 'avatar': avatar_url})
    except Exception as e:
        return jsonify({'error': f'图片处理失败: {str(e)}'}), 500

@app.route('/api/user/location', methods=['POST'])
@login_required
def update_location():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    loc = get_ip_location(ip)
    with get_db() as conn:
        conn.execute("UPDATE users SET location = ? WHERE id = ?", (loc, current_user.id))
    return jsonify({'status': 'ok', 'location': loc})

@app.route('/api/user/bio', methods=['POST'])
@login_required
def update_bio():
    data = request.get_json()
    bio = data.get('bio', '').strip()
    with get_db() as conn:
        conn.execute("UPDATE users SET bio = ? WHERE id = ?", (bio or '这个人很懒，什么都没写。', current_user.id))
    return jsonify({'status': 'ok'})

@app.route('/api/user/email', methods=['POST'])
@login_required
def bind_email():
    data = request.get_json()
    email = data.get('email', '').strip()
    if not is_valid_email(email):
        return jsonify({'error': '邮箱格式不正确'}), 400
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ? AND id != ?", (email, current_user.id)).fetchone()
        if existing:
            return jsonify({'error': '该邮箱已被绑定'}), 400
        conn.execute("UPDATE users SET email = ? WHERE id = ?", (email, current_user.id))
    return jsonify({'status': 'ok', 'message': '邮箱绑定成功'})

@app.route('/api/user/phone', methods=['POST'])
@login_required
def bind_phone():
    data = request.get_json()
    phone = data.get('phone', '').strip()
    if not re.match(r'^1[3-9]\d{9}$', phone):
        return jsonify({'error': '手机号格式不正确'}), 400
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE phone = ? AND id != ?", (phone, current_user.id)).fetchone()
        if existing:
            return jsonify({'error': '该手机号已被绑定'}), 400
        conn.execute("UPDATE users SET phone = ?, phone_verified = 1 WHERE id = ?", (phone, current_user.id))
    return jsonify({'status': 'ok', 'message': '手机号绑定成功'})

@app.route('/api/user/realname', methods=['POST'])
@login_required
def bind_realname():
    data = request.get_json()
    real_name = data.get('real_name', '').strip()
    id_number = data.get('id_number', '').strip()
    if not real_name or not id_number:
        return jsonify({'error': '姓名和身份证号不能为空'}), 400
    if not re.match(r'^[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]$', id_number):
        return jsonify({'error': '身份证号格式不正确'}), 400
    birth_year = int(id_number[6:10])
    birth_month = int(id_number[10:12])
    birth_day = int(id_number[12:14])
    today = datetime.date.today()
    age = today.year - birth_year
    if (today.month, today.day) < (birth_month, birth_day):
        age -= 1
    age_group = 'adult' if age >= 18 else 'minor'
    id_hash = hashlib.sha256(id_number.encode()).hexdigest()
    with get_db() as conn:
        conn.execute("UPDATE users SET real_name = ?, id_number_hash = ?, is_realname = 1, age_group = ? WHERE id = ?",
                     (real_name, id_hash, age_group, current_user.id))
    return jsonify({'status': 'ok', 'message': '实名认证成功', 'age_group': age_group})

@app.route('/api/activate_achievement', methods=['POST'])
@login_required
def activate_achievement():
    code = request.get_json().get('code', '').strip()
    code_map = {
        'ZJ4512webmaster': ('站长', 30, 'is_webmaster'),
        'ZJ4512boss': ('老大！！！', 30, 'is_boss'),
        'ZJ4512Senior admin': ('高级管理员', 20, 'admin_level'),
        'ZJ4512admin': ('管理员', 10, 'admin_level'),
        'ZJ4512alpha': ('Alpha测试参与者', 10, 'is_alpha'),
        'ZJ4512Beta': ('Beta测试参与者', 10, 'is_beta'),
    }
    if code not in code_map:
        return jsonify({'error': '无效的认证码'}), 403

    name, points, flag = code_map[code]
    achievements = json.loads(current_user.earned_achievements or '[]')
    if name in achievements:
        return jsonify({'error': '该成就已获得'}), 400
    if name in ['站长', '老大！！！']:
        with get_db() as conn:
            existing = conn.execute(
                "SELECT u.username FROM user_achievements ua "
                "JOIN users u ON ua.user_id = u.id "
                "WHERE ua.achievement_id = (SELECT id FROM achievements WHERE name = ?) "
                "AND ua.user_id != ?",
                (name, current_user.id)
            ).fetchone()
            if existing:
                owner = existing['username']
                return jsonify({'error': f'该成就已被 {owner} 获得，不可重复认证'}), 400
    achievements.append(name)
    with get_db() as conn:
        conn.execute("UPDATE users SET earned_achievements = ?, credit_score = credit_score + ? WHERE id = ?",
                     (json.dumps(achievements), points, current_user.id))
        if flag.startswith('is_'):
            conn.execute(f"UPDATE users SET {flag} = 1 WHERE id = ?", (current_user.id,))
        else:
            conn.execute(f"UPDATE users SET {flag} = {flag} + 1 WHERE id = ?", (current_user.id,))
        ach_id = conn.execute("SELECT id FROM achievements WHERE name = ?", (name,)).fetchone()
        if ach_id:
            conn.execute("INSERT OR IGNORE INTO user_achievements (user_id, achievement_id) VALUES (?, ?)",
                         (current_user.id, ach_id['id']))
    return jsonify({'status': 'ok', 'message': f'🎉 获得成就：{name}！成长值 +{points}'})

@app.route('/api/report', methods=['POST'])
@login_required
def submit_report():
    data = request.get_json()
    target_type = data.get('target_type')
    target_id = data.get('target_id')
    reason = data.get('reason','').strip()
    if not target_type or not target_id or not reason: return jsonify({'error':'参数不完整'}),400
    with get_db() as conn:
        conn.execute("INSERT INTO reports (reporter_id, target_type, target_id, reason) VALUES (?,?,?,?)", (current_user.id, target_type, target_id, reason))
    return jsonify({'status':'ok','message':'举报已提交'})

# ========== 搜索用户（修复版） ==========
@app.route('/api/search_users')
def search_users():
    q = request.args.get('q','').strip()
    if not q: return jsonify([])
    with get_db() as conn:
        rows = conn.execute("SELECT id, username, credit_score, is_webmaster, is_boss, is_alpha, is_beta, avatar, display_id FROM users WHERE username LIKE ? LIMIT 20", ('%'+q+'%',)).fetchall()
        users = []
        for row in rows:
            d = dict(row)
            d['credit_score'] = d['credit_score'] or 0
            d['credit_level'] = get_credit_level(d['credit_score'])
            d['is_gold'] = d['credit_score'] >= 200 or d['is_webmaster'] or d['is_boss'] or d['is_alpha'] or d['is_beta']
            users.append(d)
    return jsonify(users)

@app.route('/api/level_center')
@login_required
def level_center():
    with get_db() as conn:
        row = conn.execute("SELECT exp, credit_score FROM users WHERE id = ?", (current_user.id,)).fetchone()
        if not row: return jsonify({'error':'用户不存在'}),404
        exp = row['exp']
        credit = row['credit_score']
        levels = [0,20,50,100,150,200]
        level = 1
        for i, lv in enumerate(levels, 1):
            if exp >= lv: level = i
        name = ['见习生','初级鉴定师','资深鉴定师','铜牌评级师','银牌评级师','金牌评级师'][level-1]
        if exp >= 200: name = '🌟 创世评级师'
        next_exp = 200 if exp >= 200 else min([l for l in levels if l > exp], default=200)
        return jsonify({'level':level,'name':name,'exp':exp,'next_level_exp':next_exp,'credit_score':credit})

@app.route('/api/daily_bonus', methods=['POST'])
@login_required
def daily_bonus():
    from datetime import date
    today = date.today().isoformat()
    with get_db() as conn:
        row = conn.execute("SELECT last_login_date FROM users WHERE id = ?", (current_user.id,)).fetchone()
        if row and row['last_login_date'] == today:
            return jsonify({'error':'今日已签到'}),400
        conn.execute("UPDATE users SET exp = exp + 2, login_days = login_days + 1, last_login_date = ? WHERE id = ?", (today, current_user.id))
    return jsonify({'status':'ok','message':'✅ 签到成功！+2 EXP'}),200

@app.route('/api/achievements')
@login_required
def get_achievements():
    with get_db() as conn:
        all_achs = conn.execute("SELECT id, name, description, icon, points FROM achievements ORDER BY id").fetchall()
        unlocked = conn.execute("SELECT achievement_id FROM user_achievements WHERE user_id = ?", (current_user.id,)).fetchall()
        unlocked_ids = [row['achievement_id'] for row in unlocked]
        result = []
        for a in all_achs:
            result.append({
                'id': a['id'],
                'name': a['name'],
                'description': a['description'],
                'icon': a['icon'],
                'points': a['points'],
                'unlocked': a['id'] in unlocked_ids
            })
    return jsonify(result)

@app.route('/api/admin/reports', methods=['GET'])
@login_required
@device_handshake_required
def get_reports():
    if current_user.admin_level < 1: return jsonify({'error': '权限不足'}), 403
    with get_db() as conn:
        rows = conn.execute(
            "SELECT r.*, u.username as reporter_name FROM reports r "
            "JOIN users u ON r.reporter_id = u.id "
            "WHERE r.status = 'pending' ORDER BY r.created_at DESC"
        ).fetchall()
        return jsonify([dict(row) for row in rows])

@app.route('/api/admin/reports/<int:report_id>', methods=['POST'])
@login_required
@device_handshake_required
def handle_report(report_id):
    if current_user.admin_level < 1: return jsonify({'error': '权限不足'}), 403
    data = request.get_json()
    action = data.get('action')
    with get_db() as conn:
        conn.execute("UPDATE reports SET status = ?, reviewed_by = ? WHERE id = ?",
                     ('approved' if action == 'approve' else 'rejected', current_user.id, report_id))
    return jsonify({'status': 'ok'})

@app.route('/api/admin/pending_posts', methods=['GET'])
@login_required
@device_handshake_required
def get_pending_posts():
    if current_user.admin_level < 1: return jsonify({'error': '权限不足'}), 403
    with get_db() as conn:
        rows = conn.execute(
            "SELECT p.*, u.username FROM posts p "
            "JOIN users u ON p.user_id = u.id "
            "WHERE p.status = 'pending' ORDER BY p.created_at ASC"
        ).fetchall()
        return jsonify([dict(row) for row in rows])

@app.route('/api/admin/approve_post/<int:post_id>', methods=['POST'])
@login_required
@device_handshake_required
def approve_post(post_id):
    if current_user.admin_level < 1: return jsonify({'error': '权限不足'}), 403
    with get_db() as conn:
        conn.execute("UPDATE posts SET status = 'approved' WHERE id = ?", (post_id,))
    return jsonify({'status': 'ok'})

@app.route('/api/admin/reject_post/<int:post_id>', methods=['POST'])
@login_required
@device_handshake_required
def reject_post(post_id):
    if current_user.admin_level < 1: return jsonify({'error': '权限不足'}), 403
    data = request.get_json()
    reason = data.get('reason', '无')
    with get_db() as conn:
        conn.execute("UPDATE posts SET status = 'rejected', reject_reason = ? WHERE id = ?", (reason, post_id))
    return jsonify({'status': 'ok'})

@app.route('/api/grade/<code>')
def get_grade_by_code(code):
    with get_db() as conn:
        post = conn.execute("SELECT id FROM posts WHERE grade_code = ? AND status = 'approved'", (code,)).fetchone()
        if post:
            return jsonify({'id': post['id']})
        return jsonify({'error': '未找到该评级码'}), 404

@app.route('/api/dm/conversations')
@login_required
def get_conversations():
    with get_db() as conn:
        rows = conn.execute("SELECT DISTINCT CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END AS other_user_id FROM messages WHERE sender_id = ? OR receiver_id = ?", (current_user.id, current_user.id, current_user.id)).fetchall()
        convs = []
        for row in rows:
            uid = row['other_user_id']
            other = conn.execute("SELECT id, username, credit_score, avatar, display_id FROM users WHERE id = ?", (uid,)).fetchone()
            if not other: continue
            last = conn.execute("SELECT content, created_at FROM messages WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?) ORDER BY created_at DESC LIMIT 1", (current_user.id, uid, uid, current_user.id)).fetchone()
            unread = conn.execute("SELECT COUNT(*) FROM messages WHERE receiver_id = ? AND sender_id = ? AND is_read = 0", (current_user.id, uid)).fetchone()[0]
            convs.append({
                'user_id': other['id'],
                'username': other['username'],
                'credit_score': other['credit_score'],
                'avatar': other['avatar'],
                'display_id': other['display_id'],
                'last_message': last['content'] if last else '',
                'last_time': last['created_at'] if last else None,
                'unread': unread
            })
        convs.sort(key=lambda x: x['last_time'] or '', reverse=True)
    return jsonify(convs)

@app.route('/api/dm/messages/<int:other_user_id>')
@login_required
def get_dm_messages(other_user_id):
    with get_db() as conn:
        conn.execute("UPDATE messages SET is_read = 1, read_at = CURRENT_TIMESTAMP WHERE receiver_id = ? AND sender_id = ? AND is_read = 0", (current_user.id, other_user_id))
        rows = conn.execute("SELECT id, sender_id, receiver_id, content, created_at, is_read FROM messages WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?) ORDER BY created_at ASC LIMIT 200", (current_user.id, other_user_id, other_user_id, current_user.id))
        return jsonify([dict(row) for row in rows])

@app.route('/api/dm/send', methods=['POST'])
@login_required
def send_dm():
    data = request.get_json()
    receiver_id = data.get('receiver_id')
    content = data.get('content','').strip()
    if not receiver_id or not content: return jsonify({'error':'参数不完整'}),400
    if receiver_id == current_user.id: return jsonify({'error':'不能给自己发私信'}),400
    if current_user.dm_ban_until:
        try:
            if datetime.datetime.now() < datetime.datetime.strptime(current_user.dm_ban_until, '%Y-%m-%d %H:%M:%S'):
                return jsonify({'error':'您当前被禁私信'}),403
        except: pass
    with get_db() as conn:
        receiver = conn.execute("SELECT id, credit_score FROM users WHERE id = ?", (receiver_id,)).fetchone()
        if not receiver: return jsonify({'error':'用户不存在'}),404
        risk_warning = None
        risk_words = ['转账','加微信','私下交易','汇款','银行卡','188','8888','V信','WX']
        for w in risk_words:
            if w in content:
                risk_warning = '⚠️ 请注意保护个人信息，勿轻信陌生人的转账或交易请求'
                break
        if receiver['credit_score'] < 60:
            risk_warning = '⚠️ 对方信誉分较低，请谨慎对话'
        cursor = conn.execute("INSERT INTO messages (sender_id, receiver_id, content) VALUES (?,?,?)", (current_user.id, receiver_id, content))
        new_msg = {'id':cursor.lastrowid,'sender_id':current_user.id,'receiver_id':receiver_id,'content':content,'created_at':datetime.datetime.now().isoformat(),'is_read':0}
    return jsonify({'status':'ok','message':new_msg,'warning':risk_warning}),201

@app.route('/api/dm/unread_count')
@login_required
def unread_dm_count():
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM messages WHERE receiver_id = ? AND is_read = 0", (current_user.id,)).fetchone()[0]
    return jsonify({'unread': count})

@app.route('/api/tags')
def get_tags():
    with get_db() as conn:
        rows = conn.execute("SELECT tag, COUNT(*) as count FROM posts WHERE tag IS NOT NULL AND tag != '' GROUP BY tag ORDER BY count DESC").fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/version')
def get_version():
    return jsonify({'version': 'V2.8.30s'})

# ========== 安全功能 ==========
@app.route('/api/admin/security_status', methods=['GET'])
@login_required
@device_handshake_required
def get_security_status():
    if current_user.admin_level < 1:
        return jsonify({'error': '权限不足'}), 403
    # 从用户对象读取真实冻结状态
    locks = {
        'warnlocker': current_user.freeze_level == 'warnlocker' if current_user.freeze_until and datetime.datetime.now() < datetime.datetime.fromisoformat(current_user.freeze_until) else False,
        'xzlocker_s': current_user.freeze_level == 'XZlocker-s' if current_user.freeze_until and datetime.datetime.now() < datetime.datetime.fromisoformat(current_user.freeze_until) else False,
        'icelocker': current_user.freeze_level == 'Icelocker' if current_user.freeze_until and datetime.datetime.now() < datetime.datetime.fromisoformat(current_user.freeze_until) else False,
        'xzlocker': current_user.freeze_level == 'XZlocker' if current_user.freeze_until and datetime.datetime.now() < datetime.datetime.fromisoformat(current_user.freeze_until) else False,
        'windlocker': current_user.freeze_level == 'windlocker' if current_user.freeze_until and datetime.datetime.now() < datetime.datetime.fromisoformat(current_user.freeze_until) else False,
    }
    return jsonify({'locks': locks, 'sukey': None, 'oem': {'oem': False, 'oem-small': False, 'oem+': False}})

@app.route('/api/admin/toggle_oem', methods=['POST'])
@login_required
@device_handshake_required
def toggle_oem():
    if current_user.admin_level < 1:
        return jsonify({'error': '权限不足'}), 403
    data = request.get_json()
    oem_type = data.get('type')
    enabled = data.get('enabled', False)
    return jsonify({'status': 'ok', 'message': f'OEM {oem_type} {"启用" if enabled else "禁用"}'})

# ========== 激活码系统 ==========
ACTIVATION_PREFIX_MAP = {
    'Admin': {'field': 'admin_level', 'value': 1},
    'Senior': {'field': 'admin_level', 'value': 3},
    'Webmaster': {'field': 'is_webmaster', 'value': 1},
    'Boss': {'field': 'is_boss', 'value': 1},
    'Alpha': {'field': 'is_alpha', 'value': 1},
    'Beta': {'field': 'is_beta', 'value': 1},
}

def verify_activation_code(code, expected_prefix=None):
    import re
    pattern = r'^([A-Za-z]+)-([A-Za-z0-9\-]+)-(\d{6})$'
    match = re.match(pattern, code)
    if not match:
        return False, "格式错误（正确格式：前缀-EUID-YYMMDD）", None, None
    prefix, euid, yymmdd = match.groups()
    if expected_prefix and prefix != expected_prefix:
        return False, f"前缀错误（应为 {expected_prefix}）", None, None
    with get_db() as conn:
        user = conn.execute("SELECT id, username FROM users WHERE display_id = ?", (euid,)).fetchone()
        if not user:
            return False, "该激活码EUID错误", None, None
    today = datetime.datetime.now().strftime('%y%m%d')
    if yymmdd != today:
        return False, "该激活码时间戳错误（仅当日有效）", None, None
    return True, "验证通过", euid, prefix

@app.route('/api/admin/unlock_by_code', methods=['POST'])
@login_required
@device_handshake_required
def unlock_by_code():
    data = request.get_json()
    code = data.get('code', '').strip()
    prefix = data.get('type', '').strip()
    if not code:
        return jsonify({'error': '请输入激活码'}), 400
    if prefix:
        valid, msg, euid, _ = verify_activation_code(code, prefix)
    else:
        valid, msg, euid, extracted_prefix = verify_activation_code(code)
        if not valid:
            return jsonify({'error': msg}), 400
        prefix = extracted_prefix
    if not valid:
        return jsonify({'error': msg}), 400
    if prefix not in ACTIVATION_PREFIX_MAP:
        return jsonify({'error': '无效的前缀'}), 400
    with get_db() as conn:
        target = conn.execute("SELECT * FROM users WHERE display_id = ?", (euid,)).fetchone()
        if not target:
            return jsonify({'error': '该激活码EUID错误'}), 404
        config = ACTIVATION_PREFIX_MAP[prefix]
        field = config['field']
        if field == 'admin_level':
            if target['admin_level'] >= config['value']:
                return jsonify({'error': f'该用户已是 {prefix}'}), 400
        else:
            if target[field] == 1:
                return jsonify({'error': f'该用户已是 {prefix}'}), 400
        if field == 'admin_level':
            conn.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (config['value'], target['id']))
        else:
            conn.execute(f"UPDATE users SET {field} = 1 WHERE id = ?", (target['id']))
        conn.execute(
            "INSERT INTO admin_logs (admin_id, admin_name, action, detail) VALUES (?, ?, 'activate_code', ?)",
            (current_user.id, current_user.username, json.dumps({
                'prefix': prefix,
                'target_euid': euid,
                'target_username': target['username']
            }))
        )
        conn.commit()
    return jsonify({'status': 'ok', 'message': f'✅ 已成功为 {target["username"]} 激活 {prefix}'})

# ========== SUkey 系统 ==========
_su_tokens = {}

@app.route('/api/admin/su_prepare', methods=['POST'])
@login_required
@device_handshake_required
def su_prepare():
    if current_user.admin_level < 2:
        return jsonify({'error': '权限不足，仅高级管理员可操作'}), 403
    sukey = secrets.token_hex(6)
    _su_tokens[current_user.id] = {
        'token': sukey,
        'expires': datetime.datetime.now() + datetime.timedelta(minutes=5)
    }
    return jsonify({'sukey': sukey, 'expires_in': 300})

@app.route('/api/admin/su', methods=['POST'])
@login_required
@device_handshake_required
def admin_su():
    if current_user.admin_level < 2:
        return jsonify({'error': '权限不足，仅高级管理员可操作'}), 403

    # 检查是否已冻结
    if current_user.freeze_level and current_user.freeze_until:
        try:
            freeze_until = datetime.datetime.fromisoformat(current_user.freeze_until)
            if datetime.datetime.now() < freeze_until:
                return jsonify({'error': f'账户已被冻结（{current_user.freeze_level}），解冻时间：{freeze_until}'}), 403
        except:
            pass

    data = request.get_json()
    target_euid = data.get('target_euid', '').strip()
    admin_euid = data.get('admin_euid', '').strip()
    sukey_input = data.get('sukey', '').strip()

    if not target_euid or not admin_euid or not sukey_input:
        return jsonify({'error': '目标EUID、你的EUID和SUkey不能为空'}), 400

    if admin_euid != current_user.display_id:
        return jsonify({'error': '你的EUID输入有误'}), 403

    token_record = _su_tokens.get(current_user.id)
    if not token_record or token_record['expires'] < datetime.datetime.now():
        return jsonify({'error': 'SUkey已过期或未生成'}), 403

    if token_record['token'] != sukey_input:
        return jsonify({'error': 'SUkey错误'}), 403

    del _su_tokens[current_user.id]

    # 记录本次SU调用
    with get_db() as conn:
        row = conn.execute("SELECT su_timestamps FROM users WHERE id = ?", (current_user.id,)).fetchone()
        timestamps = json.loads(row['su_timestamps']) if row and row['su_timestamps'] else []
        now_iso = datetime.datetime.now().isoformat()
        timestamps.append(now_iso)
        cutoff = (datetime.datetime.now() - datetime.timedelta(hours=36)).isoformat()
        timestamps = [t for t in timestamps if t > cutoff]
        su_count = len(timestamps)
        conn.execute("UPDATE users SET su_timestamps = ? WHERE id = ?", (json.dumps(timestamps), current_user.id))
        conn.commit()

    # 触发熔断判断
    freeze_triggered = None
    freeze_duration = None
    freeze_mark = None
    new_admin_level = None

    if su_count >= 20:
        freeze_triggered = 'XZlocker'
        freeze_duration = 365 * 24 * 60 * 60
        freeze_mark = '⚡ 该用户曾触发终极冻结，永久降级管理员'
        new_admin_level = 1
    elif su_count >= 15:
        freeze_triggered = 'Icelocker'
        freeze_duration = 48 * 60 * 60
        freeze_mark = '❄️ 该用户曾触发一级强冻，7天内无法升级高级管理'
        new_admin_level = 1
    elif su_count >= 10:
        freeze_triggered = 'XZlocker-s'
        freeze_duration = 36 * 60 * 60
        freeze_mark = '⚠️ 该用户曾触发中级冻结，3天内无法升级高级管理'
        new_admin_level = 1
    elif su_count >= 5:
        freeze_triggered = 'warnlocker'
        freeze_duration = 24 * 60 * 60
        freeze_mark = '🔔 该用户曾触发警告冻结，24h内部分功能受限'
        new_admin_level = current_user.admin_level

    if freeze_triggered:
        with get_db() as conn:
            freeze_until = (datetime.datetime.now() + datetime.timedelta(seconds=freeze_duration)).isoformat()
            conn.execute("""
                UPDATE users 
                SET freeze_level = ?, freeze_until = ?, freeze_mark = ?, admin_level = ?
                WHERE id = ?
            """, (freeze_triggered, freeze_until, freeze_mark, new_admin_level, current_user.id))
            conn.commit()
        if freeze_triggered == 'XZlocker':
            return jsonify({
                'error': f'🚫 终极冻结已触发！账号永久降级为普通管理员，所有高级权限永久取消。',
                'freeze_level': freeze_triggered,
                'su_count': su_count,
                'freeze_until': '永久'
            }), 403
        return jsonify({
            'error': f'⚠️ 账户触发 {freeze_triggered}，冻结至 {freeze_until}，{freeze_mark}',
            'freeze_level': freeze_triggered,
            'su_count': su_count,
            'freeze_until': freeze_until
        }), 403

    with get_db() as conn:
        target = conn.execute("SELECT * FROM users WHERE display_id = ?", (target_euid,)).fetchone()
        if not target:
            return jsonify({'error': '目标用户不存在'}), 404
        if target['admin_level'] >= 10:
            return jsonify({'error': '目标账号为站长，不可模拟登录'}), 403

        conn.execute(
            """INSERT INTO admin_logs (admin_id, admin_name, action, target_type, target_id, detail)
               VALUES (?, ?, 'admin_su', 'user', ?, ?)""",
            (current_user.id, current_user.username, target['id'], json.dumps({
                'target_username': target['username'],
                'target_euid': target_euid,
                'admin_euid': admin_euid,
                'method': 'SUkey-first',
                'su_count_window': su_count
            }))
        )
        # 保存原用户ID到session
        session['_su_original_user_id'] = current_user.id
        conn.commit()
        target_user = User(target)
        login_user(target_user, remember=False, duration=datetime.timedelta(minutes=30))

    return jsonify({
        'status': 'ok',
        'message': f'已切换到用户 {target["username"]}',
        'user': {
            'id': target['id'],
            'username': target['username'],
            'display_id': target['display_id'] or '',
            'admin_level': target.get('admin_level', 0)
        },
        'su_count_window': su_count
    })

@app.route('/api/admin/audit', methods=['POST'])
@login_required
@device_handshake_required
def admin_audit():
    if current_user.admin_level < 2:
        return jsonify({'error': '权限不足，仅高级管理员可操作'}), 403
    data = request.get_json()
    euid = data.get('euid', '').strip()
    time_start = data.get('time_start', '').strip()
    time_end = data.get('time_end', '').strip()
    if not euid:
        return jsonify({'error': '请输入目标用户的 EUID'}), 400
    with get_db() as conn:
        target = conn.execute("SELECT id, username FROM users WHERE display_id = ?", (euid,)).fetchone()
        if not target:
            return jsonify({'error': '用户不存在'}), 404
        user_id = target['id']
        time_condition = ""
        params = [user_id]
        if time_start:
            time_condition += " AND created_at >= ?"
            params.append(time_start)
        if time_end:
            time_condition += " AND created_at <= ?"
            params.append(time_end)
        posts = conn.execute(
            f"SELECT id, title, tag, status, created_at FROM posts WHERE user_id = ? {time_condition} ORDER BY created_at DESC",
            params
        ).fetchall()
        comments = conn.execute(
            f"SELECT id, post_id, created_at FROM comments WHERE user_id = ? {time_condition} ORDER BY created_at DESC",
            params
        ).fetchall()
        messages = conn.execute(
            f"SELECT id, sender_id, receiver_id, created_at FROM messages WHERE (sender_id = ? OR receiver_id = ?) {time_condition} ORDER BY created_at DESC",
            [user_id, user_id] + params[1:]
        ).fetchall()
        likes = conn.execute(
            f"SELECT id, post_id, created_at FROM likes WHERE user_id = ? {time_condition} ORDER BY created_at DESC",
            params
        ).fetchall()
        conn.execute(
            """INSERT INTO admin_logs (admin_id, admin_name, action, target_type, target_id, detail)
               VALUES (?, ?, 'admin_audit', 'user', ?, ?)""",
            (current_user.id, current_user.username, target['id'], json.dumps({
                'target_username': target['username'],
                'target_euid': euid,
                'time_start': time_start,
                'time_end': time_end
            }))
        )
        conn.commit()
    return jsonify({
        'status': 'ok',
        'target_user': target['username'],
        'target_euid': euid,
        'posts': [dict(p) for p in posts],
        'comments': [dict(c) for c in comments],
        'messages': [dict(m) for m in messages],
        'likes': [dict(l) for l in likes],
        'summary': {
            'post_count': len(posts),
            'comment_count': len(comments),
            'message_count': len(messages),
            'like_count': len(likes)
        }
    })

@app.route('/api/parliament/trigger', methods=['POST'])
@login_required
@device_handshake_required
def parliament_trigger():
    if current_user.admin_level < 1:
        return jsonify({'error': '权限不足'}), 403
    data = request.get_json()
    target_user_id = data.get('target_user_id')
    reason = data.get('reason', '').strip()
    if not target_user_id or not reason:
        return jsonify({'error': '目标用户ID和原因不能为空'}), 400
    vote_id = secrets.token_hex(8)
    with get_db() as conn:
        target = conn.execute("SELECT id, username FROM users WHERE id = ?", (target_user_id,)).fetchone()
        if not target:
            return jsonify({'error': '目标用户不存在'}), 404
        expires_at = (datetime.datetime.now() + datetime.timedelta(hours=2)).isoformat()
        conn.execute(
            """INSERT INTO parliament_votes (vote_id, initiated_by, trigger_reason, expires_at)
               VALUES (?, ?, ?, ?)""",
            (vote_id, current_user.id, reason, expires_at)
        )
        admins = conn.execute("SELECT id, username FROM users WHERE admin_level >= 2").fetchall()
        for admin in admins:
            if admin['id'] == current_user.id:
                continue
            conn.execute(
                "INSERT INTO messages (sender_id, receiver_id, content, is_system) VALUES (?, ?, ?, ?)",
                (0, admin['id'], f"📣 议会投票：{current_user.username} 发起对用户 {target['username']} 的投票，原因：{reason}。请前往安全控制台表决。", 1)
            )
        conn.commit()
    return jsonify({
        'status': 'ok',
        'vote_id': vote_id,
        'expires_at': expires_at,
        'message': '投票已发起，已通知所有高级管理员'
    })

@app.route('/api/parliament/active')
@login_required
@device_handshake_required
def get_active_votes():
    if current_user.admin_level < 1:
        return jsonify({'error': '权限不足'}), 403
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM parliament_votes WHERE status = 'active' AND expires_at > datetime('now') ORDER BY created_at DESC"
        ).fetchall()
        votes = []
        for row in rows:
            votes.append(dict(row))
            voted = conn.execute(
                "SELECT id FROM parliament_vote_records WHERE vote_id = ? AND voter_id = ?",
                (row['vote_id'], current_user.id)
            ).fetchone()
            votes[-1]['has_voted'] = 1 if voted else 0
        return jsonify(votes)

@app.route('/api/parliament/vote', methods=['POST'])
@login_required
@device_handshake_required
def parliament_vote():
    if current_user.admin_level < 1:
        return jsonify({'error': '权限不足'}), 403
    data = request.get_json()
    vote_id = data.get('vote_id')
    choice = data.get('choice')
    if not vote_id or choice not in ('approve', 'reject'):
        return jsonify({'error': '参数不完整'}), 400
    with get_db() as conn:
        vote = conn.execute(
            "SELECT * FROM parliament_votes WHERE vote_id = ? AND status = 'active' AND expires_at > datetime('now')",
            (vote_id,)
        ).fetchone()
        if not vote:
            return jsonify({'error': '投票不存在或已过期'}), 404
        existing = conn.execute(
            "SELECT id FROM parliament_vote_records WHERE vote_id = ? AND voter_id = ?",
            (vote_id, current_user.id)
        ).fetchone()
        if existing:
            return jsonify({'error': '您已经投过票'}), 400
        conn.execute(
            "INSERT INTO parliament_vote_records (vote_id, voter_id, choice) VALUES (?, ?, ?)",
            (vote_id, current_user.id, choice)
        )
        conn.commit()
        total_admins = conn.execute("SELECT COUNT(*) FROM users WHERE admin_level >= 2").fetchone()[0]
        votes = conn.execute(
            "SELECT choice, COUNT(*) as count FROM parliament_vote_records WHERE vote_id = ? GROUP BY choice",
            (vote_id,)
        ).fetchall()
        approve_count = sum(v['count'] for v in votes if v['choice'] == 'approve')
        reject_count = sum(v['count'] for v in votes if v['choice'] == 'reject')
        total_votes = approve_count + reject_count
        if total_votes >= total_admins or (total_votes > 0 and approve_count > reject_count):
            conn.execute("UPDATE parliament_votes SET status = 'passed', result = 'freeze' WHERE vote_id = ?", (vote_id,))
            conn.execute(
                "INSERT INTO messages (sender_id, receiver_id, content, is_system) VALUES (?, ?, ?, ?)",
                (0, vote['initiated_by'], f"✅ 投票 {vote_id} 已通过，结果：冻结。", 1)
            )
            conn.commit()
            return jsonify({'status': 'ok', 'message': '投票已通过，执行冻结'})
        conn.commit()
    return jsonify({'status': 'ok', 'message': '投票已记录'})

@app.route('/api/system_messages')
@login_required
def get_system_messages():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM messages WHERE receiver_id = ? AND is_system = 1 ORDER BY created_at DESC LIMIT 50", (current_user.id,)).fetchall()
        return jsonify([dict(row) for row in rows])

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

