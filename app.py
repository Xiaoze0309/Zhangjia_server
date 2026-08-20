from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
import os
import datetime
from werkzeug.utils import secure_filename
from PIL import Image
import io
import re
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
class User(UserMixin):
    def __init__(self, id, username, password_hash, email):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.email = email
@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if row:
        return User(row['id'], row['username'], row['password_hash'], row['email'])
    return None
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn
def init_db():
    with get_db() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT UNIQUE NOT NULL,
                      password_hash TEXT NOT NULL,
                      email TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS posts
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id INTEGER NOT NULL,
                      title TEXT NOT NULL,
                      content TEXT,
                      images TEXT,
                      tag TEXT,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (user_id) REFERENCES users (id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS likes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      post_id INTEGER NOT NULL,
                      user_id INTEGER NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      UNIQUE(post_id, user_id),
                      FOREIGN KEY (post_id) REFERENCES posts (id),
                      FOREIGN KEY (user_id) REFERENCES users (id))''')
        conn.execute('''CREATE TABLE IF NOT EXISTS comments
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      post_id INTEGER NOT NULL,
                      user_id INTEGER NOT NULL,
                      content TEXT NOT NULL,
                      created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                      FOREIGN KEY (post_id) REFERENCES posts (id),
                      FOREIGN KEY (user_id) REFERENCES users (id))''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_posts_user ON posts(user_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_posts_tag ON posts(tag)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_likes_post ON likes(post_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id)')
init_db()
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
def compress_image(file, max_size=800, quality=75):
    img = Image.open(file.stream)
    if img.mode in ('RGBA', 'LA'):
        img = img.convert('RGB')
    img.thumbnail((max_size, max_size))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=quality, optimize=True)
    buf.seek(0)
    return buf
def hash_password(password):
    return generate_password_hash(password)
def check_password(password, hashed):
    return check_password_hash(hashed, password)
def is_valid_email(email):
    return re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email) is not None
@app.route('/')
def index():
    return render_template('index.html')
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    email = data.get('email', '').strip()
    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400
    if len(username) < 3:
        return jsonify({'error': '用户名至少3个字符'}), 400
    if len(password) < 4:
        return jsonify({'error': '密码至少4个字符'}), 400
    if email and not is_valid_email(email):
        return jsonify({'error': '邮箱格式不正确'}), 400
    hashed = hash_password(password)
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)", (username, hashed, email if email else None))
        return jsonify({'status': 'ok', 'message': '注册成功'}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': '用户名已存在'}), 400
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    if not username or not password:
        return jsonify({'error': '请输入用户名和密码'}), 400
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row or not check_password(password, row['password_hash']):
            return jsonify({'error': '用户名或密码错误'}), 401
        user = User(row['id'], row['username'], row['password_hash'], row['email'])
        login_user(user, remember=True, duration=datetime.timedelta(days=30))
        return jsonify({'status': 'ok', 'user': {'id': row['id'], 'username': row['username'], 'email': row['email']}})
@app.route('/api/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return jsonify({'status': 'ok'})
@app.route('/api/me')
def me():
    if current_user.is_authenticated:
        return jsonify({'id': current_user.id, 'username': current_user.username, 'email': current_user.email})
    return jsonify({'error': '未登录'}), 401
@app.route('/api/posts')
def get_posts():
    search = request.args.get('search', '').strip()
    tag = request.args.get('tag', '').strip()
    user_id = request.args.get('user_id', '')
    sql = "SELECT posts.*, users.username FROM posts LEFT JOIN users ON posts.user_id = users.id WHERE 1=1"
    params = []
    if search:
        sql += " AND (posts.title LIKE ? OR posts.content LIKE ? OR posts.tag LIKE ?)"
        like = '%' + search + '%'
        params.extend([like, like, like])
    if tag:
        sql += " AND posts.tag LIKE ?"
        params.append('%' + tag + '%')
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
    return jsonify(posts)
@app.route('/api/posts', methods=['POST'])
@login_required
def add_post():
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    tag = request.form.get('tag', '').strip()
    if not title:
        return jsonify({'error': '标题不能为空'}), 400
    if not tag:
        return jsonify({'error': '请选择分类'}), 400
    with get_db() as conn:
        recent = conn.execute("SELECT id FROM posts WHERE user_id=? AND title=? AND created_at > datetime('now', '-5 seconds')", (current_user.id, title)).fetchone()
        if recent:
            return jsonify({'error': '请勿重复提交'}), 429
    files = request.files.getlist('images')
    saved_names = []
    for f in files:
        if f and allowed_file(f.filename):
            ext = f.filename.rsplit('.', 1)[1].lower()
            new_name = f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(f.filename)}"
            compressed = compress_image(f)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_name)
            with open(filepath, 'wb') as out:
                out.write(compressed.read())
            saved_names.append(new_name)
    images_str = ','.join(saved_names) if saved_names else None
    with get_db() as conn:
        conn.execute("INSERT INTO posts (user_id, title, content, images, tag) VALUES (?, ?, ?, ?, ?)", (current_user.id, title, content, images_str, tag))
    return jsonify({'status': 'ok'}), 201
@app.route('/api/posts/<int:post_id>')
def get_post(post_id):
    with get_db() as conn:
        post = conn.execute("SELECT posts.*, users.username FROM posts LEFT JOIN users ON posts.user_id = users.id WHERE posts.id = ?", (post_id,)).fetchone()
        if not post:
            return jsonify({'error': '帖子不存在'}), 404
        p = dict(post)
        p['like_count'] = conn.execute("SELECT COUNT(*) FROM likes WHERE post_id = ?", (post_id,)).fetchone()[0]
        p['comment_count'] = conn.execute("SELECT COUNT(*) FROM comments WHERE post_id = ?", (post_id,)).fetchone()[0]
        if current_user.is_authenticated:
            liked = conn.execute("SELECT id FROM likes WHERE post_id = ? AND user_id = ?", (post_id, current_user.id)).fetchone()
            p['liked'] = 1 if liked else 0
        else:
            p['liked'] = 0
        comments = conn.execute("SELECT comments.*, users.username FROM comments LEFT JOIN users ON comments.user_id = users.id WHERE post_id = ? ORDER BY comments.id ASC", (post_id,)).fetchall()
        p['comments'] = [dict(c) for c in comments]
    return jsonify(p)
@app.route('/api/posts/<int:post_id>/like', methods=['POST'])
@login_required
def toggle_like(post_id):
    with get_db() as conn:
        existing = conn.execute("SELECT id FROM likes WHERE post_id = ? AND user_id = ?", (post_id, current_user.id)).fetchone()
        if existing:
            conn.execute("DELETE FROM likes WHERE id = ?", (existing['id'],))
            return jsonify({'status': 'unliked'})
        else:
            conn.execute("INSERT INTO likes (post_id, user_id) VALUES (?, ?)", (post_id, current_user.id))
            return jsonify({'status': 'liked'})
@app.route('/api/posts/<int:post_id>/comments', methods=['POST'])
@login_required
def add_comment(post_id):
    data = request.get_json()
    content = data.get('content', '').strip()
    if not content:
        return jsonify({'error': '评论不能为空'}), 400
    with get_db() as conn:
        conn.execute("INSERT INTO comments (post_id, user_id, content) VALUES (?, ?, ?)", (post_id, current_user.id, content))
        new_id = conn.lastrowid
        row = conn.execute("SELECT comments.*, users.username FROM comments LEFT JOIN users ON comments.user_id = users.id WHERE comments.id = ?", (new_id,)).fetchone()
    return jsonify(dict(row)), 201
@app.route('/api/tags')
def get_tags():
    with get_db() as conn:
        rows = conn.execute("SELECT tag, COUNT(*) as count FROM posts WHERE tag IS NOT NULL AND tag != '' GROUP BY tag ORDER BY count DESC").fetchall()
        return jsonify([dict(r) for r in rows])
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

