import sqlite3
import random
from datetime import datetime

# 1. 连接金库
conn = sqlite3.connect("mindvault_keys.db")

# 🔥 核心防御：如果表不存在，印钞机自己先建表！防止报 no such table 错误
conn.execute("CREATE TABLE IF NOT EXISTS activation_keys (key_code TEXT PRIMARY KEY, is_active BOOLEAN, created_at TEXT)")
conn.commit()

def generate_keys(count=5):
    print(f"\n🚀 开始铸造 {count} 枚神级密钥...\n")
    
    # 🔥 体验优化：剔除了极易混淆的数字 0、1 和字母 O、I
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    
    for _ in range(count):
        # 生成类似 MV-A8F2-9B3C 的无歧义炫酷密钥
        part1 = ''.join(random.choices(chars, k=4))
        part2 = ''.join(random.choices(chars, k=4))
        key_code = f"MV-{part1}-{part2}"
        
        try:
            conn.execute("INSERT INTO activation_keys (key_code, is_active, created_at) VALUES (?, ?, ?)",
                         (key_code, True, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            print(f"✅ 铸造成功: {key_code}")
        except Exception as e:
            print(f"❌ 失败: {e}")
    print("\n🎉 密钥铸造完毕！可以拿去发给客户了！")

if __name__ == "__main__":
    generate_keys(5) # 默认生成 5 个，你想生成几个就改这个数字
