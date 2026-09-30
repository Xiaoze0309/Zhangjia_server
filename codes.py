"""
LanOS 3.0 - 三码体系
- 樟嘉码（条形码，管理员专用）：ZJ-{Base32(SHA256(EPID|ESID|ETID|SALT))[:22]}
- 数据码（二维码，公开）：https://.../v/{ESID}
- 公众号码（二维码）：https://.../wx/{ESID}
"""
import hashlib
import base64
import io
import qrcode
import barcode
from barcode.writer import ImageWriter

# 樟嘉码盐值（生产环境应从环境变量读取）
ZJ_SALT = 'zhangjia-2026-lanos3-secret'

# Base32 字母表（RFC 4648，去掉填充 =）
_B32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'


def _base32_encode(data: bytes) -> str:
    """自定义 Base32 编码（RFC 4648），返回无填充字符串"""
    return base64.b32encode(data).decode('ascii').rstrip('=')


def gen_zj_code(epid: str, esid: str, etid: str) -> str:
    """
    生成樟嘉码：ZJ-{Base32(SHA256(EPID|ESID|ETID|SALT))[:22]}
    示例：ZJ-7K3M9P2XQ8NR5TW4YB6HC
    """
    raw = f"{epid}|{esid}|{etid}|{ZJ_SALT}".encode('utf-8')
    digest = hashlib.sha256(raw).digest()
    b32 = _base32_encode(digest)
    return f"ZJ-{b32[:22]}"


def verify_zj_code(zj_code: str, epid: str, esid: str, etid: str) -> bool:
    """校验樟嘉码是否匹配"""
    expected = gen_zj_code(epid, esid, etid)
    return zj_code.upper() == expected.upper()


def gen_qrcode_image(data: str, box_size: int = 6, border: int = 2) -> io.BytesIO:
    """生成二维码 PNG，返回 BytesIO"""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a1a1a", back_color="#FAF8F3")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    buf.seek(0)
    return buf


def gen_barcode_image(data: str) -> io.BytesIO:
    """生成 Code128 条形码 PNG，返回 BytesIO"""
    buf = io.BytesIO()
    Code128 = barcode.get_barcode_class('code128')
    writer = ImageWriter()
    # 自定义输出参数
    options = {
        'module_width': 0.4,
        'module_height': 14.0,
        'quiet_zone': 2.0,
        'font_size': 8,
        'text_distance': 2.0,
        'background': '#FAF8F3',
        'foreground': '#1a1a1a',
    }
    Code128(data, writer=writer).write(buf, options=options)
    buf.seek(0)
    return buf


def build_data_code_url(base_url: str, esid: str) -> str:
    """数据码 URL：公开验证页"""
    return f"{base_url}/v/{esid}"


def build_wx_code_url(base_url: str, esid: str) -> str:
    """公众号码 URL：跳转公众号"""
    return f"{base_url}/wx/{esid}"
