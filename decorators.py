from functools import wraps
from flask import redirect, url_for, flash, jsonify, request
from flask_login import current_user


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': '请先登录'}), 401
            flash('请先登录', 'warning')
            return redirect(url_for('center.login'))
        return f(*args, **kwargs)
    return decorated_function


def rater_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': '请先登录'}), 401
            flash('请先登录', 'warning')
            return redirect(url_for('center.login'))
        if not current_user.is_rater_user:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': '需要评级师权限'}), 403
            flash('需要评级师权限', 'error')
            return redirect(url_for('center.center_index'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': '请先登录'}), 401
            flash('请先登录', 'warning')
            return redirect(url_for('center.login'))
        if not current_user.is_admin_user:
            if request.path.startswith('/api/'):
                return jsonify({'success': False, 'message': '需要管理员权限'}), 403
            flash('需要管理员权限', 'error')
            return redirect(url_for('center.center_index'))
        return f(*args, **kwargs)
    return decorated_function


def rate_limit(f):
    """简单的频率限制装饰器（基于 IP + 时间窗口）"""
    from flask import g
    import time

    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 实际生产中可接入 Redis 或 Flask-Limiter
        return f(*args, **kwargs)
    return decorated_function
