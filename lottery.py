"""
LanOS 2.5 中秋抽奖脚本（原生 sqlite3）
生成 5 个 EUID + 5 个 EFID，写入 lottery_records 和 coupons 表

用法：python lottery.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app
from db import init_db_schema, get_db
from center_app import gen_euid, gen_efid


def run_lottery(winners=None, count=5):
    init_db_schema()
    with app.app_context():
        db = get_db()
        records = []
        for i in range(count):
            euid = gen_euid()
            efid = gen_efid()
            while db.execute("SELECT id FROM lottery_records WHERE euid=?", (euid,)).fetchone():
                euid = gen_euid()
            while db.execute("SELECT id FROM lottery_records WHERE efid=?", (efid,)).fetchone():
                efid = gen_efid()
            while db.execute("SELECT id FROM coupons WHERE efid=?", (efid,)).fetchone():
                efid = gen_efid()

            username = winners[i] if winners and i < len(winners) else f'中奖用户{i+1}'

            db.execute(
                "INSERT INTO lottery_records (euid, efid, username, prize_type) VALUES (?, ?, ?, 'free_rating')",
                (euid, efid, username)
            )
            db.execute(
                "INSERT INTO coupons (efid, discount_type, discount_value, is_used) VALUES (?, 'full', 0, 0)",
                (efid,)
            )
            records.append({'euid': euid, 'efid': efid, 'username': username})
        db.commit()

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
        for r in records:
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
    winners = None
    run_lottery(winners=winners, count=5)
