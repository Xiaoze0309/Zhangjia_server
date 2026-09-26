from flask import Flask, request, jsonify, render_template, send_from_directory, session
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, datetime, re, json, hashlib, base64, io, requests, random, secrets, shutil, string
from werkzeug.utils import secure_filename
from PIL import Image
from functools import wraps

from security import init_all_security, admin_required, owner_required, rate_limit

from center_app import center_bp

TZ_BEIJING = datetime.timezone(datetime.timedelta(hours=8))
def now_bj():
    return datetime.datetime.now(TZ_BEIJING)

def gen_epid():
    ts = now_bj().strftime("%y%m%d%H")     # 25092314
    alphabet = string.ascii_letters + string.digits   # A-Za-z0-9，URL安全
    rand = ''.join(secrets.choice(alphabet) for _ in range(12))
    return f"EPID-{ts}-{rand}"

def gen_test_epid():
    """生成测试单 EPID：EPID-TEXT-6位数字"""
    while True:
        code = ''.join(str(secrets.randbelow(10)) for _ in range(6))
        epid = f"EPID-TEXT-{code}"
        with get_db() as conn:
            if not conn.execute("SELECT id FROM cert_orders WHERE order_no=?", (epid,)).fetchone():
                return epid

app = Flask(__name__)
app.register_blueprint(center_bp)
app.secret_key = 'zhangjia-2026-fixed-secret-key'
app.config['REMEMBER_COOKIE_DURATION'] = datetime.timedelta(days=30)
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=30)
init_all_security(app)

UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

DEFAULT_VERSION = 'LanOS 2.2609.C01.ALCFSAE'

# ========== Beta 环境配置 ==========
BETA_DB_PATH = 'betadata.db'
MAIN_DB_PATH = 'database.db'

def is_beta_request():
    """判断当前请求是否来自 beta 子域名"""
    try:
        host = (request.host or '').split(':')[0].lower()
        return host.startswith('beta.')
    except Exception:
        return False

def get_beta_enabled():
    """从主库 settings 读取 beta 开关（默认开启）"""
    try:
        with sqlite3.connect(MAIN_DB_PATH) as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = 'beta_enabled'").fetchone()
            return row[0] == '1' if row else True
    except Exception:
        return True

@app.before_request
def check_beta_status():
    """Beta 关闭时拦截除管理员 API 之外的所有请求"""
    if is_beta_request() and not get_beta_enabled():
        if not request.path.startswith('/api/admin/'):
            return jsonify({
                'error': 'Beta 环境已暂时关闭',
                'message': '请访问主站 www.zhangjiacoins.dpdns.org'
            }), 503

# ========== 数据库 ==========
def get_db():
    """根据请求主机自动选择主库或 beta 库"""
    try:
        if is_beta_request():
            db_path = BETA_DB_PATH
        else:
            db_path = MAIN_DB_PATH
    except (RuntimeError, AttributeError):
        db_path = MAIN_DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db(db_path=MAIN_DB_PATH):
    """初始化数据库结构，可指定路径"""
    with sqlite3.connect(db_path) as conn:
        for col in ['avatar','bio','phone','phone_verified','credit_score','growth_level',
                    'is_realname','age_group','is_alpha','is_beta','is_boss','is_webmaster',
                    'admin_level','earned_achievements','login_days','last_login_date',
                    'bans_issued','valid_reports','location','mute_until','post_ban_until',
                    'comment_ban_until','dm_ban_until','admin_ban_until','ban_until',
                    'real_name','id_number_hash','display_id','is_owner',
                    'freeze_level','freeze_until','freeze_mark','su_timestamps',
                    'last_device_handshake']:
            try: conn.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except: pass

        for col in ['is_pinned INTEGER DEFAULT 0','pinned_at TIMESTAMP',
                    'report_code TEXT','post_type TEXT DEFAULT "grade"',
                    'status TEXT DEFAULT "pending"','reject_reason TEXT',
                    'grade_code TEXT','views INTEGER DEFAULT 0']:
            try: conn.execute(f"ALTER TABLE posts ADD COLUMN {col}")
            except: pass

        try: conn.execute("ALTER TABLE comments ADD COLUMN parent_id INTEGER DEFAULT NULL")
        except: pass

        conn.execute("CREATE INDEX IF NOT EXISTS idx_posts_pinned ON posts(is_pinned)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comments_parent ON comments(parent_id)")

        conn.execute('''CREATE TABLE IF NOT EXISTS favorites (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, post_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, post_id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS follows (id INTEGER PRIMARY KEY AUTOINCREMENT, follower_id INTEGER NOT NULL, following_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(follower_id, following_id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS checkins (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, checkin_date TEXT NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, checkin_date))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS comment_likes (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, comment_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, comment_id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS achievements (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT NOT NULL, type TEXT NOT NULL, icon TEXT, points INTEGER DEFAULT 10)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS titles (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS achievement_titles (achievement_id INTEGER NOT NULL, title_id INTEGER NOT NULL)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS user_achievements (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, achievement_id INTEGER NOT NULL, unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(user_id, achievement_id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY AUTOINCREMENT, reporter_id INTEGER NOT NULL, target_type TEXT NOT NULL, target_id INTEGER NOT NULL, reason TEXT NOT NULL, status TEXT DEFAULT 'pending', reviewed_by INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id INTEGER NOT NULL, receiver_id INTEGER NOT NULL, content TEXT NOT NULL, is_read INTEGER DEFAULT 0, read_at TIMESTAMP, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        try: conn.execute("ALTER TABLE messages ADD COLUMN is_system INTEGER DEFAULT 0")
        except: pass
        try: conn.execute("ALTER TABLE messages ADD COLUMN notif_type TEXT DEFAULT NULL")
        except: pass
        conn.execute('''CREATE TABLE IF NOT EXISTS likes (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(post_id, user_id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS comments (id INTEGER PRIMARY KEY AUTOINCREMENT, post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, content TEXT NOT NULL, parent_id INTEGER DEFAULT NULL, reply_to_user_id INTEGER DEFAULT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('app_version', ?)", (DEFAULT_VERSION,))
        conn.execute('''CREATE TABLE IF NOT EXISTS admin_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, admin_id INTEGER NOT NULL, admin_name TEXT NOT NULL, action TEXT NOT NULL, target_type TEXT, target_id INTEGER, detail TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS coin_ratings (id INTEGER PRIMARY KEY AUTOINCREMENT, cert_number TEXT UNIQUE NOT NULL, name TEXT NOT NULL, grade TEXT, era TEXT, variety TEXT, size TEXT, weight TEXT, comment TEXT, front_image TEXT, back_image TEXT, guarantee_amount INTEGER, manager TEXT DEFAULT '小泽', extra_info TEXT DEFAULT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        if not conn.execute("SELECT id FROM achievements LIMIT 1").fetchone():
            for a in [('表里如一','信誉分达到300','credit','🏆',10),('信守不渝','信誉分达到400','credit','🏆',20),('言必行行必果','信誉分达到500','credit','🏆',30),('开诚布公','信誉分达到600','credit','🏆',50),('Alpha测试参与者','V1.0-1.9注册','identity','🔰',10),('Beta测试参与者','V2.0-3.9注册','identity','🔰',10),('站长','认证站长','identity','👑',30),('老大！！！','认证老大','identity','👑',30),('高级管理员','认证高级管理员','identity','⚜️',20),('管理员','认证管理员','identity','🔱',10),('包拯','封禁20个无误封','action','⚖️',10),('遵法守法','有效举报20次','action','🛡️',10),('每日达','累计登录60天','login','📅',20),('日复一日，年复一年','累计登录365天','login','📅',50)]:
                conn.execute("INSERT INTO achievements (name, description, type, icon, points) VALUES (?,?,?,?,?)", a)
        conn.execute("UPDATE posts SET status = 'approved' WHERE status IS NULL")
        conn.commit()

# 初始化主库
init_db(MAIN_DB_PATH)

# 初始化 beta 库（如果不存在就从主库复制，存在则同步结构）
if not os.path.exists(BETA_DB_PATH):
    shutil.copy(MAIN_DB_PATH, BETA_DB_PATH)
    print(f"[beta] 已创建 {BETA_DB_PATH}（从主库复制）")
else:
    init_db(BETA_DB_PATH)
    print(f"[beta] {BETA_DB_PATH} 结构已同步")

# 确保 beta_enabled 默认开启
with sqlite3.connect(MAIN_DB_PATH) as conn:
    conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('beta_enabled', '1')")
    conn.commit()


class User(UserMixin):
    def __init__(self, row):
        row = dict(row)
        self.id = row['id']
        self.username = row['username']
        self.password_hash = row['password_hash']
        self.email = row['email']
        self.exp = row.get('exp', 0) or 0
        self.is_admin = row.get('is_admin', 0)
        self.admin_level = row.get('admin_level', 0) or 0
        self.credit_score = row.get('credit_score') or 120
        self.bio = row.get('bio', '这个人很懒，什么都没写。')
        self.avatar = row.get('avatar', None)
        self.is_realname = row.get('is_realname', 0)
        self.real_name = row.get('real_name', '')
        self.age_group = row.get('age_group', None)
        self.phone = row.get('phone', None)
        self.phone_verified = row.get('phone_verified', 0)
        self.display_id = row.get('display_id', '')
        earned = row.get('earned_achievements')
        self.earned_achievements = json.loads(earned) if earned else []
        self.login_days = row.get('login_days', 0) or 0
        self.is_boss = row.get('is_boss', 0)
        self.is_webmaster = row.get('is_webmaster', 0)
        self.is_alpha = row.get('is_alpha', 0)
        self.is_beta = row.get('is_beta', 0)
        self.location = row.get('location', '未知地区')
        self.post_ban_until = row.get('post_ban_until', None)
        self.comment_ban_until = row.get('comment_ban_until', None)
        self.dm_ban_until = row.get('dm_ban_until', None)
        self.is_owner = row.get('is_owner', 0)
        self.freeze_level = row.get('freeze_level', None)
        self.freeze_until = row.get('freeze_until', None)
        self.freeze_mark = row.get('freeze_mark', None)
        su_raw = row.get('su_timestamps')
        self.su_timestamps = json.loads(su_raw) if su_raw else []
        self.last_device_handshake = row.get('last_device_handshake', None)

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return User(row) if row else None

ROMAN_MAP = {0:'',1:'I',2:'II',3:'III',4:'IV',5:'V',6:'VI',7:'VII',8:'VIII',9:'IX',10:'X',11:'XI',12:'XII',13:'XIII',14:'XIV',15:'XV',16:'XVI',17:'XVII',18:'XVIII'}

def encrypt_random(raw):
    num = int(raw); bin_str = bin(num)[2:]
    while len(bin_str) % 4 != 0: bin_str = '0' + bin_str
    hex_str = ''
    for i in range(0, len(bin_str), 4):
        hex_str += hex(int(bin_str[i:i+4], 2))[2:].upper()
    enc_str = str(int(hex_str, 16))
    return enc_str[-9:] if len(enc_str) > 9 else enc_str.zfill(9)

def generate_display_id():
    date_str = now_bj().strftime("%y%m%d")
    while True:
        raw = str(random.randint(100000000, 999999999))
        if raw[0] != '0': break
    enc_num = encrypt_random(raw)
    roman = ROMAN_MAP.get(int(enc_num[-2]) + int(enc_num[-1]), '')
    return f"{date_str}-{enc_num}{roman}"

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

def get_growth_level(exp): return max(1, (exp or 0) // 50 + 1)

def get_ip_location(ip):
    if not ip: return '未知地区'
    if ip.startswith('127.') or ip.startswith('192.168.') or ip.startswith('10.') or ip == '::1': return '本地'
    try:
        r = requests.get(f'http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,regionName,city', timeout=2)
        data = r.json()
        if data.get('status') == 'success':
            return f"{data.get('regionName','')}·{data.get('city','')}"
    except: pass
    return '未知地区'

# ========== 页面路由 ==========
@app.route('/')
def index():
    host = (request.host or '').split(':')[0].lower()
    if host.startswith('intro.'):
        return render_template('intro.html')
    if host.startswith('talk.'):
        return render_template('talk.html')
    if host.startswith('beta.'):
        return render_template('beta.html')
    return render_template('index.html')

@app.route('/talk')
def talk():
    return render_template('talk.html')

@app.route('/talk/<int:post_id>')
def talk_detail(post_id):
    return render_template('talk_detail.html')

@app.route('/intro')
def intro():
    return render_template('intro.html')

@app.route('/intro/lan')
def intro_lan():
    return render_template('intro_lan.html')

@app.route('/intro/safe')
def intro_safe():
    return render_template('intro_safe.html')

@app.route('/beta')
def beta():
    return render_template('beta.html')

@app.route('/privacy')
def privacy(): return render_template('privacy.html')

@app.route('/privacy-realname')
def privacy_realname(): return render_template('privacy-realname.html')

@app.route('/privacy-ip')
def privacy_ip(): return render_template('privacy-ip.html')

@app.route('/privacy-dm')
def privacy_dm(): return render_template('privacy-dm.html')

@app.route('/privacy-phone')
def privacy_phone(): return render_template('privacy-phone.html')

@app.route('/api/version')
def get_version():
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'app_version'").fetchone()
        return jsonify({'version': row['value'] if row else DEFAULT_VERSION})

# ========== 注册/登录 ==========
@app.route('/api/register', methods=['POST'])
@rate_limit(3, 60)
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    email = data.get('email', '').strip()
    if not username or not password: return jsonify({'error': '用户名和密码不能为空'}), 400
    if len(username) < 3: return jsonify({'error': '用户名至少3个字符'}), 400
    if len(password) < 4: return jsonify({'error': '密码至少4个字符'}), 400
    if email and not is_valid_email(email): return jsonify({'error': '邮箱格式不正确'}), 400
    try:
        with get_db() as conn:
            cursor = conn.execute("INSERT INTO users (username, password_hash, email, credit_score) VALUES (?,?,?,120)",
                                  (username, hash_password(password), email if email else None))
            new_id = cursor.lastrowid
            display_id = generate_display_id()
            while conn.execute("SELECT id FROM users WHERE display_id = ?", (display_id,)).fetchone():
                display_id = generate_display_id()
            conn.execute("UPDATE users SET display_id = ? WHERE id = ?", (display_id, new_id))
        return jsonify({'status': 'ok', 'message': '注册成功'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': '用户名已存在'}), 400

@app.route('/api/login', methods=['POST'])
@rate_limit(5, 60)
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password: return jsonify({'error': '请输入用户名和密码'}), 400
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row or not check_password(password, row['password_hash']):
            return jsonify({'error': '用户名或密码错误'}), 401
        session.pop('_su_original_user_id', None)
        user = User(row)
        login_user(user, remember=True, duration=datetime.timedelta(days=30))
        today = now_bj().date().isoformat()
        if row['last_login_date'] != today:
            conn.execute("UPDATE users SET login_days = login_days + 1, last_login_date = ? WHERE id = ?", (today, user.id))
        ip = (request.headers.get('X-Forwarded-For', request.remote_addr) or '').split(',')[0].strip()
        loc = get_ip_location(ip)
        if loc not in ['本地', '未知地区']:
            conn.execute("UPDATE users SET location = ? WHERE id = ?", (loc, user.id))
        return jsonify({'status': 'ok', 'user': {
            'id': row['id'], 'username': row['username'], 'email': row['email'],
            'exp': row['exp'], 'credit_score': row['credit_score'] or 120,
            'is_admin': row['is_admin'], 'admin_level': row['admin_level'] or 0,
            'display_id': row['display_id']
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
                login_user(User(row), remember=True, duration=datetime.timedelta(days=30))
                return jsonify({'status': 'ok', 'message': '已退出模拟登录'})
    logout_user()
    return jsonify({'status': 'ok'})

@app.route('/api/me')
def me():
    if current_user.is_authenticated:
        is_su = session.get('_su_original_user_id') is not None
        return jsonify({
            'id': current_user.id, 'username': current_user.username,
            'email': current_user.email, 'exp': current_user.exp,
            'credit_score': current_user.credit_score,
            'is_admin': current_user.is_admin, 'admin_level': current_user.admin_level,
            'bio': current_user.bio, 'avatar': current_user.avatar,
            'is_realname': current_user.is_realname, 'age_group': current_user.age_group,
            'phone': current_user.phone, 'phone_verified': current_user.phone_verified,
            'display_id': current_user.display_id,
            'earned_achievements': current_user.earned_achievements,
            'login_days': current_user.login_days, 'location': current_user.location,
            'is_webmaster': current_user.is_webmaster, 'is_boss': current_user.is_boss,
            'is_alpha': current_user.is_alpha, 'is_beta': current_user.is_beta,
            'is_owner': current_user.is_owner, 'is_su_mode': is_su,
            'is_beta_env': is_beta_request()
        })
    return jsonify({'error': '未登录'}), 401

@app.route('/api/user/<int:user_id>')
def get_user_profile(user_id):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row: return jsonify({'error': '用户不存在'}), 404
        user = dict(row)
        user['credit_score'] = user.get('credit_score') or 120
        user['credit_level'] = get_credit_level(user['credit_score'])
        user['growth_level'] = get_growth_level(user.get('exp', 0))
        user['post_count'] = conn.execute("SELECT COUNT(*) FROM posts WHERE user_id = ?", (user_id,)).fetchone()[0]
        user['like_count'] = conn.execute("SELECT COUNT(*) FROM likes l JOIN posts p ON l.post_id = p.id WHERE p.user_id = ?", (user_id,)).fetchone()[0]
        user['follower_count'] = conn.execute("SELECT COUNT(*) FROM follows WHERE following_id = ?", (user_id,)).fetchone()[0]
        user['following_count'] = conn.execute("SELECT COUNT(*) FROM follows WHERE follower_id = ?", (user_id,)).fetchone()[0]
        titles = conn.execute("SELECT t.name FROM user_displayed_titles dt JOIN titles t ON dt.title_id = t.id WHERE dt.user_id = ? ORDER BY dt.display_order", (user_id,)).fetchall() if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_displayed_titles'").fetchone() else []
        user['display_titles'] = [t['name'] for t in titles]
        credit = user['credit_score']
        user['is_gold'] = credit >= 200 or user.get('is_webmaster') or user.get('is_boss') or user.get('is_alpha') or user.get('is_beta')
        if current_user.is_authenticated:
            follow = conn.execute("SELECT id FROM follows WHERE follower_id = ? AND following_id = ?", (current_user.id, user_id)).fetchone()
            user['is_following'] = 1 if follow else 0
        else:
            user['is_following'] = 0
    return jsonify(user)

# ========== 帖子 ==========
@app.route('/api/posts')
def get_posts():
    search = request.args.get('search', '').strip()
    tag = request.args.get('tag', '').strip()
    user_id = request.args.get('user_id', '')
    feed = request.args.get('feed', 'all')
    section = request.args.get('section', 'home')

    sql = """SELECT posts.*, users.username, users.credit_score, users.is_webmaster,
             users.is_boss, users.is_alpha, users.is_beta, users.avatar, users.display_id
             FROM posts LEFT JOIN users ON posts.user_id = users.id WHERE 1=1"""
    params = []
    sql += " AND posts.section = ?"
    params.append(section)
    if not current_user.is_authenticated or (current_user.admin_level < 1 and not current_user.is_webmaster):
        sql += " AND posts.status = 'approved'"
    if search:
        sql += " AND (posts.title LIKE ? OR posts.content LIKE ? OR posts.tag LIKE ? OR posts.grade_code = ?)"
        like = '%' + search + '%'
        params.extend([like, like, like, search])
    if tag:
        sql += " AND posts.tag LIKE ?"
        params.append('%' + tag + '%')
    if user_id and user_id.isdigit():
        sql += " AND posts.user_id = ?"
        params.append(int(user_id))
    if feed == 'following' and current_user.is_authenticated:
        sql += " AND posts.user_id IN (SELECT following_id FROM follows WHERE follower_id = ?)"
        params.append(current_user.id)

    sql += " ORDER BY posts.is_pinned DESC, posts.pinned_at DESC, posts.id DESC"

    with get_db() as conn:
        posts = [dict(r) for r in conn.execute(sql, params).fetchall()]
        for p in posts:
            p['like_count'] = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", (p['id'],)).fetchone()[0]
            p['comment_count'] = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", (p['id'],)).fetchone()[0]
            if current_user.is_authenticated:
                p['liked'] = 1 if conn.execute("SELECT id FROM likes WHERE post_id = ? AND user_id = ?", (p['id'], current_user.id)).fetchone() else 0
                p['favorited'] = 1 if conn.execute("SELECT id FROM favorites WHERE post_id = ? AND user_id = ?", (p['id'], current_user.id)).fetchone() else 0
            else:
                p['liked'] = 0; p['favorited'] = 0
            credit = p.get('credit_score') or 0
            p['is_gold'] = credit >= 200 or p.get('is_webmaster') or p.get('is_boss') or p.get('is_alpha') or p.get('is_beta')
            p['thumb'] = '/uploads/' + p['images'].split(',')[0] if p.get('images') else None
    return jsonify(posts)

@app.route('/api/posts', methods=['POST'])
@login_required
def add_post():
    if current_user.admin_level < 1 and not current_user.is_webmaster and not current_user.is_boss:
        return jsonify({'error': '只有管理员可以发帖'}), 403
    if current_user.post_ban_until:
        try:
            if now_bj().replace(tzinfo=None) < datetime.datetime.strptime(current_user.post_ban_until, '%Y-%m-%d %H:%M:%S'):
                return jsonify({'error': '您当前被禁帖'}), 403
        except: pass

    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    tag = request.form.get('tag', '').strip()
    post_type = request.form.get('type', 'grade')
    grade_code = request.form.get('grade_code', '').strip()
    section = request.form.get('section', 'home')

    if not title: return jsonify({'error': '标题不能为空'}), 400
    if not tag: return jsonify({'error': '请选择分类'}), 400

    for w in ['涉黄', '涉黑', '违法']:
        if w in title or w in content: return jsonify({'error': '内容包含敏感词'}), 400

    if grade_code:
        if post_type == 'grade':
            if not re.match(r'^\d{8,12}$', grade_code): return jsonify({'error': '评级码需为8-12位纯数字'}), 400
        else:
            if not re.match(r'^\d{6}-(\d{5}|号外\(HW\)|HW)-\d{8}$', grade_code):
                return jsonify({'error': '综合报格式：部门代码-第几报-日期，或 部门代码-号外(HW)-日期'}), 400

    with get_db() as conn:
        recent = conn.execute("SELECT id FROM posts WHERE user_id=? AND title=? AND created_at > datetime('now','-5 seconds')",
                              (current_user.id, title)).fetchone()
        if recent: return jsonify({'error': '请勿重复提交'}), 429

    files = request.files.getlist('images')
    saved = []
    for f in files:
        if f and f.filename and '.' in f.filename:
            ext = f.filename.rsplit('.', 1)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                name = f"{now_bj().strftime('%Y%m%d%H%M%S%f')}_{secure_filename(f.filename)}"
                try:
                    img = Image.open(f.stream)
                    if img.mode in ('RGBA', 'LA', 'P'): img = img.convert('RGB')
                    img.thumbnail((1200, 1200))
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=80, optimize=True)
                    buf.seek(0)
                    with open(os.path.join(app.config['UPLOAD_FOLDER'], name), 'wb') as out:
                        out.write(buf.read())
                    saved.append(name)
                except Exception as e:
                    print(f"图片处理失败: {e}")

    with get_db() as conn:
        conn.execute("""INSERT INTO posts (user_id, title, content, images, tag, grade_code, status, post_type, section)
                        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                     (current_user.id, title, content, ','.join(saved) if saved else None, tag,
                      grade_code if grade_code else None, post_type, section))
        conn.execute("UPDATE users SET exp = exp + 3 WHERE id = ?", (current_user.id,))
    return jsonify({'status': 'ok'}), 201

@app.route('/api/posts/<int:post_id>')
def get_post(post_id):
    with get_db() as conn:
        post = conn.execute("""SELECT posts.*, users.username, users.credit_score, users.is_webmaster,
                               users.is_boss, users.is_alpha, users.is_beta, users.avatar, users.display_id
                               FROM posts LEFT JOIN users ON posts.user_id = users.id WHERE posts.id = ?""",
                            (post_id,)).fetchone()
        if not post: return jsonify({'error': '帖子不存在'}), 404
        if post['status'] != 'approved' and (not current_user.is_authenticated or (current_user.admin_level < 1 and not current_user.is_webmaster)):
            return jsonify({'error': '该帖子未通过审核'}), 403

        p = dict(post)
        conn.execute("UPDATE posts SET views = COALESCE(views, 0) + 1 WHERE id = ?", (post_id,))
        p['views'] = (p.get('views') or 0) + 1
        p['like_count'] = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", (post_id,)).fetchone()[0]
        p['comment_count'] = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", (post_id,)).fetchone()[0]
        if current_user.is_authenticated:
            p['liked'] = 1 if conn.execute("SELECT id FROM likes WHERE post_id = ? AND user_id = ?", (post_id, current_user.id)).fetchone() else 0
            p['favorited'] = 1 if conn.execute("SELECT id FROM favorites WHERE post_id = ? AND user_id = ?", (post_id, current_user.id)).fetchone() else 0
        else:
            p['liked'] = 0; p['favorited'] = 0

        rows = conn.execute("""SELECT comments.*, users.username, users.credit_score, users.is_webmaster,
                               users.is_boss, users.is_alpha, users.is_beta, users.avatar, users.display_id
                               FROM comments LEFT JOIN users ON comments.user_id = users.id
                               WHERE post_id = ? ORDER BY comments.id ASC""", (post_id,)).fetchall()
        all_comments = []
        for c in rows:
            d = dict(c)
            credit = d.get('credit_score') or 0
            d['is_gold'] = credit >= 200 or d.get('is_webmaster') or d.get('is_boss') or d.get('is_alpha') or d.get('is_beta')
            d['like_count'] = conn.execute("SELECT COUNT(*) FROM comment_likes WHERE comment_id = ?", (d['id'],)).fetchone()[0]
            d['liked'] = 0
            if current_user.is_authenticated:
                d['liked'] = 1 if conn.execute("SELECT id FROM comment_likes WHERE comment_id = ? AND user_id = ?", (d['id'], current_user.id)).fetchone() else 0
            all_comments.append(d)

        top = [c for c in all_comments if not c.get('parent_id')]
        for t in top:
            t['children'] = [c for c in all_comments if c.get('parent_id') == t['id']]
        p['comments'] = top
        credit = p.get('credit_score') or 0
        p['is_gold'] = credit >= 200 or p.get('is_webmaster') or p.get('is_boss') or p.get('is_alpha') or p.get('is_beta')
    return jsonify(p)

@app.route('/api/posts/<int:post_id>/edit', methods=['POST'])
@login_required
def edit_post(post_id):
    with get_db() as conn:
        post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if not post: return jsonify({'error': '帖子不存在'}), 404
        if post['user_id'] != current_user.id and current_user.admin_level < 1 and not current_user.is_webmaster:
            return jsonify({'error': '无权编辑'}), 403
        data = request.get_json() or {}
        title = (data.get('title') or '').strip()
        content = (data.get('content') or '').strip()
        if not title: return jsonify({'error': '标题不能为空'}), 400
        conn.execute("UPDATE posts SET title = ?, content = ? WHERE id = ?", (title, content, post_id))
        conn.execute("INSERT INTO admin_logs (admin_id, admin_name, action, target_type, target_id, detail) VALUES (?, ?, 'edit_post', 'post', ?, ?)",
                     (current_user.id, current_user.username, post_id, json.dumps({'title': title})))
        conn.commit()
    return jsonify({'status': 'ok'})

@app.route('/api/posts/<int:post_id>/like', methods=['POST'])
@login_required
def toggle_like(post_id):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM likes WHERE post_id = ? AND user_id = ?", (post_id, current_user.id)).fetchone()
        if existing:
            conn.execute("DELETE FROM likes WHERE id = ?", (existing['id'],))
            return jsonify({'status': 'unliked'})
        conn.execute("INSERT INTO likes (post_id, user_id) VALUES (?,?)", (post_id, current_user.id))
        author = conn.execute("SELECT user_id, title FROM posts WHERE id = ?", (post_id,)).fetchone()
        if author:
            conn.execute("UPDATE users SET credit_score = credit_score + 2 WHERE id = ?", (author['user_id'],))
            if author['user_id'] != current_user.id:
                conn.execute("INSERT INTO messages (sender_id, receiver_id, content, is_system, notif_type) VALUES (?, ?, ?, 1, 'like')",
                             (0, author['user_id'], f"❤️ {current_user.username} 赞了你的帖子《{author['title'][:20]}》"))
        return jsonify({'status': 'liked'})

@app.route('/api/posts/<int:post_id>/favorite', methods=['POST'])
@login_required
def toggle_favorite(post_id):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM favorites WHERE post_id = ? AND user_id = ?", (post_id, current_user.id)).fetchone()
        if existing:
            conn.execute("DELETE FROM favorites WHERE id = ?", (existing['id'],))
            return jsonify({'status': 'unfavorited'})
        conn.execute("INSERT INTO favorites (post_id, user_id) VALUES (?,?)", (post_id, current_user.id))
        return jsonify({'status': 'favorited'})

@app.route('/api/favorites')
@login_required
def get_favorites():
    with get_db() as conn:
        rows = conn.execute("""SELECT p.*, u.username FROM favorites f
                               JOIN posts p ON f.post_id = p.id
                               JOIN users u ON p.user_id = u.id
                               WHERE f.user_id = ? ORDER BY f.created_at DESC""", (current_user.id,)).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get('images'): d['thumb'] = '/uploads/' + d['images'].split(',')[0]
            result.append(d)
        return jsonify(result)

@app.route('/api/posts/<int:post_id>/comments', methods=['POST'])
@login_required
@rate_limit(20, 60)
def add_comment(post_id):
    with get_db() as conn:
        post = conn.execute("SELECT status, user_id, title FROM posts WHERE id = ?", (post_id,)).fetchone()
        if post and post['status'] != 'approved':
            return jsonify({'error': '该帖子未通过审核，暂不可评论'}), 403

    if current_user.comment_ban_until:
        try:
            if now_bj().replace(tzinfo=None) < datetime.datetime.strptime(current_user.comment_ban_until, '%Y-%m-%d %H:%M:%S'):
                return jsonify({'error': '您当前被禁评'}), 403
        except: pass

    data = request.get_json()
    content = (data.get('content') or '').strip()
    parent_id = data.get('parent_id')
    reply_to_user_id = data.get('reply_to_user_id')
    if not content: return jsonify({'error': '评论不能为空'}), 400
    if len(content) > 500: return jsonify({'error': '评论过长（最多500字）'}), 400
    for w in ['涉黄', '涉黑', '违法']:
        if w in content: return jsonify({'error': '评论包含敏感词'}), 400

    mentions = re.findall(r'@([A-Za-z0-9_\u4e00-\u9fa5]{2,20})', content)

    with get_db() as conn:
        cursor = conn.execute("INSERT INTO comments (post_id, user_id, content, parent_id, reply_to_user_id) VALUES (?,?,?,?,?)",
                              (post_id, current_user.id, content, parent_id, reply_to_user_id))
        conn.execute("UPDATE users SET exp = exp + 1 WHERE id = ?", (current_user.id,))
        new_id = cursor.lastrowid

        if post and post['user_id'] != current_user.id:
            conn.execute("INSERT INTO messages (sender_id, receiver_id, content, is_system, notif_type) VALUES (?, ?, ?, 1, 'comment')",
                         (0, post['user_id'], f"💬 {current_user.username} 评论了你的帖子"))

        if parent_id:
            parent = conn.execute("SELECT user_id FROM comments WHERE id = ?", (parent_id,)).fetchone()
            if parent and parent['user_id'] != current_user.id:
                conn.execute("INSERT INTO messages (sender_id, receiver_id, content, is_system, notif_type) VALUES (?, ?, ?, 1, 'reply')",
                             (0, parent['user_id'], f"↩️ {current_user.username} 回复了你的评论"))

        if reply_to_user_id and reply_to_user_id != current_user.id:
            if not parent_id or reply_to_user_id != parent['user_id']:
                conn.execute("INSERT INTO messages (sender_id, receiver_id, content, is_system, notif_type) VALUES (?, ?, ?, 1, 'reply')",
                             (0, reply_to_user_id, f"↩️ {current_user.username} 回复了你的评论"))

        for name in mentions:
            target = conn.execute("SELECT id FROM users WHERE username = ?", (name,)).fetchone()
            if target and target['id'] != current_user.id:
                conn.execute("INSERT INTO messages (sender_id, receiver_id, content, is_system, notif_type) VALUES (?, ?, ?, 1, 'mention')",
                             (0, target['id'], f"📢 {current_user.username} 在评论中提到了你"))

        row = conn.execute("""SELECT comments.*, users.username, users.credit_score, users.is_webmaster,
                              users.is_boss, users.is_alpha, users.is_beta, users.avatar, users.display_id
                              FROM comments LEFT JOIN users ON comments.user_id = users.id WHERE comments.id = ?""",
                           (new_id,)).fetchone()
        d = dict(row)
        credit = d.get('credit_score') or 0
        d['is_gold'] = credit >= 200 or d.get('is_webmaster') or d.get('is_boss') or d.get('is_alpha') or d.get('is_beta')
        d['like_count'] = 0
        d['liked'] = 0
    return jsonify(d), 201

@app.route('/api/comments/<int:comment_id>/like', methods=['POST'])
@login_required
def toggle_comment_like(comment_id):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM comment_likes WHERE comment_id = ? AND user_id = ?", (comment_id, current_user.id)).fetchone()
        if existing:
            conn.execute("DELETE FROM comment_likes WHERE id = ?", (existing['id'],))
            return jsonify({'status': 'unliked'})
        conn.execute("INSERT INTO comment_likes (comment_id, user_id) VALUES (?,?)", (comment_id, current_user.id))
        return jsonify({'status': 'liked'})

# ========== 搜索 / 关注 ==========
@app.route('/api/search_users')
def search_users():
    q = request.args.get('q', '').strip()
    if not q: return jsonify([])
    with get_db() as conn:
        rows = conn.execute("""SELECT id, username, credit_score, is_webmaster, is_boss, is_alpha, is_beta,
                               avatar, display_id, bio FROM users WHERE username LIKE ? LIMIT 20""",
                            ('%' + q + '%',)).fetchall()
        users = []
        for row in rows:
            d = dict(row)
            d['credit_score'] = d['credit_score'] or 120
            d['credit_level'] = get_credit_level(d['credit_score'])
            d['is_gold'] = d['credit_score'] >= 200 or d['is_webmaster'] or d['is_boss'] or d['is_alpha'] or d['is_beta']
            users.append(d)
    return jsonify(users)

@app.route('/api/follow/<int:user_id>', methods=['POST'])
@login_required
def toggle_follow(user_id):
    if user_id == current_user.id: return jsonify({'error': '不能关注自己'}), 400
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM follows WHERE follower_id = ? AND following_id = ?", (current_user.id, user_id)).fetchone()
        if existing:
            conn.execute("DELETE FROM follows WHERE id = ?", (existing['id'],))
            return jsonify({'status': 'unfollowed'})
        conn.execute("INSERT INTO follows (follower_id, following_id) VALUES (?, ?)", (current_user.id, user_id))
        conn.execute("INSERT INTO messages (sender_id, receiver_id, content, is_system, notif_type) VALUES (?, ?, ?, 1, 'follow')",
                     (0, user_id, f"👥 {current_user.username} 关注了你"))
        return jsonify({'status': 'followed'})

@app.route('/api/user/<int:user_id>/posts')
def get_user_posts(user_id):
    with get_db() as conn:
        rows = conn.execute("""SELECT p.*, u.username FROM posts p JOIN users u ON p.user_id = u.id
                               WHERE p.user_id = ? AND p.status = 'approved'
                               ORDER BY p.is_pinned DESC, p.id DESC""", (user_id,)).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if d.get('images'): d['thumb'] = '/uploads/' + d['images'].split(',')[0]
            result.append(d)
        return jsonify(result)

# ========== 私信 ==========
@app.route('/api/dm/conversations')
@login_required
def get_conversations():
    with get_db() as conn:
        rows = conn.execute("""SELECT DISTINCT CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END AS other_user_id
                               FROM messages WHERE sender_id = ? OR receiver_id = ?""",
                            (current_user.id, current_user.id, current_user.id)).fetchall()
        convs = []
        for row in rows:
            uid = row['other_user_id']
            if uid == 0: continue
            other = conn.execute("SELECT id, username, credit_score, avatar, display_id FROM users WHERE id = ?", (uid,)).fetchone()
            if not other: continue
            last = conn.execute("""SELECT content, created_at FROM messages WHERE
                                   (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
                                   ORDER BY created_at DESC LIMIT 1""",
                                (current_user.id, uid, uid, current_user.id)).fetchone()
            unread = conn.execute("SELECT COUNT(*) FROM messages WHERE receiver_id = ? AND sender_id = ? AND is_read = 0", (current_user.id, uid)).fetchone()[0]
            convs.append({
                'user_id': other['id'], 'username': other['username'],
                'credit_score': other['credit_score'] or 120,
                'avatar': other['avatar'], 'display_id': other['display_id'],
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
        conn.execute("UPDATE messages SET is_read = 1, read_at = ? WHERE receiver_id = ? AND sender_id = ? AND is_read = 0",
                     (now_bj().isoformat(), current_user.id, other_user_id))
        rows = conn.execute("""SELECT id, sender_id, receiver_id, content, created_at, is_read FROM messages
                               WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
                               ORDER BY created_at ASC LIMIT 200""",
                            (current_user.id, other_user_id, other_user_id, current_user.id)).fetchall()
        return jsonify([dict(row) for row in rows])

@app.route('/api/dm/send', methods=['POST'])
@login_required
@rate_limit(30, 60)
def send_dm():
    data = request.get_json()
    receiver_id = data.get('receiver_id')
    content = (data.get('content') or '').strip()
    if not receiver_id or not content: return jsonify({'error': '参数不完整'}), 400
    if receiver_id == current_user.id: return jsonify({'error': '不能给自己发私信'}), 400
    if current_user.dm_ban_until:
        try:
            if now_bj().replace(tzinfo=None) < datetime.datetime.strptime(current_user.dm_ban_until, '%Y-%m-%d %H:%M:%S'):
                return jsonify({'error': '您当前被禁私信'}), 403
        except: pass
    with get_db() as conn:
        receiver = conn.execute("SELECT id, credit_score FROM users WHERE id = ?", (receiver_id,)).fetchone()
        if not receiver: return jsonify({'error': '用户不存在'}), 404
        receiver_credit = receiver['credit_score'] or 120
        risk_warning = None
        for w in ['转账', '加微信', '私下交易', '汇款', '银行卡', 'V信', 'WX']:
            if w in content:
                risk_warning = '⚠️ 请注意保护个人信息，勿轻信陌生人的转账或交易请求'
                break
        if receiver_credit < 60:
            risk_warning = '⚠️ 对方信誉分较低，请谨慎对话'
        cursor = conn.execute("INSERT INTO messages (sender_id, receiver_id, content) VALUES (?,?,?)",
                              (current_user.id, receiver_id, content))
        new_msg = {'id': cursor.lastrowid, 'sender_id': current_user.id, 'receiver_id': receiver_id,
                   'content': content, 'created_at': now_bj().isoformat(), 'is_read': 0}
    return jsonify({'status': 'ok', 'message': new_msg, 'warning': risk_warning}), 201

@app.route('/api/dm/unread_count')
@login_required
def unread_dm_count():
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM messages WHERE receiver_id = ? AND is_read = 0", (current_user.id,)).fetchone()[0]
    return jsonify({'unread': count})

# ========== 通知 ==========
@app.route('/api/notifications/unread')
@login_required
def notif_unread():
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM messages WHERE receiver_id = ? AND is_system = 1 AND is_read = 0", (current_user.id,)).fetchone()[0]
    return jsonify({'unread': count})

@app.route('/api/notifications')
@login_required
def get_notifications():
    with get_db() as conn:
        rows = conn.execute("""SELECT * FROM messages WHERE receiver_id = ? AND is_system = 1
                               ORDER BY created_at DESC LIMIT 50""", (current_user.id,)).fetchall()
        return jsonify([dict(row) for row in rows])

# ========== 标签 ==========
@app.route('/api/tags')
def get_tags():
    with get_db() as conn:
        rows = conn.execute("""SELECT tag, COUNT(*) as count FROM posts
                               WHERE tag IS NOT NULL AND tag != ''
                               GROUP BY tag ORDER BY count DESC""").fetchall()
        return jsonify([dict(r) for r in rows])

# ========== 评级卡片 ==========
@app.route('/api/coin/<cert_number>')
def get_coin(cert_number):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM coin_ratings WHERE cert_number = ?", (cert_number,)).fetchone()
        if not row: return jsonify({'error': '未找到该编号'}), 404
        return jsonify(dict(row))

# ========== 用户设置 ==========
@app.route('/api/user/avatar', methods=['POST'])
@login_required
def upload_avatar():
    file = request.files.get('avatar')
    if not file or not file.filename:
        return jsonify({'error': '未选择图片'}), 400
    parts = file.filename.rsplit('.', 1)
    if len(parts) < 2:
        return jsonify({'error': '文件缺少扩展名'}), 400
    ext = parts[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'不支持的图片格式：.{ext}'}), 400
    try:
        img = Image.open(file.stream)
        if img.mode in ('RGBA', 'LA', 'P'):
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
    ip = (request.headers.get('X-Forwarded-For', request.remote_addr) or '').split(',')[0].strip()
    loc = get_ip_location(ip)
    with get_db() as conn:
        conn.execute("UPDATE users SET location = ? WHERE id = ?", (loc, current_user.id))
    return jsonify({'status': 'ok', 'location': loc})

@app.route('/api/user/bio', methods=['POST'])
@login_required
def update_bio():
    data = request.get_json()
    bio = (data.get('bio') or '').strip()
    if len(bio) > 200:
        return jsonify({'error': '简介最多200字'}), 400
    with get_db() as conn:
        conn.execute("UPDATE users SET bio = ? WHERE id = ?",
                     (bio or '这个人很懒，什么都没写。', current_user.id))
    return jsonify({'status': 'ok'})

@app.route('/api/user/email', methods=['POST'])
@login_required
def bind_email():
    data = request.get_json()
    email = data.get('email', '').strip()
    if not is_valid_email(email):
        return jsonify({'error': '邮箱格式不正确'}), 400
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM users WHERE email = ? AND id != ?",
                                (email, current_user.id)).fetchone()
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
        existing = conn.execute("SELECT id FROM users WHERE phone = ? AND id != ?",
                                (phone, current_user.id)).fetchone()
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

# ========== 成就 ==========
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
    achievements = current_user.earned_achievements or []
    if name in achievements:
        return jsonify({'error': '该成就已获得'}), 400
    if name in ['站长', '老大！！！']:
        with get_db() as conn:
            existing = conn.execute(
                "SELECT u.username FROM user_achievements ua "
                "JOIN users u ON ua.user_id = u.id "
                "WHERE ua.achievement_id = (SELECT id FROM achievements WHERE name = ?) "
                "AND ua.user_id != ?", (name, current_user.id)).fetchone()
            if existing:
                return jsonify({'error': f'该成就已被 {existing["username"]} 获得'}), 400
    achievements.append(name)
    with get_db() as conn:
        conn.execute("UPDATE users SET earned_achievements = ?, credit_score = credit_score + ? WHERE id = ?",
                     (json.dumps(achievements), points, current_user.id))
        if flag == 'admin_level':
            target_level = 3 if name == '高级管理员' else 1
            conn.execute("UPDATE users SET admin_level = MAX(COALESCE(admin_level, 0), ?) WHERE id = ?",
                         (target_level, current_user.id))
        elif flag.startswith('is_'):
            conn.execute(f"UPDATE users SET {flag} = 1 WHERE id = ?", (current_user.id,))
        else:
            conn.execute(f"UPDATE users SET {flag} = COALESCE({flag}, 0) + 1 WHERE id = ?", (current_user.id,))
        ach_id = conn.execute("SELECT id FROM achievements WHERE name = ?", (name,)).fetchone()
        if ach_id:
            conn.execute("INSERT OR IGNORE INTO user_achievements (user_id, achievement_id) VALUES (?, ?)",
                         (current_user.id, ach_id['id']))
    return jsonify({'status': 'ok', 'message': f'🎉 获得成就：{name}！成长值 +{points}'})

@app.route('/api/achievements')
@login_required
def get_achievements():
    with get_db() as conn:
        all_achs = conn.execute("SELECT id, name, description, icon, points FROM achievements ORDER BY id").fetchall()
        unlocked = conn.execute("SELECT achievement_id FROM user_achievements WHERE user_id = ?",
                                (current_user.id,)).fetchall()
        unlocked_ids = [row['achievement_id'] for row in unlocked]
        result = []
        for a in all_achs:
            result.append({
                'id': a['id'], 'name': a['name'], 'description': a['description'],
                'icon': a['icon'], 'points': a['points'],
                'unlocked': a['id'] in unlocked_ids
            })
    return jsonify(result)

@app.route('/api/level_center')
@login_required
def level_center():
    with get_db() as conn:
        row = conn.execute("SELECT exp, credit_score FROM users WHERE id = ?", (current_user.id,)).fetchone()
        if not row:
            return jsonify({'error': '用户不存在'}), 404
        exp = row['exp'] or 0
        credit = row['credit_score'] or 120
        levels = [0, 20, 50, 100, 150, 200]
        level = 1
        for i, lv in enumerate(levels, 1):
            if exp >= lv: level = i
        # 门槛：LV6 仅管理员/站长/Boss 可达
        is_admin = (current_user.admin_level or 0) >= 1 or current_user.is_webmaster or current_user.is_boss
        if level >= 6 and not is_admin:
            level = 5
        names = ['见习生', '初级鉴定师', '资深鉴定师', '铜牌评级师', '银牌评级师', '金牌评级师']
        name = names[level - 1]
        if level == 6:
            name = '⚡ 金牌评级师 · LV6'
        next_exp = 200 if exp >= 200 else min([l for l in levels if l > exp], default=200)
        return jsonify({'level': level, 'name': name, 'exp': exp, 'next_level_exp': next_exp,
                        'credit_score': credit, 'is_admin_unlocked': is_admin})

@app.route('/api/daily_bonus', methods=['POST'])
@login_required
def daily_bonus():
    today = datetime.date.today().isoformat()
    with get_db() as conn:
        row = conn.execute("SELECT last_login_date FROM users WHERE id = ?", (current_user.id,)).fetchone()
        if row and row['last_login_date'] == today:
            return jsonify({'error': '今日已签到'}), 400
        conn.execute("UPDATE users SET exp = exp + 3, login_days = login_days + 1, last_login_date = ? WHERE id = ?",
                     (today, current_user.id))
    return jsonify({'status': 'ok', 'message': '✅ 签到成功！+3 鉴定积分'}), 200

@app.route('/api/checkin_calendar')
@login_required
def checkin_calendar():
    now = now_bj()
    year, month = now.year, now.month
    first_day = datetime.date(year, month, 1)
    weekday = first_day.weekday()
    if month == 12:
        next_month = datetime.date(year + 1, 1, 1)
    else:
        next_month = datetime.date(year, month + 1, 1)
    days_in_month = (next_month - first_day).days

    with get_db() as conn:
        rows = conn.execute(
            "SELECT checkin_date FROM checkins WHERE user_id = ? AND checkin_date LIKE ?",
            (current_user.id, f"{year}-{month:02d}%")).fetchall()
        checked_days = [int(r['checkin_date'].split('-')[2]) for r in rows]

    return jsonify({
        'year': year, 'month': month,
        'days_in_month': days_in_month,
        'first_weekday': weekday,
        'checked_days': checked_days
    })

@app.route('/api/checkin_today', methods=['POST'])
@login_required
def checkin_today():
    today = datetime.date.today().isoformat()
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM checkins WHERE user_id = ? AND checkin_date = ?",
                                (current_user.id, today)).fetchone()
        if existing:
            return jsonify({'error': '今日已签到'}), 400
        conn.execute("INSERT INTO checkins (user_id, checkin_date) VALUES (?, ?)", (current_user.id, today))
        conn.execute("UPDATE users SET exp = exp + 3, login_days = login_days + 1 WHERE id = ?", (current_user.id,))
        conn.commit()
    return jsonify({'status': 'ok', 'message': '✅ 签到成功！+3 鉴定积分'})

# ========== 举报 ==========
@app.route('/api/report', methods=['POST'])
@login_required
@rate_limit(10, 60)
def submit_report():
    data = request.get_json()
    target_type = data.get('target_type')
    target_id = data.get('target_id')
    reason = data.get('reason', '').strip()
    if not target_type or not target_id or not reason:
        return jsonify({'error': '参数不完整'}), 400
    with get_db() as conn:
        conn.execute("INSERT INTO reports (reporter_id, target_type, target_id, reason) VALUES (?,?,?,?)",
                     (current_user.id, target_type, target_id, reason))
    return jsonify({'status': 'ok', 'message': '举报已提交'})

# ========== 管理员路由 ==========
@app.route('/api/admin/version', methods=['POST'])
@login_required
@owner_required
def set_version():
    data = request.get_json() or {}
    new_version = (data.get('version') or '').strip()
    if not new_version: return jsonify({'error': '版本号不能为空'}), 400
    if len(new_version) > 60: return jsonify({'error': '版本号过长（最多60字符）'}), 400
    with get_db() as conn:
        conn.execute("UPDATE settings SET value = ? WHERE key = 'app_version'", (new_version,))
        conn.execute("INSERT INTO admin_logs (admin_id, admin_name, action, detail) VALUES (?, ?, 'update_version', ?)",
                     (current_user.id, current_user.username, json.dumps({'new_version': new_version})))
        conn.commit()
    return jsonify({'status': 'ok', 'version': new_version})

@app.route('/api/admin/beta_toggle', methods=['POST'])
@login_required
@owner_required
def beta_toggle():
    """开关 Beta 环境（仅站长）"""
    data = request.get_json() or {}
    enabled = '1' if data.get('enabled') else '0'
    with sqlite3.connect(MAIN_DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('beta_enabled', ?)", (enabled,))
        conn.commit()
    with sqlite3.connect(MAIN_DB_PATH) as conn:
        conn.execute("""INSERT INTO admin_logs (admin_id, admin_name, action, detail)
                        VALUES (?, ?, 'beta_toggle', ?)""",
                     (current_user.id, current_user.username,
                      json.dumps({'enabled': enabled == '1'})))
        conn.commit()
    return jsonify({'status': 'ok', 'beta_enabled': enabled == '1'})

@app.route('/api/admin/beta_status', methods=['GET'])
@login_required
@owner_required
def beta_status():
    """查询 Beta 开关状态"""
    return jsonify({'beta_enabled': get_beta_enabled()})

@app.route('/api/admin/delete_post', methods=['POST'])
@login_required
@admin_required()
def admin_delete_post():
    data = request.get_json()
    post_id = data.get('post_id')
    if not post_id: return jsonify({'error': '缺少帖子ID'}), 400
    with get_db() as conn:
        conn.execute("DELETE FROM comments WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM likes WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM favorites WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.execute("INSERT INTO admin_logs (admin_id, admin_name, action, target_type, target_id) VALUES (?, ?, 'delete_post', 'post', ?)",
                     (current_user.id, current_user.username, post_id))
    return jsonify({'status': 'ok'})

@app.route('/api/admin/delete_comment', methods=['POST'])
@login_required
@admin_required()
def admin_delete_comment():
    data = request.get_json()
    comment_id = data.get('comment_id')
    if not comment_id: return jsonify({'error': '缺少评论ID'}), 400
    with get_db() as conn:
        conn.execute("DELETE FROM comments WHERE id = ?", (comment_id,))
        conn.execute("INSERT INTO admin_logs (admin_id, admin_name, action, target_type, target_id) VALUES (?, ?, 'delete_comment', 'comment', ?)",
                     (current_user.id, current_user.username, comment_id))
    return jsonify({'status': 'ok'})

@app.route('/api/admin/pin_post/<int:post_id>', methods=['POST'])
@login_required
@admin_required()
def pin_post(post_id):
    data = request.get_json() or {}
    pin = 1 if data.get('pin', True) else 0
    with get_db() as conn:
        if pin:
            conn.execute("UPDATE posts SET is_pinned = 1, pinned_at = ? WHERE id = ?", (now_bj().isoformat(), post_id))
        else:
            conn.execute("UPDATE posts SET is_pinned = 0, pinned_at = NULL WHERE id = ?", (post_id,))
        conn.execute("INSERT INTO admin_logs (admin_id, admin_name, action, target_type, target_id, detail) VALUES (?, ?, ?, 'post', ?, ?)",
                     (current_user.id, current_user.username, 'pin_post' if pin else 'unpin_post', post_id, json.dumps({'pin': pin})))
        conn.commit()
    return jsonify({'status': 'ok', 'pinned': bool(pin)})

@app.route('/api/admin/reports', methods=['GET'])
@login_required
@admin_required()
def get_reports():
    with get_db() as conn:
        rows = conn.execute("""SELECT r.*, u.username as reporter_name FROM reports r
                               JOIN users u ON r.reporter_id = u.id
                               WHERE r.status = 'pending' ORDER BY r.created_at DESC""").fetchall()
        return jsonify([dict(row) for row in rows])

@app.route('/api/admin/reports/<int:report_id>', methods=['POST'])
@login_required
@admin_required()
def handle_report(report_id):
    data = request.get_json()
    action = data.get('action')
    with get_db() as conn:
        conn.execute("UPDATE reports SET status = ?, reviewed_by = ? WHERE id = ?",
                     ('approved' if action == 'approve' else 'rejected', current_user.id, report_id))
    return jsonify({'status': 'ok'})

@app.route('/api/admin/pending_posts', methods=['GET'])
@login_required
@admin_required()
def get_pending_posts():
    with get_db() as conn:
        rows = conn.execute("""SELECT p.*, u.username FROM posts p JOIN users u ON p.user_id = u.id
                               WHERE p.status = 'pending' ORDER BY p.created_at ASC""").fetchall()
        return jsonify([dict(row) for row in rows])

@app.route('/api/admin/approve_post/<int:post_id>', methods=['POST'])
@login_required
@admin_required()
def approve_post(post_id):
    with get_db() as conn:
        conn.execute("UPDATE posts SET status = 'approved' WHERE id = ?", (post_id,))
        p = conn.execute("SELECT user_id, title FROM posts WHERE id = ?", (post_id,)).fetchone()
        if p:
            conn.execute("INSERT INTO messages (sender_id, receiver_id, content, is_system, notif_type) VALUES (?, ?, ?, 1, 'approved')",
                         (0, p['user_id'], f"✅ 你的帖子《{p['title'][:20]}》已通过审核"))
    return jsonify({'status': 'ok'})

@app.route('/api/admin/reject_post/<int:post_id>', methods=['POST'])
@login_required
@admin_required()
def reject_post(post_id):
    data = request.get_json()
    reason = data.get('reason', '无')
    with get_db() as conn:
        conn.execute("UPDATE posts SET status = 'rejected', reject_reason = ? WHERE id = ?", (reason, post_id))
        p = conn.execute("SELECT user_id, title FROM posts WHERE id = ?", (post_id,)).fetchone()
        if p:
            conn.execute("INSERT INTO messages (sender_id, receiver_id, content, is_system, notif_type) VALUES (?, ?, ?, 1, 'rejected')",
                         (0, p['user_id'], f"❌ 你的帖子《{p['title'][:20]}》未通过审核：{reason}"))
    return jsonify({'status': 'ok'})

@app.route('/api/admin/security_status', methods=['GET'])
@login_required
@admin_required()
def get_security_status():
    locks = {}
    if current_user.freeze_until:
        try:
            active = now_bj().replace(tzinfo=None) < datetime.datetime.fromisoformat(current_user.freeze_until)
            locks = {
                'warnlocker': active and current_user.freeze_level == 'warnlocker',
                'xzlocker_s': active and current_user.freeze_level == 'XZlocker-s',
                'icelocker': active and current_user.freeze_level == 'Icelocker',
                'xzlocker': active and current_user.freeze_level == 'XZlocker',
                'windlocker': active and current_user.freeze_level == 'windlocker',
            }
        except: pass
    if not locks:
        locks = {'warnlocker': False, 'xzlocker_s': False, 'icelocker': False, 'xzlocker': False, 'windlocker': False}
    return jsonify({'locks': locks, 'sukey': None, 'oem': {'oem': False, 'oem-small': False, 'oem+': False}})

@app.route('/api/admin/logs', methods=['GET'])
@login_required
@admin_required(2)
def get_admin_logs():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM admin_logs ORDER BY created_at DESC LIMIT 100").fetchall()
        return jsonify([dict(row) for row in rows])

@app.route('/api/admin/toggle_oem', methods=['POST'])
@login_required
@owner_required
def toggle_oem():
    data = request.get_json()
    return jsonify({'status': 'ok', 'message': f'OEM {data.get("type")} {"启用" if data.get("enabled") else "禁用"}'})

@app.route('/api/admin/coin', methods=['POST'])
@login_required
@admin_required()
def add_coin():
    data = request.get_json() or {}
    cert_number = (data.get('cert_number') or '').strip()
    name = (data.get('name') or '').strip()
    if not cert_number or not name: return jsonify({'error': '编号和名称必填'}), 400
    with get_db() as conn:
        try:
            conn.execute("""INSERT INTO coin_ratings
                (cert_number, name, grade, era, variety, size, weight, comment,
                 front_image, back_image, guarantee_amount, manager, extra_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '小泽', ?)""",
                (cert_number, name, data.get('grade'), data.get('era'), data.get('variety'),
                 data.get('size'), data.get('weight'), data.get('comment'),
                 data.get('front_image'), data.get('back_image'),
                 data.get('guarantee_amount'), data.get('extra_info') or None))
            conn.commit()
        except sqlite3.IntegrityError:
            return jsonify({'error': '编号已存在'}), 400
    return jsonify({'status': 'ok'})

# ========== 激活码 ==========
ACTIVATION_PREFIX_MAP = {
    'Admin': {'field': 'admin_level', 'value': 1},
    'Senior': {'field': 'admin_level', 'value': 3},
    'Webmaster': {'field': 'is_webmaster', 'value': 1},
    'Boss': {'field': 'is_boss', 'value': 1},
    'Alpha': {'field': 'is_alpha', 'value': 1},
    'Beta': {'field': 'is_beta', 'value': 1},
}

def verify_activation_code(code, expected_prefix=None):
    match = re.match(r'^([A-Za-z]+)-([A-Za-z0-9\-]+)-(\d{6})$', code)
    if not match: return False, "格式错误（正确格式：前缀-EUID-YYMMDD）", None, None
    prefix, euid, yymmdd = match.groups()
    if expected_prefix and prefix != expected_prefix:
        return False, f"前缀错误（应为 {expected_prefix}）", None, None
    with get_db() as conn:
        user = conn.execute("SELECT id, username FROM users WHERE display_id = ?", (euid,)).fetchone()
        if not user: return False, "该激活码EUID错误", None, None
    today = now_bj().strftime('%y%m%d')
    if yymmdd != today: return False, "该激活码时间戳错误（仅当日有效）", None, None
    return True, "验证通过", euid, prefix

@app.route('/api/admin/unlock_by_code', methods=['POST'])
@login_required
@owner_required
def unlock_by_code():
    data = request.get_json()
    code = (data.get('code') or '').strip()
    prefix = (data.get('type') or '').strip()
    if not code: return jsonify({'error': '请输入激活码'}), 400
    if prefix:
        valid, msg, euid, _ = verify_activation_code(code, prefix)
    else:
        valid, msg, euid, extracted_prefix = verify_activation_code(code)
        if not valid: return jsonify({'error': msg}), 400
        prefix = extracted_prefix
    if not valid: return jsonify({'error': msg}), 400
    if prefix not in ACTIVATION_PREFIX_MAP: return jsonify({'error': '无效的前缀'}), 400
    with get_db() as conn:
        target = conn.execute("SELECT * FROM users WHERE display_id = ?", (euid,)).fetchone()
        if not target: return jsonify({'error': '该激活码EUID错误'}), 404
        config = ACTIVATION_PREFIX_MAP[prefix]
        field = config['field']
        if field == 'admin_level':
            if (target['admin_level'] or 0) >= config['value']:
                return jsonify({'error': f'该用户已是 {prefix}'}), 400
            conn.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (config['value'], target['id']))
        else:
            if target[field] == 1: return jsonify({'error': f'该用户已是 {prefix}'}), 400
            conn.execute(f"UPDATE users SET {field} = 1 WHERE id = ?", (target['id'],))
        conn.execute("INSERT INTO admin_logs (admin_id, admin_name, action, detail) VALUES (?, ?, 'activate_code', ?)",
                     (current_user.id, current_user.username, json.dumps({'prefix': prefix, 'target_euid': euid, 'target_username': target['username']})))
        conn.commit()
    return jsonify({'status': 'ok', 'message': f'✅ 已成功为 {target["username"]} 激活 {prefix}'})

# ========== SU / 审计 ==========
_su_tokens = {}

@app.route('/api/admin/su_prepare', methods=['POST'])
@login_required
@owner_required
def su_prepare():
    sukey = secrets.token_hex(6)
    _su_tokens[current_user.id] = {'token': sukey, 'expires': now_bj() + datetime.timedelta(minutes=5)}
    return jsonify({'sukey': sukey, 'expires_in': 300})

@app.route('/api/admin/su', methods=['POST'])
@login_required
@owner_required
def admin_su():
    if current_user.freeze_level and current_user.freeze_until:
        try:
            if now_bj().replace(tzinfo=None) < datetime.datetime.fromisoformat(current_user.freeze_until):
                return jsonify({'error': f'账户已被冻结（{current_user.freeze_level}）'}), 403
        except: pass

    data = request.get_json()
    target_euid = (data.get('target_euid') or '').strip()
    admin_euid = (data.get('admin_euid') or '').strip()
    sukey_input = (data.get('sukey') or '').strip()
    if not target_euid or not admin_euid or not sukey_input:
        return jsonify({'error': '参数不能为空'}), 400
    if admin_euid != current_user.display_id: return jsonify({'error': '你的EUID输入有误'}), 403
    token_record = _su_tokens.get(current_user.id)
    if not token_record or token_record['expires'] < now_bj():
        return jsonify({'error': 'SUkey已过期或未生成'}), 403
    if token_record['token'] != sukey_input: return jsonify({'error': 'SUkey错误'}), 403
    del _su_tokens[current_user.id]

    with get_db() as conn:
        target = conn.execute("SELECT * FROM users WHERE display_id = ?", (target_euid,)).fetchone()
        if not target: return jsonify({'error': '目标用户不存在'}), 404
        if (target['admin_level'] or 0) >= 10: return jsonify({'error': '目标账号为站长，不可模拟登录'}), 403

        conn.execute("INSERT INTO admin_logs (admin_id, admin_name, action, target_type, target_id, detail) VALUES (?, ?, 'admin_su', 'user', ?, ?)",
                     (current_user.id, current_user.username, target['id'],
                      json.dumps({'target_username': target['username']})))
        session['_su_original_user_id'] = current_user.id
        conn.commit()
        login_user(User(target), remember=False, duration=datetime.timedelta(minutes=30))

    return jsonify({'status': 'ok', 'message': f'已切换到用户 {target["username"]}',
                    'user': {'id': target['id'], 'username': target['username'],
                             'display_id': target['display_id'] or '',
                             'admin_level': target.get('admin_level', 0)}})

@app.route('/api/admin/audit', methods=['POST'])
@login_required
@owner_required
def admin_audit():
    data = request.get_json()
    euid = (data.get('euid') or '').strip()
    if not euid: return jsonify({'error': '请输入目标用户的 EUID'}), 400
    with get_db() as conn:
        target = conn.execute("SELECT id, username FROM users WHERE display_id = ?", (euid,)).fetchone()
        if not target: return jsonify({'error': '用户不存在'}), 404
        user_id = target['id']
        posts = conn.execute("SELECT id, title, tag, status, created_at FROM posts WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        comments = conn.execute("SELECT id, post_id, created_at FROM comments WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        messages = conn.execute("SELECT id, sender_id, receiver_id, created_at FROM messages WHERE sender_id = ? OR receiver_id = ? ORDER BY created_at DESC", (user_id, user_id)).fetchall()
        likes = conn.execute("SELECT id, post_id, created_at FROM likes WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
        conn.execute("INSERT INTO admin_logs (admin_id, admin_name, action, target_type, target_id, detail) VALUES (?, ?, 'admin_audit', 'user', ?, ?)",
                     (current_user.id, current_user.username, target['id'], json.dumps({'target_username': target['username']})))
        conn.commit()
    return jsonify({'status': 'ok', 'target_user': target['username'], 'target_euid': euid,
                    'posts': [dict(p) for p in posts], 'comments': [dict(c) for c in comments],
                    'messages': [dict(m) for m in messages], 'likes': [dict(l) for l in likes],
                    'summary': {'post_count': len(posts), 'comment_count': len(comments),
                                'message_count': len(messages), 'like_count': len(likes)}})

# ========== 系统消息 ==========
@app.route('/api/system_messages')
@login_required
def get_system_messages():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM messages WHERE receiver_id = ? AND is_system = 1 ORDER BY created_at DESC LIMIT 50", (current_user.id,)).fetchall()
        return jsonify([dict(row) for row in rows])


@app.route('/manifest.json')
def pwa_manifest():
    resp = send_from_directory('static', 'manifest.json', mimetype='application/manifest+json')
    resp.headers['Cache-Control'] = 'public, max-age=86400'
    return resp

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ========== 全局异常日志（调试用） ==========
@app.errorhandler(Exception)
def handle_all_exceptions(e):
    import traceback
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return e
    print("\n========== [APP ERROR] ==========")
    print("Host:", request.host)
    print("Path:", request.path)
    print(traceback.format_exc())
    print("=================================\n")
    return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
