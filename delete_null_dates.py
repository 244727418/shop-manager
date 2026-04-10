import sqlite3
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'manager', 'shop_manager.db')
print(f'数据库路径: {db_path}')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 先查看有哪些记录
cursor.execute('SELECT id, store_id, start_date, end_date FROM manual_margin_data')
records = cursor.fetchall()
print(f'当前记录数: {len(records)}')
for r in records:
    print(f'  ID: {r[0]}, store_id: {r[1]}, start_date: {r[2]}, end_date: {r[3]}')

# 删除start_date为空的记录
cursor.execute('DELETE FROM manual_margin_data WHERE start_date IS NULL OR start_date = ""')
print(f'已删除 {cursor.rowcount} 条空日期记录')

conn.commit()
conn.close()
print('删除完成')