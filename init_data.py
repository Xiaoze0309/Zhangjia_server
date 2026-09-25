"""
LanOS 2.5 评级中心 - 数据库初始化脚本（原生 sqlite3）
用法：python init_data.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from db import init_db_schema, get_db
from center_app import gen_efid
from werkzeug.security import generate_password_hash


def init_departments(db):
    depts = [
        ('jinan',   '济南站',   'EUID-JN'),
        ('beihai',  '北海站',   'EUID-BH'),
        ('hechi',   '河池站',   'EUID-HC'),
        ('lingbao', '灵宝站',   'EUID-LB'),
        ('moscow',  '莫斯科站', 'EUID-MS'),
    ]
    for slug, name, prefix in depts:
        existing = db.execute("SELECT id FROM departments WHERE slug=?", (slug,)).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO departments (slug, name, euid_prefix, pay_qr) VALUES (?, ?, ?, ?)",
                (slug, name, prefix, f'/static/pay/{slug}.jpg')
            )
            print(f'  + 部门：{name} ({slug})')
        else:
            print(f'  = 部门已存在：{name}')
    db.commit()


def init_pricing(db):
    dept_slugs = ['jinan', 'beihai', 'hechi', 'lingbao', 'moscow']
    count = 0
    for dept in dept_slugs:
        for svc in ['online', 'offline']:
            for box in ['PLA', 'JIN']:
                for guar in [0, 1]:
                    existing = db.execute(
                        "SELECT id FROM department_pricing WHERE department_slug=? AND service_type=? AND box_type=? AND has_guarantee=?",
                        (dept, svc, box, guar)
                    ).fetchone()
                    if existing:
                        continue
                    price = 50.0
                    if box == 'JIN':
                        price += 30.0
                    if guar == 1:
                        price += 20.0
                    if svc == 'offline':
                        price += 10.0
                    db.execute(
                        "INSERT INTO department_pricing (department_slug, service_type, box_type, has_guarantee, price) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (dept, svc, box, guar, price)
                    )
                    count += 1
    db.commit()
    print(f'  + 定价记录：{count} 条')


def init_admin(db):
    existing = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not existing:
        db.execute(
            "INSERT INTO users (username, email, password_hash, phone, is_rater, is_admin, rater_department, rater_euid) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ('admin', 'admin@zhangjiacenter.local', generate_password_hash('admin123'),
             '10000000000', 1, 1, 'jinan', 'EUID-CE-0001')
        )
        db.commit()
        print('  + 管理员：admin / admin123 (评级师+管理员, 部门=jinan)')
    else:
        db.execute(
            "UPDATE users SET is_rater=1, is_admin=1, rater_department=COALESCE(rater_department,'jinan'), "
            "rater_euid=COALESCE(rater_euid,'EUID-CE-0001') WHERE username='admin'"
        )
        db.commit()
        print('  = 管理员已存在，已确保权限')


def init_coupons(db, count=5):
    for _ in range(count):
        efid = gen_efid()
        while db.execute("SELECT id FROM coupons WHERE efid=?", (efid,)).fetchone():
            efid = gen_efid()
        db.execute(
            "INSERT INTO coupons (efid, discount_type, discount_value, is_used) VALUES (?, 'full', 0, 0)",
            (efid,)
        )
        print(f'  + 优惠券：{efid} (全免)')
    db.commit()


def main():
    init_db_schema()
    with app.app_context():
        db = get_db()
        print('=== LanOS 2.5 数据库初始化 ===')
        print()
        print('[1/4] 建表...')
        print('  + 所有表已创建/确认')
        print('[2/4] 部门...')
        init_departments(db)
        print('[3/4] 定价...')
        init_pricing(db)
        print('[4/4] 管理员 + 优惠券...')
        init_admin(db)
        init_coupons(db)

        print()
        print('=== 初始化完成 ===')
        print()
        print('部门列表：')
        for d in db.execute("SELECT slug, name, euid_prefix FROM departments ORDER BY id"):
            print(f'  {d["slug"]:12s} {d["name"]:8s} {d["euid_prefix"]}')
        print()
        print('优惠券列表：')
        for c in db.execute("SELECT efid, discount_type, is_used FROM coupons"):
            status = '已使用' if c['is_used'] else '可用'
            print(f'  {c["efid"]}  {c["discount_type"]}  {status}')
        print()
        print('管理员：admin / admin123')


if __name__ == '__main__':
    main()
