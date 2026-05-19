import json
import sys

# 強制設定標準輸出編碼為 utf-8
sys.stdout.reconfigure(encoding='utf-8')

with open('schedule_result.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for item in data:
    if item['day'] == 4:
        print(f"[{item['class_name']}] {item['course_name']} - {item['teacher_name']}")
