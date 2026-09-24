"""
LanOS 2.5 评级中心 - 数据库初始化脚本
用法：python init_data.py
"""
import os
import sys
from datetime import datetime

# 确保能导入项目模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, User, Department, DepartmentPricing, Coupon
from center_app import gen_efid


def init_departments():
    """初始化部门"""
    depts = [
        {'slug': 'jinan',   'name': '济南站', 'euid_prefix': 'EUID-JN'},
        {'slug': 'beihai',  'name': '北海站', 'euid_prefix': 'EUID-BH'},
        {'slug': 'hechi',   'name': '河池站', 'euid_prefix': 'EUID-HC'},
        {'slug': 'lingbao', 'name': '灵宝站', 'euid_prefix': 'EUID-LB'},
        {'slug': 'moscow',  'name': '莫斯科站', 'euid_prefix': 'EUID-MS'},
    ]
    for d in depts:
        existing = Department.query.filter_by(slug=d['slug']).first()
        if not existing:
            dept = Department(
                slug=d['slug'],
                name=d['name'],
                euid_prefix=d['euid_prefix'],
                pay_qr=f'/static/pay/{d["slug"]}.jpg',
            )
            db.session.add(dept)
            print(f'  + 部门：{d["name"]} ({d["slug"]})')
        else:
            print(f'  = 部门已存在：{d["name"]}')
    db.session.commit()


def init_pricing():
    """初始化定价表"""
    dept_slugs = ['jinan', 'beihai', 'hechi', 'lingbao', 'moscow']
    service_types = ['online', 'offline']
    box_types = ['PLA', 'JIN']
    guarantee_options = [0, 1]

    count = 0
    for dept in dept_slugs:
        for svc in service_types:
            for box in box_types:
                for guar in guarantee_options:
                    existing = DepartmentPricing.query.filter_by(
                        department_slug=dept,
                        service_type=svc,
                        box_type=box,
                        has_guarantee=guar
                    ).first()
                    if existing:
                        continue

                    # 定价规则
                    price = 50.0
                    if box == 'JIN':
                        price += 30.0
                    if guar == 1:
                        price += 20.0
                    if svc == 'offline':
                        price += 10.0

                    pricing = DepartmentPricing(
                        department_slug=dept,
                        service_type=svc,
                        box_type=box,
                        has_guarantee=guar,
                        price=price,
                    )
                    db.session.add(pricing)
                    count += 1
    db.session.commit()
    print(f'  + 定价记录：{count} 条')


def init_admin():
    """创建默认管理员"""
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@zhangjiacenter.local',
            phone='10000000000',
            is_rater=1,
            is_admin=1,
            rater_department='jinan',
            rater_euid='EUID-CE-0001',
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print('  + 管理员：admin / admin123 (评级师+管理员, 部门=jinan)')
    else:
        # 确保管理员有评级师+管理员权限
        admin.is_rater = 1
        admin.is_admin = 1
        if not admin.rater_department:
            admin.rater_department = 'jinan'
        if not admin.rater_euid:
            admin.rater_euid = 'EUID-CE-0001'
        db.session.commit()
        print('  = 管理员已存在，已确保权限')


def init_coupons(count=5):
    """生成测试优惠券（全免券）"""
    for _ in range(count):
        efid = gen_efid()
        existing = Coupon.query.filter_by(efid=efid).first()
        if existing:
            continue
        coupon = Coupon(
            efid=efid,
            discount_type='full',
            discount_value=0,
            is_used=0,
        )
        db.session.add(coupon)
        print(f'  + 优惠券：{efid} (全免)')
    db.session.commit()


def main():
    with app.app_context():
        print('=== LanOS 2.5 数据库初始化 ===')
        print()

        print('[1/4] 建表...')
        db.create_all()
        print('  + 所有表已创建/确认')

        print('[2/4] 部门...')
        init_departments()

        print('[3/4] 定价...')
        init_pricing()

        print('[4/4] 管理员 + 优惠券...')
        init_admin()
        init_coupons()

        print()
        print('=== 初始化完成 ===')
        print()
        print('部门列表：')
        for d in Department.query.all():
            print(f'  {d.slug:12s} {d.name:8s} {d.euid_prefix}')
        print()
        print('优惠券列表：')
        for c in Coupon.query.all():
            status = '已使用' if c.is_used else '可用'
            print(f'  {c.efid}  {c.discount_type}  {status}')
        print()
        print('管理员：admin / admin123')


if __name__ == '__main__':
    main()
