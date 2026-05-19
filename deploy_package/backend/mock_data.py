import random
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Department, Teacher, Classroom, ClassGroup, Course, SystemSetting
import time

import os
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:secretpassword@localhost:15432/course_schedule")

def init_mock_data():
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine)
    
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("正在執行資料庫架構更新與資料重置...")

    dept = Department(name="資通工程系")
    db.add(dept)
    db.commit()

    teachers = [Teacher(name=f"老師{i:02d}", department_id=dept.id) for i in range(15)]
    teachers[0].name = "系主任"; teachers[0].is_director = True
    db.add_all(teachers)
    db.commit()

    classes = [
        ClassGroup(name="資通一A", department_id=dept.id),
        ClassGroup(name="資通二A", department_id=dept.id),
        ClassGroup(name="資通三A", department_id=dept.id),
        ClassGroup(name="資通四A", department_id=dept.id)
    ]
    db.add_all(classes)
    db.commit()

    rooms = [
        Classroom(name="101大教室"),
        Classroom(name="電算中心A"),
        Classroom(name="體育館"),
        Classroom(name="專題室"),
    ]
    db.add_all(rooms)
    db.commit()

    db.add(SystemSetting(
        ge_zone_day=0, 
        ge_zone_slots="5,6,7,8", 
        midweek_limit_enabled=True,
        midweek_allowed_slots="2,3,4,5,6,7"
    ))
    db.commit()

    # --- 課程分配 ---
    # 1. 勞作教育
    labor = Course(
        name="勞作教育", 
        credits=1, 
        teacher_id=teachers[4].id,
        classroom_id=rooms[0].id,
        allowed_slots="1,8"
    )
    labor.classes = [classes[0]]
    db.add(labor)

    # 2. 其它專業課
    # 大一
    y1 = [("計概", 3, 1, 0), ("微積分", 3, 0, 1), ("英文(一)", 2, 0, 2)] # (名, 學分, 教室索引, 老師索引)
    # 大二
    y2 = [("AI概論", 2, 1, 8), ("數位邏輯", 3, 1, 9)]
    # 大三
    y3 = [("專題(一)", 3, 3, 0), ("資通安全", 3, 0, 14)]

    def add_batch(data, class_obj):
        for name, credits, r_idx, t_idx in data:
            c = Course(name=name, credits=credits, classroom_id=rooms[r_idx].id, teacher_id=teachers[t_idx].id)
            db.add(c); db.flush(); c.classes = [class_obj]

    add_batch(y1, classes[0])
    add_batch(y2, classes[1])
    add_batch(y3, classes[2])

    db.commit()
    db.close()
    print("✅ 資料庫更新完成！")

if __name__ == "__main__":
    init_mock_data()
