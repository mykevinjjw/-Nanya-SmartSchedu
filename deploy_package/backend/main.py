from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import os

# 匯入專案模組
from models import Teacher, Classroom, ClassGroup, Course, Base, Department, SystemSetting, course_class_association
from scheduler import CourseScheduler, SessionLocal, engine
import uvicorn

# 初始化資料庫表
Base.metadata.create_all(bind=engine)

app = FastAPI(title="大學自動排課系統")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# 掛載前端靜態檔案
# 取得目前檔案路徑 (backend/) 的上一層，再進入 frontend
current_dir = os.path.dirname(os.path.abspath(__file__))
frontend_path = os.path.join(os.path.dirname(current_dir), "frontend")

@app.get("/")
def read_root():
    index_file = os.path.join(frontend_path, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"error": f"index.html not found at {index_file}"}

# 暫存最後一次排課結果
last_schedule_result = None

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

# --- Pydantic Models ---
class TeacherSchema(BaseModel):
    id: int; name: str; is_director: bool
    class Config: from_attributes = True

class TeacherCreate(BaseModel):
    name: str; is_director: bool = False

class ClassroomSchema(BaseModel):
    id: int; name: str
    class Config: from_attributes = True

class ClassroomCreate(BaseModel):
    name: str

class ClassGroupSchema(BaseModel):
    id: int; name: str
    class Config: from_attributes = True

class ClassGroupCreate(BaseModel):
    name: str

class CourseSchema(BaseModel):
    id: int; name: str; credits: int; teacher_id: int; classroom_id: Optional[int] = None
    fixed_day: Optional[int] = None
    fixed_slot: Optional[int] = None
    allowed_slots: Optional[str] = None
    class_ids: List[int] = []
    is_reserved: bool = False
    should_schedule: bool = True
    class Config: from_attributes = True

class CourseCreate(BaseModel):
    name: str; credits: int; teacher_id: int; class_ids: List[int]; classroom_id: Optional[int] = None
    fixed_day: Optional[int] = None
    fixed_slot: Optional[int] = None
    allowed_slots: Optional[str] = None
    is_reserved: bool = False
    should_schedule: bool = True

class SettingSchema(BaseModel):
    thursday_afternoon_off: bool; friday_all_day_off: bool; afternoon_force_start_slot5: bool
    ge_zone_day: int; ge_zone_slots: str; labor_slots: str
    director_off_day: int; director_off_slots: str
    midweek_limit_enabled: bool; midweek_allowed_slots: str

# --- API ---

import io
import csv

class ImportSchema(BaseModel):
    teachers: List[dict]
    classrooms: List[dict]
    class_groups: List[dict]
    courses: List[dict]
    settings: Optional[dict] = None

def perform_bulk_import(data: ImportSchema, db: Session):
    # 1. 清空現有資料 (按照關聯順序)
    db.execute(course_class_association.delete())
    db.query(Course).delete()
    db.query(ClassGroup).delete()
    db.query(Teacher).delete()
    db.query(Classroom).delete()
    db.query(Department).delete()
    db.query(SystemSetting).delete()
    
    # 建立預設系所
    dept = Department(name="預設系所")
    db.add(dept); db.flush()

    # 2. 匯入教室
    rooms_map = {}
    for r in data.classrooms:
        obj = Classroom(name=r['name'])
        db.add(obj); db.flush()
        rooms_map[r['name']] = obj.id
    
    # 3. 匯入老師
    teachers_map = {}
    for t in data.teachers:
        obj = Teacher(name=t['name'], 
                      is_director=t.get('is_director', False), department_id=dept.id)
        db.add(obj); db.flush()
        teachers_map[t['name']] = obj.id
        
    # 4. 匯入班級
    classes_map = {}
    for g in data.class_groups:
        obj = ClassGroup(name=g['name'], department_id=dept.id)
        db.add(obj); db.flush()
        classes_map[g['name']] = obj.id

    # 5. 匯入課程
    for c in data.courses:
        t_id = teachers_map.get(c['teacher_name'])
        
        # 教室自動識別邏輯
        r_name = c.get('classroom_name')
        r_id = None
        if r_name:
            r_name = r_name.strip()
            if r_name not in rooms_map:
                new_room = Classroom(name=r_name)
                db.add(new_room); db.flush()
                rooms_map[r_name] = new_room.id
            r_id = rooms_map[r_name]

        obj = Course(
            name=c['name'], 
            credits=c['credits'], 
            classroom_id=r_id,
            teacher_id=t_id,
            fixed_day=c.get('fixed_day'),
            fixed_slot=c.get('fixed_slot'),
            allowed_slots=c.get('allowed_slots'),
            is_reserved=c.get('is_reserved', False),
            should_schedule=c.get('should_schedule', True)
        )
        # 關聯班級 (支援逗號或垂直線分隔)
        c_classes = []
        raw_class_names = c.get('class_names', [])
        if isinstance(raw_class_names, str):
            raw_class_names = raw_class_names.replace(',', '|').split('|')
        
        for name in raw_class_names:
            name = name.strip()
            if name in classes_map:
                target = db.query(ClassGroup).filter(ClassGroup.id == classes_map[name]).first()
                if target: c_classes.append(target)
        obj.classes = c_classes
        db.add(obj)
        
    # 6. 匯入設定
    s = data.settings or {}
    setting = SystemSetting(
        thursday_afternoon_off=s.get('thursday_afternoon_off', True),
        friday_all_day_off=s.get('friday_all_day_off', True),
        ge_zone_day=s.get('ge_zone_day', 0),
        ge_zone_slots=s.get('ge_zone_slots', "5,6,7,8"),
        labor_slots=s.get('labor_slots', "1,8"),
        director_off_day=s.get('director_off_day', 1),
        director_off_slots=s.get('director_off_slots', "1,2,3,4"),
        midweek_limit_enabled=s.get('midweek_limit_enabled', True),
        midweek_allowed_slots=s.get('midweek_allowed_slots', "2,3,4,5,6,7")
    )
    db.add(setting)
    db.commit()

# --- API ---

@app.post("/api/import")
def bulk_import(data: ImportSchema, db: Session = Depends(get_db)):
    try:
        perform_bulk_import(data, db)
        return {"ok": True, "message": "資料已全數重新匯入"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

class CSVTextSchema(BaseModel):
    text: str

@app.post("/api/import-csv")
def import_csv(payload: CSVTextSchema, db: Session = Depends(get_db)):
    try:
        # 移除可能存在的 BOM 字元
        text = payload.text
        if text.startswith('\ufeff'):
            text = text[1:]
        
        f = io.StringIO(text)
        reader = csv.reader(f)
        data = {"teachers": [], "classrooms": [], "class_groups": [], "courses": [], "settings": {}}
        for row in reader:
            if not row or not row[0]: continue
            rtype = row[0].lower().strip()
            # 支援中英文類別名稱
            if rtype in ['teacher', '老師']:
                data['teachers'].append({"name": row[1], "is_director": row[2].lower() in ['true', '是']})
            elif rtype in ['classroom', '教室']:
                data['classrooms'].append({"name": row[1], "room_type": row[2]})
            elif rtype in ['class', '班級']:
                data['class_groups'].append({"name": row[1]})
            elif rtype in ['course', '課程']:
                data['courses'].append({
                    "name": row[1], "credits": int(row[2]), "teacher_name": row[3],
                    "class_names": row[4], "classroom_name": row[5],
                    "fixed_day": int(row[6]) if (len(row)>6 and row[6]) else None,
                    "fixed_slot": int(row[7]) if (len(row)>7 and row[7]) else None,
                    "allowed_slots": row[8] if (len(row)>8 and row[8]) else None
                })
        
        perform_bulk_import(ImportSchema(**data), db)
        return {"ok": True, "message": "CSV 資料已順利匯入"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"CSV 解析錯誤: {str(e)}")

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
            "classroom_id": c.classroom_id, "fixed_day": c.fixed_day,
            "fixed_slot": c.fixed_slot, "allowed_slots": c.allowed_slots, "class_ids": c.class_ids,
            "is_reserved": c.is_reserved, "should_schedule": c.should_schedule
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
    obj.name = teacher.name; obj.is_director = teacher.is_director
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
    obj = ClassGroup(name=cg.name, department_id=dept.id if dept else 1)
    db.add(obj); db.commit(); db.refresh(obj); return obj

@app.put("/api/class_groups/{id}")
def update_class_group(id: int, cg: ClassGroupCreate, db: Session = Depends(get_db)):
    obj = db.query(ClassGroup).filter(ClassGroup.id == id).first()
    if not obj: raise HTTPException(404)
    obj.name = cg.name
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
    uvicorn.run(app, host="0.0.0.0", port=9000)
