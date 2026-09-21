# security.py — 樟嘉评级安全模块
import os
import time
import threading
import datetime
from functools import wraps
from flask import jsonify, request
from flask_login import current_user


def init_session_security(app):
    secure = os.environ.get('SECURE_COOKIES', '1') == '1'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['SESSION_COOKIE_SECURE'] = secure
    app.config['SESSION_COOKIE_NAME'] = 'zj_session'
    app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(hours=24)
    print(f"[security] Session 安全已启用（Secure={secure}）")


def init_security_headers(app):
    @app.after_request
    def set_security_headers(response):
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        if request.is_secure or request.headers.get('X-Forwarded-Proto') == 'https':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response
    print("[security] 安全响应头已启用")


SCANNER_UA = [
    'sqlmap', 'nikto', 'nmap', 'masscan', 'acunetix',
    'nessus', 'openvas', 'w3af', 'zgrab', 'gobuster',
    'dirbuster', 'wpscan', 'nuclei', 'xray', 'hydra',
]


def init_ua_filter(app):
    @app.before_request
    def check_ua():
        ua = (request.headers.get('User-Agent') or '').lower()
        if not ua:
            return jsonify({'error': 'Bad Request'}), 400
        for scanner in SCANNER_UA:
            if scanner in ua:
                print(f"[security] 拦截扫描器 UA: {ua[:60]}")
                return jsonify({'error': 'Forbidden'}), 403
    print("[security] UA 过滤已启用")


def admin_required(min_level=1):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'error': '未登录'}), 401
            level = current_user.admin_level or 0
            if level < min_level:
                return jsonify({'error': '权限不足'}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator


def owner_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return jsonify({'error': '未登录'}), 401
        is_owner = (
            current_user.is_webmaster
            or (current_user.admin_level or 0) >= 10
            or getattr(current_user, 'is_owner', 0)
        )
        if not is_owner:
            return jsonify({'error': '仅站长可操作'}), 403
        return f(*args, **kwargs)
    return wrapped


_rate_buckets = {}
_rate_lock = threading.Lock()


def rate_limit(max_requests=5, window_seconds=60, key='ip'):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if key == 'user' and current_user.is_authenticated:
                k = f"user:{current_user.id}"
            else:
                ip = request.headers.get('X-Forwarded-For', request.remote_addr) or ''
                ip = ip.split(',')[0].strip()
                k = f"ip:{ip}"
            k = f"{f.__name__}:{k}"
            now = time.time()
            with _rate_lock:
                bucket = _rate_buckets.get(k, [])
                bucket = [t for t in bucket if t > now - window_seconds]
                if len(bucket) >= max_requests:
                    retry_after = int(bucket[0] + window_seconds - now) + 1
                    return jsonify({'error': f'请求过于频繁，请 {retry_after} 秒后再试'}), 429, {'Retry-After': str(retry_after)}
                bucket.append(now)
                _rate_buckets[k] = bucket
            return f(*args, **kwargs)
        return wrapped
    return decorator


def init_all_security(app):
    init_session_security(app)
    init_security_headers(app)
    init_ua_filter(app)
    print("[security] 全部安全模块初始化完成")
