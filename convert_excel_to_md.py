import pandas as pd
import os
import re

def main():
    file_path = 'J-自動排課系統/115-1資工系教師授課科目規劃表.xlsx'
    df = pd.read_excel(file_path, sheet_name='資工系')

    # 尋找表頭在哪一行
    header_idx = -1
    for i in range(len(df)):
        row = df.iloc[i]
        if '學制年級' in str(row.values) and '科目名稱' in str(row.values):
            header_idx = i
            break
            
    if header_idx == -1:
        print("找不到表頭！")
        return

    # 重新設定 DataFrame
    df.columns = df.iloc[header_idx]
    df = df.iloc[header_idx+1:].reset_index(drop=True)

    # 取出需要的欄位
    required_cols = ['學制年級', '科目名稱', '學分數', '時數', '開課教師', '備註(開課建議教師)']
    available_cols = [c for c in required_cols if c in df.columns]
    df = df[available_cols]

    # ffill 學制年級
    if '學制年級' in df.columns:
        df['學制年級'] = df['學制年級'].ffill()

    # 移除空列或小計
    df = df.dropna(subset=['科目名稱'])
    df = df[~df['科目名稱'].astype(str).str.contains('小計|應開')]

    # 準備轉換的資料
    md_rows = []
    
    # 手動需要拆分的課程
    split_map = {
        "作業系統實務程式語言設計": ["作業系統實務", "程式語言設計"],
        "微積分資料結構": ["微積分", "資料結構"],
        "雲端運算資料結構": ["雲端運算", "資料結構"]
    }

    for _, row in df.iterrows():
        class_name = str(row.get('學制年級', '')).replace('\n', ' ')
        course_name = str(row.get('科目名稱', '')).strip()
        credits = str(row.get('學分數', '3')).replace('.0', '')
        hours = str(row.get('時數', credits)).replace('.0', '')
        teacher = str(row.get('開課教師', '')).replace('nan', '').strip()
        note = str(row.get('備註(開課建議教師)', '')).replace('nan', '').strip()

        if class_name == 'nan' or not class_name.strip() or '學制年級' in class_name or '---' in class_name:
            continue
            
        if '支援共同科目與通識課程' in course_name or '日四技共同' in class_name or '日四技產專' in class_name:
             # 先跳過這些，讓它們原本的系級或通識設定來處理
             continue

        # 處理拆分課程
        courses_to_add = []
        if course_name in split_map:
            for sc in split_map[course_name]:
                courses_to_add.append(sc)
        else:
            courses_to_add.append(course_name)

        for c_name in courses_to_add:
            if not teacher:
                teacher = "(保留課程)" # 如果沒寫老師，暫定保留
            
            # Markdown 表格行: | 教師 | 課程名稱 | 班級 | 學分/時數 | 備註 |
            credit_hour = f"{credits}/{hours}" if credits != hours else credits
            md_row = f"| {teacher} | {c_name} | {class_name} | {credit_hour} | {note} |"
            md_rows.append(md_row)

    md_content = "\n# 115-1 資工系教師授課科目規劃表\n\n"
    md_content += "| 教師 | 課程名稱 | 班級 | 學分/時數 | 備註 |\n"
    md_content += "|---|---|---|---|---|\n"
    md_content += "\n".join(md_rows)
    md_content += "\n"

    # 寫入 / 附加到 course_summary.md
    summary_path = 'course_summary.md'
    
    with open(summary_path, 'r', encoding='utf-8') as f:
        existing_content = f.read()
        
    # 如果已經存在，先移除舊的
    if "# 115-1 資工系教師授課科目規劃表" in existing_content:
        parts = existing_content.split("# 115-1 資工系教師授課科目規劃表")
        existing_content = parts[0].strip() + "\n\n"
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write(existing_content + md_content)
        
    print(f"成功將 115-1 課程規劃表轉出並附加到 course_summary.md。共處理 {len(md_rows)} 筆課程。")

if __name__ == '__main__':
    main()
