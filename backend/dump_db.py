import os
import json
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from models import Teacher, Classroom, ClassGroup, Course, Base

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:secretpassword@localhost:15432/course_schedule")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def dump_data():
    db = SessionLocal()
    data = {
        "teachers": [],
        "classes": [],
        "courses": []
    }
    
    for t in db.query(Teacher).all():
        data["teachers"].append({"id": t.id, "name": t.name, "is_director": t.is_director})
        
    for cl in db.query(ClassGroup).all():
        data["classes"].append({"id": cl.id, "name": cl.name})
        
    for c in db.query(Course).all():
        data["courses"].append({
            "id": c.id,
            "name": c.name,
            "teacher": c.teacher.name if c.teacher else None,
            "credits": c.credits,
            "classes": [cl.name for cl in c.classes],
            "should_schedule": c.should_schedule,
            "fixed": f"{c.fixed_day}-{c.fixed_slot}" if c.fixed_day is not None else None
        })
        
    with open("db_dump.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    db.close()
    print("Dumped to db_dump.json")

if __name__ == "__main__":
    dump_data()
