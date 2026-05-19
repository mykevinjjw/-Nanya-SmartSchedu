import json
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Department, Teacher, Classroom, ClassGroup, Course, SystemSetting

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:secretpassword@localhost:15432/course_schedule")

def init_115_1_final():
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("--- 正在執行原子化資料匯入 (115-1 終極去重版) ---", flush=True)

    json_path = os.path.join(os.path.dirname(__file__), "comprehensive_115_1.json")
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    dept = Department(name="資訊工程系")
    db.add(dept); db.flush()

    teachers_map = {name: Teacher(name=name, department_id=dept.id) for name in data["teachers"]}
    db.add_all(teachers_map.values()); db.flush()
    
    # 增加虛擬老師
    for special in ["共同", "通識", "班導師", "(保留課程)", "(同系工組)", "共開", "系主任"]:
        if special not in teachers_map:
            t = Teacher(name=special, department_id=dept.id)
            db.add(t); db.flush(); teachers_map[special] = t

    # --- 教室清單 (規則 5E) ---
    pc_room_names = ["C407", "C501", "F301", "F302", "F317", "F407", "F409"]
    gen_room_names = ["C405", "C501", "C502", "體育館", "無人機實作場"]
    all_rooms = list(set(pc_room_names + gen_room_names))
    
    rooms_map = {rname: Classroom(name=rname) for rname in all_rooms}
    db.add_all(rooms_map.values()); db.flush()

    classes_map = {cname: ClassGroup(name=cname, department_id=dept.id) for cname in data["class_groups"]}
    db.add_all(classes_map.values()); db.flush()

    # --- 核心邏輯：真正的「班級-課程」唯一性 ---
    global_course_registry = {} 
    class_course_set = {cl.id: set() for cl in classes_map.values()}

    for c in data["courses"]:
        c_name = c["name"]
        cl_name = c["class_name"]
        t_name = c["teacher_name"]
        
        # 1. 基本過濾
        if c["credits"] > 4 or any(k in c_name for k in ["實習", "摘要", "統計", "說明"]): continue
        
        cl_obj = classes_map.get(cl_name)
        if not cl_obj: continue

        # 2. 班級內去重
        if c_name in class_course_set[cl_obj.id]: continue

        # 3. 跨班合併 (合班)
        key = (c_name, t_name)
        if key in global_course_registry:
            course_obj = global_course_registry[key]
            if cl_obj not in course_obj.classes:
                course_obj.classes.append(cl_obj)
        else:
            t_obj = teachers_map.get(t_name, teachers_map["(保留課程)"])
            
            # --- 強化的教室識別與初分配 ---
            r_obj = None
            note_str = (c["note"] or "").upper()
            c_name_upper = c_name.upper()
            
            # 平衡分配用
            if not hasattr(init_115_1_final, "_pc_idx"): init_115_1_final._pc_idx = 0
            if not hasattr(init_115_1_final, "_gen_idx"): init_115_1_final._gen_idx = 0

            if "體育" in c_name_upper:
                r_obj = rooms_map.get("體育館")
            elif "無人機" in c_name_upper or "無人機" in note_str:
                r_obj = rooms_map.get("無人機實作場")
            elif "電腦" in note_str:
                # 輪詢分配電腦教室
                r_obj = rooms_map.get(pc_room_names[init_115_1_final._pc_idx % len(pc_room_names)])
                init_115_1_final._pc_idx += 1
            else:
                # 輪詢分配一般教室
                r_obj = rooms_map.get(gen_room_names[init_115_1_final._gen_idx % len(gen_room_names)])
                init_115_1_final._gen_idx += 1

            course_obj = Course(
                name=c_name, credits=c["credits"], teacher_id=t_obj.id,
                classroom_id=r_obj.id if r_obj else None,
                fixed_day=c.get("fixed_day"), fixed_slot=c.get("fixed_slot"),
                allowed_slots=c.get("allowed_slots"), note=c["note"]
            )
            db.add(course_obj); db.flush()
            course_obj.classes = [cl_obj]
            global_course_registry[key] = course_obj
        
        class_course_set[cl_obj.id].add(c_name)

    db.add(SystemSetting(
        thursday_afternoon_off=True, friday_all_day_off=True,
        ge_zone_day=0, ge_zone_slots="5,6,7,8",
        director_off_day=1, director_off_slots="1,2,3,4",
        midweek_limit_enabled=False, midweek_allowed_slots="1,2,3,4,5,6,7,8"
    ))

    db.commit()
    db.close()
    print(f"✅ 終極去重匯入成功！實際開課數: {len(global_course_registry)}", flush=True)

if __name__ == "__main__":
    init_115_1_final()
