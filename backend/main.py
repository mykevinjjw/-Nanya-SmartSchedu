from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from models import Teacher, Classroom, ClassGroup, Course, Base, Department
from scheduler import CourseScheduler, SessionLocal, engine
import uvicorn

Base.metadata.create_all(bind=engine)

app = FastAPI(title="大學自動排課系統")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- Models ---
class TeacherSchema(BaseModel):
    id: int
    name: str
    is_director: bool
    title: str = "一般教師" # 新增職稱
    class Config: from_attributes = True

class TeacherCreate(BaseModel):
    name: str
    is_director: bool = False
    title: str = "一般教師"

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
    id: int; name: str; credits: int; teacher_id: int; class_group_id: int; room_type_required: str
    class Config: from_attributes = True

class CourseCreate(BaseModel):
    name: str; credits: int; teacher_id: int; class_group_id: int; room_type_required: str

# --- API ---
@app.get("/api/data")
def get_all_data(db: Session = Depends(get_db)):
    return {"teachers": db.query(Teacher).all(), "courses": db.query(Course).all(), "classrooms": db.query(Classroom).all(), "class_groups": db.query(ClassGroup).all()}

@app.post("/api/teachers")
def create_teacher(teacher: TeacherCreate, db: Session = Depends(get_db)):
    obj = Teacher(**teacher.dict())
    db.add(obj); db.commit(); db.refresh(obj); return obj

@app.put("/api/teachers/{id}")
def update_teacher(id: int, teacher: TeacherCreate, db: Session = Depends(get_db)):
    obj = db.query(Teacher).filter(Teacher.id == id).first()
    if not obj: raise HTTPException(404)
    obj.name = teacher.name; obj.is_director = teacher.is_director; obj.title = teacher.title
    db.commit(); return obj

@app.delete("/api/teachers/{id}")
def delete_teacher(id: int, db: Session = Depends(get_db)):
    db.query(Teacher).filter(Teacher.id == id).delete(); db.commit(); return {"ok": True}

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
    db.query(Classroom).filter(Classroom.id == id).delete(); db.commit(); return {"ok": True}

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
    db.query(ClassGroup).filter(ClassGroup.id == id).delete(); db.commit(); return {"ok": True}

@app.post("/api/courses")
def create_course(course: CourseCreate, db: Session = Depends(get_db)):
    obj = Course(**course.dict()); db.add(obj); db.commit(); db.refresh(obj); return obj

@app.put("/api/courses/{id}")
def update_course(id: int, course: CourseCreate, db: Session = Depends(get_db)):
    obj = db.query(Course).filter(Course.id == id).first()
    if not obj: raise HTTPException(404)
    for k, v in course.dict().items(): setattr(obj, k, v)
    db.commit(); return obj

@app.delete("/api/courses/{id}")
def delete_course(id: int, db: Session = Depends(get_db)):
    db.query(Course).filter(Course.id == id).delete(); db.commit(); return {"ok": True}

@app.post("/api/run-scheduler")
def run_scheduler_api():
    scheduler = CourseScheduler()
    return scheduler.solve()

@app.get("/api/schedule")
def get_current_schedule():
    return []

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=9000)
