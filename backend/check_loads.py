from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from models import Teacher, Classroom, ClassGroup, Course, Base
import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:secretpassword@localhost:15432/course_schedule")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def check_loads():
    db = SessionLocal()
    print("--- Class Loads ---")
    classes = db.query(ClassGroup).all()
    for cl in classes:
        load = sum(c.credits for c in cl.courses if c.should_schedule)
        print(f"Class: {cl.name}, Load: {load} hours")
    
    print("\n--- Teacher Loads ---")
    teachers = db.query(Teacher).all()
    for t in teachers:
        load = sum(c.credits for c in t.courses if c.should_schedule)
        if load > 0:
            print(f"Teacher: {t.name}, Load: {load} hours")
            
    pc_courses = db.query(Course).filter(Course.should_schedule == True, Course.note.like('%電腦%')).all()
    total_pc_hours = sum(c.credits for c in pc_courses)
    print(f"\nTotal PC Courses: {len(pc_courses)}, Total PC Hours: {total_pc_hours}")
    
    db.close()

if __name__ == "__main__":
    check_loads()
