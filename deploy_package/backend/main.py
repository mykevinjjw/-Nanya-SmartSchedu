from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
import os
import time
import io
import csv
import uvicorn

# 匯入專案模組
from models import Teacher, Classroom, ClassGroup, Course, Base, Department, SystemSetting, course_class_association
from scheduler import CourseScheduler, SessionLocal, engine

app = FastAPI(title="大學自動排課系統")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# 初始化資料庫表 (帶重試機制)
def init_db():
    retries = 5
    while retries > 0:
        try:
            print(f"正在初始化資料庫... (剩餘重試次數: {retries})")
            Base.metadata.create_all(bind=engine)
            print("✅ 資料庫初始化成功！")
            return
        except Exception as e:
            print(f"❌ 資料庫初始化失敗: {e}")
            retries -= 1
            time.sleep(5)
    print("‼️ 無法連線至資料庫，請檢查 Docker 容器狀態。")

@app.on_event("startup")
async def startup_event():
    init_db()

# 掛載前端靜態檔案
frontend_paths = [
    "/app/frontend",
    "/frontend",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend"),
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
]

@app.get("/")
def read_root():
    for path in frontend_paths:
        index_file = os.path.join(path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
    
    tried_paths = [os.path.join(p, "index.html") for p in frontend_paths]
    return {
        "error": "找不到 index.html",
        "tried_paths": tried_paths,
        "current_workdir": os.getcwd()
    }

# 暫存最後一次排課結果與狀態
last_schedule_result = None
is_scheduling = False

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

class ImportSchema(BaseModel):
    teachers: List[dict]
    classrooms: List[dict]
    class_groups: List[dict]
    courses: List[dict]
    settings: Optional[dict] = None

def perform_bulk_import(data: ImportSchema, db: Session):
    db.execute(course_class_association.delete())
    db.query(Course).delete()
    db.query(ClassGroup).delete()
    db.query(Teacher).delete()
    db.query(Classroom).delete()
    db.query(Department).delete()
    db.query(SystemSetting).delete()
    
    dept = Department(name="預設系所")
    db.add(dept); db.flush()

    rooms_map = {}
    for r in data.classrooms:
        obj = Classroom(name=r['name'])
        db.add(obj); db.flush()
        rooms_map[r['name']] = obj.id
    
    teachers_map = {}
    for t in data.teachers:
        obj = Teacher(name=t['name'], 
                      is_director=t.get('is_director', False), department_id=dept.id)
        db.add(obj); db.flush()
        teachers_map[t['name']] = obj.id
        
    classes_map = {}
    for g in data.class_groups:
        obj = ClassGroup(name=g['name'], department_id=dept.id)
        db.add(obj); db.flush()
        classes_map[g['name']] = obj.id

    for c in data.courses:
        t_id = teachers_map.get(c['teacher_name'])
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
            name=c['name'], credits=c['credits'], classroom_id=r_id, teacher_id=t_id,
            fixed_day=c.get('fixed_day'), fixed_slot=c.get('fixed_slot'),
            allowed_slots=c.get('allowed_slots'), is_reserved=c.get('is_reserved', False),
            should_schedule=c.get('should_schedule', True)
        )
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
        text = payload.text
        if text.startswith('\ufeff'): text = text[1:]
        f = io.StringIO(text)
        reader = csv.reader(f)
        data = {"teachers": [], "classrooms": [], "class_groups": [], "courses": [], "settings": {}}
        for row in reader:
            if not row or not row[0]: continue
            rtype = row[0].lower().strip()
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
async def run_scheduler_api(background_tasks: BackgroundTasks):
    global last_schedule_result, is_scheduling
    if is_scheduling: return {"ok": False, "message": "排課任務正在執行中，請稍後。"}
    is_scheduling = True
    def task():
        global last_schedule_result, is_scheduling
        try:
            print("🚀 背景排課任務啟動...")
            scheduler = CourseScheduler()
            result = scheduler.solve()
            if result:
                last_schedule_result = result
                print("✅ 背景排課任務完成！")
            scheduler.db.close()
        except Exception as e:
            print(f"❌ 背景排課發生錯誤: {e}")
        finally:
            is_scheduling = False
    background_tasks.add_task(task)
    return {"ok": True, "message": "排課任務已在背景啟動，預計 1-3 分鐘內完成。"}

@app.get("/api/schedule")
def get_current_schedule(): 
    return {
        "is_scheduling": is_scheduling,
        "result": last_schedule_result if last_schedule_result else []
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)
