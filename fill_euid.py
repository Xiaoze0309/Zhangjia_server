import sqlite3
import random
import datetime

ROMAN_MAP = {
    0: '', 1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V',
    6: 'VI', 7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X',
    11: 'XI', 12: 'XII', 13: 'XIII', 14: 'XIV', 15: 'XV',
    16: 'XVI', 17: 'XVII', 18: 'XVIII'
}

def encrypt_random(raw):
    num = int(raw)
    bin_str = bin(num)[2:]
    while len(bin_str) % 4 != 0:
        bin_str = '0' + bin_str
    hex_str = ''
    for i in range(0, len(bin_str), 4):
        hex_str += hex(int(bin_str[i:i+4], 2))[2:].upper()
    encrypted = int(hex_str, 16)
    enc_str = str(encrypted)
    if len(enc_str) > 9:
        enc_str = enc_str[-9:]
    else:
        enc_str = enc_str.zfill(9)
    return enc_str

def generate_display_id():
    date_str = datetime.datetime.now().strftime("%y%m%d")
    while True:
        raw = str(random.randint(100000000, 999999999))
        if raw[0] != '0':
            break
    enc_num = encrypt_random(raw)
    last_two_sum = int(enc_num[-2]) + int(enc_num[-1])
    roman = ROMAN_MAP.get(last_two_sum, '')
    return f"{date_str}-{enc_num}{roman}"

def fill_euid():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE display_id IS NULL")
    rows = cursor.fetchall()
    if not rows:
        print("✅ 所有用户已有 EUID，无需补全。")
        conn.close()
        return
    print(f"📋 找到 {len(rows)} 个用户需要补全 EUID。")
    for (user_id,) in rows:
        while True:
            new_euid = generate_display_id()
            cursor.execute("SELECT id FROM users WHERE display_id = ?", (new_euid,))
            if not cursor.fetchone():
                break
        cursor.execute("UPDATE users SET display_id = ? WHERE id = ?", (new_euid, user_id))
        print(f"用户 ID {user_id} ➜ EUID: {new_euid}")
    conn.commit()
    conn.close()
    print("🎉 补全完成！")

if __name__ == "__main__":
    fill_euid()
