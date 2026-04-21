from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base, Department, Teacher, Classroom, ClassGroup, Course

DATABASE_URL = "sqlite:///backend/course_schedule.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

def init_mock_data():
    # 重新建立資料表（這會清空舊資料）
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    print("正在還原原始資料庫...")

    dept = Department(name="資通工程系")
    db.add(dept)
    db.commit()

    # 原始老師資料
    teachers = [
        Teacher(name="系主任", is_director=True, department_id=dept.id), # 1
        Teacher(name="李教授", department_id=dept.id), # 2
        Teacher(name="陳副教授", department_id=dept.id), # 3
        Teacher(name="黃老師", department_id=dept.id), # 4
        Teacher(name="趙教授", department_id=dept.id), # 5
        Teacher(name="孫老師", department_id=dept.id), # 6
        Teacher(name="郭老師A", department_id=dept.id), # 7
        Teacher(name="郭老師B", department_id=dept.id), # 8
    ]
    db.add_all(teachers)
    db.commit()

    # 原始教室資料
    rooms = [
        Classroom(name="101普通教室", room_type="一般"),
        Classroom(name="102普通教室", room_type="一般"),
        Classroom(name="電腦教室A", room_type="電腦"),
        Classroom(name="電腦教室B", room_type="電腦"),
        Classroom(name="體育館", room_type="體育"),
        Classroom(name="專題研討室", room_type="專題"),
    ]
    db.add_all(rooms)
    db.commit()

    # 原始班級資料 (並附上預設教室)
    classes = [
        ClassGroup(name="資通A班", department_id=dept.id, default_classroom_id=rooms[0].id),
        ClassGroup(name="資通B班", department_id=dept.id, default_classroom_id=rooms[1].id)
    ]
    db.add_all(classes)
    db.commit()

    # 原始課程資料
    curriculum_pool = [
        ("計算機概論", 3, "電腦", 0),
        ("作業系統實務", 3, "電腦", 1),
        ("實務專題", 3, "專題", 0),
        ("微積分", 3, "一般", 2),
        ("資料結構", 3, "電腦", 3),
        ("勞作教育", 1, "一般", 4),
        ("體育", 2, "體育", 5),
    ]

    for class_obj in classes:
        for name, credits, r_type, t_idx in curriculum_pool:
            db.add(Course(name=name, credits=credits, room_type_required=r_type, teacher_id=teachers[t_idx].id, class_group_id=class_obj.id))
        
        # 通識課程
        t_ge = teachers[6] if class_obj.name == "資通A班" else teachers[7]
        db.add(Course(name="通識課程", credits=4, room_type_required="一般", teacher_id=t_ge.id, class_group_id=class_obj.id))
    
    db.commit()
    print("✅ 原始資料已成功還原！")
    db.close()

if __name__ == "__main__":
    init_mock_data()
