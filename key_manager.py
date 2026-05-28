import sqlite3
import uuid
import os
from datetime import datetime

# 连接到大盘的密钥数据库
DB_PATH = "mindvault_keys.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS activation_keys (key_code TEXT PRIMARY KEY, is_active BOOLEAN, created_at TEXT)")
    conn.commit()
    return conn


def generate_key(conn):
    # 生成炫酷的专属密钥格式：MIND-XXXX-XXXX
    raw_uuid = uuid.uuid4().hex.upper()
    new_key = f"MIND-{raw_uuid[:4]}-{raw_uuid[4:8]}"
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute("INSERT INTO activation_keys (key_code, is_active, created_at) VALUES (?, ?, ?)",
                 (new_key, True, created_at))
    conn.commit()
    print(f"\n✨ [发卡成功] 成功生成专属密钥: \033[92m{new_key}\033[0m")
    print(f"👉 将此密钥发给你的朋友，他们登录后将拥有独立的记忆图谱！\n")


def list_keys(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT key_code, is_active, created_at FROM activation_keys ORDER BY created_at DESC")
    rows = cursor.fetchall()

    print("\n" + "=" * 40)
    print(" 🗝️ MindVault 商业密钥大盘")
    print("=" * 40)
    if not rows:
        print("暂无生成的下级密钥。")
    for row in rows:
        status = "🟢 生效中" if row[1] else "🔴 已封禁"
        print(f"[{status}] 密钥: {row[0]} | 生成于: {row[2]}")
    print("=" * 40 + "\n")


def disable_key(conn):
    target = input("请输入要封禁的密钥: ").strip().upper()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active FROM activation_keys WHERE key_code = ?", (target,))
    if cursor.fetchone():
        cursor.execute("UPDATE activation_keys SET is_active = False WHERE key_code = ?", (target,))
        conn.commit()
        print(f"\n🚫 密钥 [{target}] 已被物理封禁！拥有该密钥的用户将无法再次登录！\n")
    else:
        print("\n⚠️ 找不到该密钥！\n")


def main():
    if not os.path.exists(DB_PATH):
        print("⚠️ 警告：找不到 mindvault_keys.db，请确保你在这个脚本和 main.py 放在同一个服务器目录下！")

    conn = init_db()
    while True:
        print("👑 【最高指挥官发卡终端】")
        print("1. ➕ 生成新密钥 (发卡)")
        print("2. 📊 查看所有密钥状态")
        print("3. 🚫 封禁违规密钥")
        print("4. 🚪 退出")
        choice = input("请选择操作 (1/2/3/4): ")

        if choice == '1':
            generate_key(conn)
        elif choice == '2':
            list_keys(conn)
        elif choice == '3':
            disable_key(conn)
        elif choice == '4':
            print("再见，长官！")
            break
        else:
            print("无效输入，请重试。")


if __name__ == "__main__":
    main()