import os
import re
import collections
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Department, Teacher, Classroom, ClassGroup, Course, SystemSetting, course_class_association

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:secretpassword@localhost:15432/course_schedule")

def parse_markdown_table(md_content):
    # 尋找 115-1 資工系教師授課科目規劃表
    section_pattern = r"# 115-1 資工系教師授課科目規劃表\s+(.*?)(?=\n#|$)"
    match = re.search(section_pattern, md_content, re.DOTALL)
    if not match:
        return []
    
    table_content = match.group(1)
    rows = table_content.strip().split('\n')
    data = []
    
    # 跳過標頭與分隔線
    for row in rows:
        if '|' not in row or ':---' in row or '教師 | 課程名稱' in row:
            continue
        
        cols = [c.strip() for c in row.split('|') if c.strip()]
        if len(cols) < 4:
            continue
        
        teacher_name = cols[0]
        course_name = cols[1]
        class_names = cols[2]
        credits_str = cols[3]
        note = cols[4] if len(cols) > 4 else ""
        
        # 解析學分
        try:
            credits = int(credits_str.split('/')[0])
        except:
            credits = 3
            
        data.append({
            "teacher": teacher_name,
            "course": course_name,
            "classes": class_names,
            "credits": credits,
            "note": note
        })
    return data

def init_from_summary():
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    
    # 清空資料庫
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("--- 正在從 course_summary.md 匯入 115-1 資料 ---", flush=True)

    summary_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "course_summary.md")
    with open(summary_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    course_data = parse_markdown_table(md_content)
    if not course_data:
        print("❌ 找不到課程規劃表資料")
        return

    dept = Department(name="資訊工程系")
    db.add(dept); db.flush()

    teachers_map = {}
    classes_map = {}
    rooms_map = {}
    
    # 預定義教室
    pc_room_names = ["C407", "C501", "F301", "F302", "F317", "F407", "F409"]
    gen_room_names = ["C405", "C501", "C502", "體育館", "無人機實作場"]
    for rname in set(pc_room_names + gen_room_names + ["I201"]):
        r = Classroom(name=rname)
        db.add(r); db.flush()
        rooms_map[rname] = r

    pc_idx = 0
    gen_idx = 0
    class_load_tracker = collections.defaultdict(int)

    global_course_registry = {} # 用於合併合班課 (同名且同老師)

    for item in course_data:
        c_name = item["course"]
        credits = item["credits"]
        t_name = item["teacher"]
        cl_names_raw = item["classes"]
        
        # 1. 基本過濾 & 無效班級過濾
        invalid_class_keywords = ["表1", "時數表", "日四技共同", "日四技產專", "備註"]
        if any(k in cl_names_raw for k in invalid_class_keywords):
            continue
            
        if credits > 4 or any(k in c_name for k in ["摘要", "說明"]):
            continue
        
        # 2. 移除自動拆分邏輯，直接使用原始課名（避免負載加倍）
        split_courses = [{"name": c_name, "credits": credits, "note": item["note"]}]

        for sc in split_courses:
            sc_name = sc["name"]
            sc_credits = sc["credits"]
            sc_note = sc["note"]

            # 解析班級並過濾超額學分
            c_list = []
            raw_classes = item["classes"].replace('、', ',').split(',')
            
            # 產專班過濾邏輯：大一不排大三四的專業課 (如資安實務、專案管理等)
            if "產專一" in item["classes"]:
                senior_keywords = ["專案管理", "安全管理", "實務專題", "大數據", "深度學習", "影像處理", "智慧製造"]
                if any(k in sc_name for k in senior_keywords):
                    continue

            valid_classes = []
            for cname in raw_classes:
                cname = cname.strip()
                if not cname: continue
                # 如果班級學分已滿 (32節)，則跳過此班級
                if class_load_tracker[cname] + sc_credits > 34:
                    continue
                
                if cname not in classes_map:
                    cl = ClassGroup(name=cname, department_id=dept.id)
                    db.add(cl); db.flush()
                    classes_map[cname] = cl
                valid_classes.append(classes_map[cname])
                class_load_tracker[cname] += sc_credits

            if not valid_classes: continue

            # 判斷班級年級 (取第一個班級)
            year_match = re.search(r"日四技([一二三四])", item["classes"])
            fixed_day = None
            fixed_slot = None
            allowed_slots = item.get("allowed_slots") # 預設保留規劃表設定
            
            if year_match:
                year_str = year_match.group(1)
                if "英文" in sc_name:
                    if year_str == "一": 
                        sc_name = "英文(一)"
                    elif year_str == "二": 
                        sc_name = "英文(三)"
                elif "中文" in sc_name:
                    if year_str == "一": 
                        fixed_day, fixed_slot = 0, 3 # 固定週一 3-4 節
                elif "體育" in sc_name:
                    if year_str == "一": fixed_day, fixed_slot = 2, 7
                
                # [關鍵修正] 如果是大一的 3 學分專業必修課，禁止排在週一上午，把位子讓給中文課
                if year_str == "一" and sc_credits == 3 and not any(k in sc_name for k in ["中文", "英文", "電腦應用"]):
                    # 排除週一上午 (0-0, 0-1, 0-2, 0-3)
                    # 格式：Day,Slot (Day 0-4, Slot 1-9)
                    all_slots = []
                    for d in range(5):
                        for s in range(1, 10):
                            if d == 0 and s <= 4: continue # 排除週一上午
                            all_slots.append(f"{d},{s}")
                    allowed_slots = "|".join(all_slots)

            if t_name not in teachers_map:
                is_dir = any(name in t_name for name in ["林金俊", "藍中賢"])
                t = Teacher(name=t_name, is_director=is_dir, department_id=dept.id)
                db.add(t); db.flush()
                teachers_map[t_name] = t
            t_obj = teachers_map[t_name]
            
            key = (sc_name, t_name)
            if key in global_course_registry:
                course_obj = global_course_registry[key]
                for cl in valid_classes:
                    if cl not in course_obj.classes:
                        course_obj.classes.append(cl)
                continue

            r_obj = None
            if "體育" in sc_name: r_obj = rooms_map.get("體育館")
            elif "無人機" in sc_name: r_obj = rooms_map.get("無人機實作場")
            elif "中文" in sc_name: 
                r_obj = rooms_map.get("I201")
                print(f"DEBUG: 課程 {sc_name} 分配到教室 {r_obj.name if r_obj else 'None'}", flush=True)
            elif "使用電腦" in sc_note or "電腦" in sc_name:
                r_obj = rooms_map.get(pc_room_names[pc_idx % len(pc_room_names)])
                pc_idx += 1
            else:
                r_obj = rooms_map.get(gen_room_names[gen_idx % len(gen_room_names)])
                gen_idx += 1

            is_res = (t_name == "(保留課程)")
            should_sched = (not is_res) and (not any(k in sc_name for k in ["實習", "摘要", "校外實習"]))
            course_obj = Course(
                name=sc_name, credits=sc_credits, teacher_id=t_obj.id,
                classroom_id=r_obj.id if r_obj else None, note=sc_note,
                is_reserved=is_res, should_schedule=should_sched,
                fixed_day=fixed_day, fixed_slot=fixed_slot
            )
            course_obj.classes = valid_classes
            db.add(course_obj)
            global_course_registry[key] = course_obj

    # 系統設定
    db.add(SystemSetting(
        thursday_afternoon_off=True,
        friday_all_day_off=True,
        ge_zone_day=0,
        ge_zone_slots="5,6,7,8",
        director_off_day=1,
        director_off_slots="5,6,7,8"
    ))

    db.commit()
    db.close()
    print(f"✅ 匯入成功！共匯入 {len(course_data)} 門課程需求。", flush=True)

if __name__ == "__main__":
    init_from_summary()
