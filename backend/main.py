from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from models import Teacher, Classroom, ClassGroup, Course, Base, Department, SystemSetting, course_class_association
from scheduler import CourseScheduler, SessionLocal, engine
import uvicorn

Base.metadata.create_all(bind=engine)

app = FastAPI(title="大學自動排課系統")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# 暫存最後一次排課結果
last_schedule_result = None

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- Pydantic Models ---
class TeacherSchema(BaseModel):
    id: int; name: str; is_director: bool; title: str = "一般教師"
    class Config: from_attributes = True

class TeacherCreate(BaseModel):
    name: str; is_director: bool = False; title: str = "一般教師"

class ClassroomSchema(BaseModel):
    id: int; name: str; room_type: str
    class Config: from_attributes = True

class ClassroomCreate(BaseModel):
    name: str; room_type: str

class ClassGroupSchema(BaseModel):
    id: int; name: str; default_classroom_id: Optional[int] = None
    class Config: from_attributes = True

class ClassGroupCreate(BaseModel):
    name: str; default_classroom_id: Optional[int] = None

class CourseSchema(BaseModel):
    id: int; name: str; credits: int; teacher_id: int; room_type_required: str
    fixed_day: Optional[int] = None
    fixed_slot: Optional[int] = None
    allowed_slots: Optional[str] = None
    class_ids: List[int] = []
    class Config: from_attributes = True

class CourseCreate(BaseModel):
    name: str; credits: int; teacher_id: int; class_ids: List[int]; room_type_required: str
    fixed_day: Optional[int] = None
    fixed_slot: Optional[int] = None
    allowed_slots: Optional[str] = None

class SettingSchema(BaseModel):
    thursday_afternoon_off: bool; friday_all_day_off: bool; afternoon_force_start_slot5: bool
    ge_zone_day: int; ge_zone_slots: str; labor_slots: str
    director_off_day: int; director_off_slots: str
    midweek_limit_enabled: bool; midweek_allowed_slots: str

# --- API ---

@app.get("/api/data")
def get_all_data(db: Session = Depends(get_db)):
    setting = db.query(SystemSetting).first()
    if not setting:
        setting = SystemSetting()
        db.add(setting); db.commit(); db.refresh(setting)
    
    courses = []
    for c in db.query(Course).all():
        courses.append({
            "id": c.id, "name": c.name, "credits": c.credits, "teacher_id": c.teacher_id,
            "room_type_required": c.room_type_required, "fixed_day": c.fixed_day,
            "fixed_slot": c.fixed_slot, "allowed_slots": c.allowed_slots, "class_ids": c.class_ids
        })

    return {
        "teachers": db.query(Teacher).all(),
        "courses": courses,
        "classrooms": db.query(Classroom).all(),
        "class_groups": db.query(ClassGroup).all(),
        "settings": setting
    }

@app.put("/api/settings")
def update_settings(new_setting: SettingSchema, db: Session = Depends(get_db)):
    setting = db.query(SystemSetting).first()
    if not setting: setting = SystemSetting()
    for k, v in new_setting.dict().items(): setattr(setting, k, v)
    db.add(setting); db.commit(); return setting

@app.post("/api/teachers")
def create_teacher(teacher: TeacherCreate, db: Session = Depends(get_db)):
    obj = Teacher(**teacher.dict()); db.add(obj); db.commit(); db.refresh(obj); return obj

@app.put("/api/teachers/{id}")
def update_teacher(id: int, teacher: TeacherCreate, db: Session = Depends(get_db)):
    obj = db.query(Teacher).filter(Teacher.id == id).first()
    if not obj: raise HTTPException(404)
    obj.name = teacher.name; obj.is_director = teacher.is_director; obj.title = teacher.title
    db.commit(); return obj

@app.delete("/api/teachers/{id}")
def delete_teacher(id: int, db: Session = Depends(get_db)):
    db.query(Course).filter(Course.teacher_id == id).update({"teacher_id": None})
    db.query(Teacher).filter(Teacher.id == id).delete()
    db.commit(); return {"ok": True}

@app.post("/api/classrooms")
def create_classroom(room: ClassroomCreate, db: Session = Depends(get_db)):
    obj = Classroom(**room.dict()); db.add(obj); db.commit(); db.refresh(obj); return obj

@app.put("/api/classrooms/{id}")
def update_classroom(id: int, room: ClassroomCreate, db: Session = Depends(get_db)):
    obj = db.query(Classroom).filter(Classroom.id == id).first()
    if not obj: raise HTTPException(404)
    obj.name = room.name; obj.room_type = room.room_type
    db.commit(); return obj

@app.delete("/api/classrooms/{id}")
def delete_classroom(id: int, db: Session = Depends(get_db)):
    db.query(Classroom).filter(Classroom.id == id).delete()
    db.commit(); return {"ok": True}

@app.post("/api/class_groups")
def create_class_group(cg: ClassGroupCreate, db: Session = Depends(get_db)):
    dept = db.query(Department).first()
    obj = ClassGroup(name=cg.name, department_id=dept.id if dept else 1, default_classroom_id=cg.default_classroom_id)
    db.add(obj); db.commit(); db.refresh(obj); return obj

@app.put("/api/class_groups/{id}")
def update_class_group(id: int, cg: ClassGroupCreate, db: Session = Depends(get_db)):
    obj = db.query(ClassGroup).filter(ClassGroup.id == id).first()
    if not obj: raise HTTPException(404)
    obj.name = cg.name; obj.default_classroom_id = cg.default_classroom_id
    db.commit(); return obj

@app.delete("/api/class_groups/{id}")
def delete_class_group(id: int, db: Session = Depends(get_db)):
    db.execute(course_class_association.delete().where(course_class_association.c.class_group_id == id))
    db.query(ClassGroup).filter(ClassGroup.id == id).delete()
    db.commit(); return {"ok": True}

@app.post("/api/courses")
def create_course(course: CourseCreate, db: Session = Depends(get_db)):
    data = course.dict()
    class_ids = data.pop('class_ids')
    obj = Course(**data)
    obj.classes = db.query(ClassGroup).filter(ClassGroup.id.in_(class_ids)).all()
    db.add(obj); db.commit(); db.refresh(obj); return obj

@app.put("/api/courses/{id}")
def update_course(id: int, course: CourseCreate, db: Session = Depends(get_db)):
    obj = db.query(Course).filter(Course.id == id).first()
    if not obj: raise HTTPException(404)
    data = course.dict()
    class_ids = data.pop('class_ids')
    for k, v in data.items(): setattr(obj, k, v)
    obj.classes = db.query(ClassGroup).filter(ClassGroup.id.in_(class_ids)).all()
    db.commit(); return obj

@app.delete("/api/courses/{id}")
def delete_course(id: int, db: Session = Depends(get_db)):
    db.execute(course_class_association.delete().where(course_class_association.c.course_id == id))
    db.query(Course).filter(Course.id == id).delete()
    db.commit(); return {"ok": True}

@app.post("/api/run-scheduler")
def run_scheduler_api():
    global last_schedule_result
    scheduler = CourseScheduler()
    result = scheduler.solve()
    if result is None: return {"error": "無法在現有限制下找到可行解"}
    last_schedule_result = result
    scheduler.db.close()
    return result

@app.get("/api/schedule")
def get_current_schedule(): 
    return last_schedule_result if last_schedule_result else []

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000)
