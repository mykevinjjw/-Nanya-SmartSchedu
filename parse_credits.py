import re
import collections
import os

summary_path = os.path.join(os.path.dirname(__file__), "course_summary.md")
with open(summary_path, "r", encoding="utf-8") as f:
    content = f.read()

# 尋找所有的 ## 標題 (代表不同的科系/年級)
sections = re.split(r'\n## ', '\n' + content)[1:]

for section in sections:
    lines = section.strip().split('\n')
    title = lines[0].strip()
    
    # 找工作表1的表格
    table_content = ""
    in_table = False
    for line in lines:
        if '工作表: 課程結構分析' in line or '工作表: 課程規劃表' in line or '工作表: 工作表1' in line:
            pass
        if '|' in line and '課程名稱' in line and '學期' in line:
            in_table = True
            continue
        if in_table and '|' in line and ':---' in line:
            continue
        if in_table and '|' in line:
            if '至少應修' in line.replace(' ', ''):
                continue
            table_content += line + '\n'
        if in_table and not line.strip() and table_content:
            break
            
    if not table_content:
        continue
        
    sem_credits = collections.defaultdict(int)
    for row in table_content.strip().split('\n'):
        cols = [c.strip() for c in row.split('|')[1:-1]]
        if len(cols) < 5: continue
        
        c_name = cols[0]
        try:
            credits = int(cols[1])
        except:
            credits = 0
            
        sem_raw = cols[5]
        # 可能有多個學期, 例如 "1-1, 1-2"
        sems = [s.strip() for s in sem_raw.split(',') if s.strip()]
        for s in sems:
            if re.match(r'^[1-4]-[1-2]$', s):
                sem_credits[s] += credits
                
    with open("credits.txt", "a", encoding="utf-8") as out_f:
        out_f.write(f"=== {title} ===\n")
        for s in ['1-1', '1-2', '2-1', '2-2', '3-1', '3-2', '4-1', '4-2']:
            if s in sem_credits:
                out_f.write(f"  學期 {s}: {sem_credits[s]} 學分\n")
        out_f.write("\n")
