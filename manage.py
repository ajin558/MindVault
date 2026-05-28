import sqlite3
import sys

conn = sqlite3.connect("mindvault_keys.db")
# 确保表存在
conn.execute("CREATE TABLE IF NOT EXISTS activation_keys (key_code TEXT PRIMARY KEY, is_active BOOLEAN, created_at TEXT)")

def list_keys():
    print("\n=== 🔑 MINDVAULT 密钥金库清单 ===")
    cursor = conn.execute("SELECT key_code, is_active, created_at FROM activation_keys")
    for row in cursor:
        status = "🟢 畅通" if row[1] else "🔴 封禁"
        print(f"[{status}] 密钥: {row[0]} | 铸造时间: {row[2]}")
    print("=================================\n")

def ban_key(key_code):
    conn.execute("UPDATE activation_keys SET is_active = False WHERE key_code = ?", (key_code,))
    conn.commit()
    print(f"\n🚫 已降维打击，永久封禁密钥: {key_code}\n")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "ban":
        if len(sys.argv) < 3:
            print("⚠️ 请提供要封禁的密钥！例如：python3 manage.py ban MV-XXXX")
        else:
            ban_key(sys.argv[2].strip().upper())
    else:
        list_keys()
        print("💡 [最高权限提示]：如需封禁某人，请运行 `python3 manage.py ban MV-XXXX`")
