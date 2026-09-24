"""
LanOS 2.5 中秋抽奖脚本
生成 5 个 EUID（中奖用户编号）+ 5 个 EFID（优惠券码）
自动写入 lottery_records 和 coupons 表

用法：python lottery.py
"""
import os
import sys
import random
import string

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from models import db, LotteryRecord, Coupon
from center_app import gen_euid, gen_efid


def run_lottery(winners=None, count=5):
    """
    运行抽奖
    winners: 可选，指定中奖用户名列表。如不指定则只生成 EUID
    count: 生成数量，默认 5
    """
    with app.app_context():
        records = []
        for i in range(count):
            euid = gen_euid()
            efid = gen_efid()

            # 确保唯一性
            while LotteryRecord.query.filter_by(euid=euid).first():
                euid = gen_euid()
            while LotteryRecord.query.filter_by(efid=efid).first():
                efid = gen_efid()
            while Coupon.query.filter_by(efid=efid).first():
                efid = gen_efid()

            username = winners[i] if winners and i < len(winners) else f'中奖用户{i+1}'

            # 写入抽奖记录
            record = LotteryRecord(
                euid=euid,
                efid=efid,
                username=username,
                prize_type='free_rating',
            )
            db.session.add(record)

            # 写入优惠券表
            coupon = Coupon(
                efid=efid,
                discount_type='full',
                discount_value=0,
                is_used=0,
            )
            db.session.add(coupon)

            records.append({
                'euid': euid,
                'efid': efid,
                'username': username,
            })

        db.session.commit()

        print('=== 中秋抽奖结果 ===')
        print()
        print(f'{"序号":<4} {"用户名":<12} {"EUID":<20} {"EFID":<20}')
        print('-' * 60)
        for i, r in enumerate(records):
            print(f'{i+1:<4} {r["username"]:<12} {r["euid"]:<20} {r["efid"]:<20}')
        print()
        print(f'共生成 {len(records)} 张优惠券（全免评级券）')
        print()
        print('中奖名单文案（可直接复制发群）：')
        print('─' * 40)
        for i, r in enumerate(records):
            print(f'🏆 {r["username"]} - 券码：{r["efid"]}')
        print('─' * 40)
        print()
        print('私信通知文案：')
        print('─' * 40)
        for r in records:
            print(f'恭喜您在樟嘉评级中心中秋抽奖中获奖！')
            print(f'您的专属优惠券码：{r["efid"]}')
            print(f'使用方式：申请评级时输入此券码，即可免费评级一次。')
            print()
        print('─' * 40)

        return records


if __name__ == '__main__':
    # 如有中奖用户名，在此指定
    # winners = ['张三', '李四', '王五', '赵六', '钱七']
    winners = None
    run_lottery(winners=winners, count=5)
