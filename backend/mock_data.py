import random
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Department, Teacher, Classroom, ClassGroup, Course
import time

DATABASE_URL = "postgresql://admin:secretpassword@localhost:15432/course_schedule"

def get_db_engine():
    retries = 5
    while retries > 0:
        try:
            engine = create_engine(DATABASE_URL)
            engine.connect()
            return engine
        except Exception:
            time.sleep(2)
            retries -= 1
    raise Exception("無法連線至資料庫")

def init_mock_data():
    engine = get_db_engine()
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("重新建立不分年級、只分班級的課程資料...")

    dept = Department(name="資通工程系")
    db.add(dept)
    db.commit()

    teachers = [
        Teacher(name="系主任", title="教授", is_director=True, department_id=dept.id),
        Teacher(name="李教授", title="教授", department_id=dept.id),
        Teacher(name="陳副教授", title="副教授", department_id=dept.id),
        Teacher(name="林助理教授", title="助理教授", department_id=dept.id),
        Teacher(name="張老師", title="講師", department_id=dept.id),
        Teacher(name="黃老師", title="講師", department_id=dept.id),
        Teacher(name="趙教授", title="教授", department_id=dept.id),
        Teacher(name="孫老師", title="講師", department_id=dept.id),
        Teacher(name="周教授", title="教授", department_id=dept.id), # 新增師資
        Teacher(name="郭老師", title="講師", department_id=dept.id) # 新增師資
    ]
    db.add_all(teachers)
    db.commit()

    # 增加班級為 3 個，攤提課程壓力
    classes = [
        ClassGroup(name="資通A班", department_id=dept.id),
        ClassGroup(name="資通B班", department_id=dept.id),
        ClassGroup(name="資通C班", department_id=dept.id)
    ]
    db.add_all(classes)
    db.commit()

    rooms = [
        Classroom(name="101普通教室", room_type="一般"),
        Classroom(name="102普通教室", room_type="一般"),
        Classroom(name="103普通教室", room_type="一般"),
        Classroom(name="電腦教室A", room_type="電腦"),
        Classroom(name="電腦教室B", room_type="電腦"),
        Classroom(name="電腦教室C", room_type="電腦"),
        Classroom(name="體育館", room_type="體育"),
        Classroom(name="專題研討室", room_type="專題"),
    ]
    db.add_all(rooms)
    db.commit()

    # 調整課程池 (精簡核心課程，確保主任每班只教一門核心，其餘分配出去)
    curriculum_pool = [
        ("計算機概論", 3, "電腦", 0), # 系主任教 A,B,C 班的計概 (共 9 節)
        ("作業系統實務", 3, "電腦", 1), # 改由李教授教
        ("實務專題", 3, "專題", 0),    # 系主任教專題 (共 9 節)
        ("微積分", 3, "一般", 2),
        ("通訊網路概論", 3, "電腦", 3),
        ("數位邏輯", 3, "電腦", 4),
        ("資料結構", 3, "電腦", 5),
        ("勞作教育", 1, "一般", 6),
        ("體育", 2, "體育", 7),
        ("英文", 2, "一般", 8),
        ("通識課程", 2, "一般", 9),
    ]

    for class_obj in classes:
        for name, credits, r_type, t_idx in curriculum_pool:
            db.add(Course(
                name=name,
                credits=credits,
                room_type_required=r_type,
                teacher_id=teachers[t_idx].id,
                class_group_id=class_obj.id
            ))
    
    db.commit()
    print(f"✅ 成功匯入資通A班與B班共 {len(curriculum_pool)*2} 門課程！")
    db.close()

if __name__ == "__main__":
    init_mock_data()
