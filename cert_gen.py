"""
LanOS 3.0 - 电子证书 PNG 生成
尺寸 800×1200，象牙白 #FAF8F3 + 金色 #C9A227
内容：币图 + ESID + 币名 + 评级 + 部门 + 评级师 + 签发时间
底部：数据码 + 公众号码 + 樟嘉码
"""
import os
import io
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

# 配色
IVORY = (250, 248, 243)       # #FAF8F3
GOLD = (201, 162, 39)         # #C9A227
DARK = (40, 35, 28)
GRAY = (120, 115, 108)

W, H = 800, 1200

# 字体路径
_FONT_DIR = '/usr/share/fonts/opentype/noto'
FONT_REGULAR = os.path.join(_FONT_DIR, 'NotoSansCJK-Regular.ttc')
FONT_BOLD = os.path.join(_FONT_DIR, 'NotoSansCJK-Bold.ttc')
# 回退字体
_FONT_FALLBACK = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def _font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REGULAR
    if not os.path.exists(path):
        path = _FONT_FALLBACK
    return ImageFont.truetype(path, size)


def _load_coin_image(coin_images_json, upload_folder, size=(460, 460)):
    """从 coin_images JSON 加载第一张币图，缩放居中"""
    import json
    try:
        paths = json.loads(coin_images_json) if coin_images_json else []
    except Exception:
        paths = []
    if not paths:
        return None
    # 取第一张评级后图（cert_images 优先，这里传入的是 coin_images）
    rel = paths[0] if isinstance(paths, list) else paths
    full = os.path.join(upload_folder, rel.replace('uploads/', ''))
    if not os.path.exists(full):
        return None
    try:
        img = Image.open(full).convert('RGB')
    except Exception:
        return None
    img.thumbnail(size, Image.LANCZOS)
    return img


def generate_certificate(order: dict, rater_name: str, dept_name: str,
                          upload_folder: str, base_url: str,
                          data_qr_buf, wx_qr_buf, zj_barcode_buf) -> io.BytesIO:
    """
    生成电子证书 PNG，返回 BytesIO
    order: cert_orders 行的 dict
    """
    img = Image.new('RGB', (W, H), IVORY)
    draw = ImageDraw.Draw(img)

    # 顶部金色装饰条
    draw.rectangle([0, 0, W, 8], fill=GOLD)
    # 底部金色装饰条
    draw.rectangle([0, H - 8, W, H], fill=GOLD)

    # 标题
    draw.text((W // 2, 50), '樟嘉评级电子证书', fill=DARK,
              font=_font(34, bold=True), anchor='mt')
    draw.line([(W // 2 - 60, 100), (W // 2 + 60, 100)], fill=GOLD, width=3)

    y = 130

    # ESID
    esid = order.get('cert_no') or '-'
    draw.text((W // 2, y), f'ESID · {esid}', fill=GOLD,
              font=_font(20, bold=True), anchor='mt')
    y += 40

    # 币图
    coin_img = _load_coin_image(order.get('coin_images'), upload_folder, (420, 420))
    if coin_img:
        cw, ch = coin_img.size
        img.paste(coin_img, ((W - cw) // 2, y))
        y += ch + 24
    else:
        # 占位图
        draw.rectangle([(W - 300) // 2, y, (W + 300) // 2, y + 300],
                       outline=GOLD, width=2)
        draw.text((W // 2, y + 140), '暂无币图', fill=GRAY,
                  font=_font(20), anchor='mm')
        y += 324

    # 币名
    coin_name = order.get('coin_name') or '-'
    draw.text((W // 2, y), coin_name, fill=DARK, font=_font(30, bold=True), anchor='mt')
    y += 48

    # 评级信息
    cert_result = order.get('cert_result')
    grade = '-'
    try:
        import json as _json
        if cert_result:
            cr = _json.loads(cert_result) if isinstance(cert_result, str) else cert_result
            grade = cr.get('grade', '-')
    except Exception:
        pass

    info_lines = [
        f'评级：{grade}',
        f'部门：{dept_name}',
        f'评级师：{rater_name}',
    ]
    for line in info_lines:
        draw.text((W // 2, y), line, fill=DARK, font=_font(22), anchor='mt')
        y += 36

    # 签发时间
    issued = order.get('updated_at')
    if isinstance(issued, datetime):
        issued_str = issued.strftime('%Y-%m-%d %H:%M')
    else:
        issued_str = str(issued) if issued else '-'
    draw.text((W // 2, y), f'签发时间：{issued_str}', fill=GRAY,
              font=_font(18), anchor='mt')
    y += 50

    # 分割线
    draw.line([(80, y), (W - 80, y)], fill=GOLD, width=1)
    y += 24

    # 底部三码区
    code_y = y
    # 数据码（二维码）
    data_qr = Image.open(data_qr_buf).convert('RGB')
    data_qr.thumbnail((150, 150), Image.LANCZOS)
    img.paste(data_qr, (100, code_y))
    draw.text((100 + 75, code_y + 156), '数据码', fill=DARK,
              font=_font(14, bold=True), anchor='mt')

    # 公众号码（二维码）
    wx_qr = Image.open(wx_qr_buf).convert('RGB')
    wx_qr.thumbnail((150, 150), Image.LANCZOS)
    img.paste(wx_qr, (W // 2 - 75, code_y))
    draw.text((W // 2, code_y + 156), '公众号码', fill=DARK,
              font=_font(14, bold=True), anchor='mt')

    # 樟嘉码（条形码）
    zj_img = Image.open(zj_barcode_buf).convert('RGB')
    zj_img.thumbnail((200, 150), Image.LANCZOS)
    img.paste(zj_img, (W - 100 - 200, code_y))
    draw.text((W - 100 - 100, code_y + 156), '樟嘉码', fill=DARK,
              font=_font(14, bold=True), anchor='mt')

    # 底部版权
    draw.text((W // 2, H - 30), '© 2026 樟嘉评级 · LanOS 3.0', fill=GRAY,
              font=_font(13), anchor='mm')

    buf = io.BytesIO()
    img.save(buf, format='PNG', quality=95)
    buf.seek(0)
    return buf
