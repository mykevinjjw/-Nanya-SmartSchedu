from ortools.sat.python import cp_model
from sqlalchemy.orm import sessionmaker, joinedload
from sqlalchemy import create_engine
from models import Teacher, Classroom, ClassGroup, Course, Base, SystemSetting
import collections

# 資料庫連線
DATABASE_URL = "postgresql://admin:secretpassword@localhost:15432/course_schedule"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# 常數設定
DAYS = 5
SLOTS_PER_DAY = 8
TOTAL_SLOTS = DAYS * SLOTS_PER_DAY

class CourseScheduler:
    def __init__(self):
        self.db = SessionLocal()
        self.load_data()

    def load_data(self):
        self.teachers = self.db.query(Teacher).all()
        self.classrooms = self.db.query(Classroom).all()
        self.class_groups = self.db.query(ClassGroup).all()
        self.courses = self.db.query(Course).options(joinedload(Course.classes), joinedload(Course.teacher)).all()
        self.setting = self.db.query(SystemSetting).first()
        if not self.setting:
            self.setting = SystemSetting()
        
        # 動態解析設定
        self.ge_day = self.setting.ge_zone_day
        self.ge_slots = [int(s)-1 for s in self.setting.ge_zone_slots.split(',')]
        self.midweek_allowed = [int(s)-1 for s in self.setting.midweek_allowed_slots.split(',')]
        self.dir_off_slots = [int(s)-1 for s in self.setting.director_off_slots.split(',')]
        
    def solve(self):
        print(f"DEBUG: 正在為 {len(self.courses)} 門課程進行排課運算...")
        model = cp_model.CpModel()
        course_vars = {}
        ge_zone_indices = [self.ge_day * SLOTS_PER_DAY + s for s in self.ge_slots]
        
        obj_bool_vars = []
        obj_weights = []

        for c in self.courses:
            duration = c.credits
            allowed_starts = []
            is_ge = "通識" in c.name
            
            # 讀取課程自身的容許節次 (取代全域勞作邏輯)
            course_allowed_slots = [int(s)-1 for s in c.allowed_slots.split(',')] if c.allowed_slots else None

            for d in range(DAYS):
                for s in range(SLOTS_PER_DAY - duration + 1):
                    t_idx = d * SLOTS_PER_DAY + s
                    occupied = list(range(t_idx, t_idx + duration))
                    slots_in_day = [slot % 8 for slot in occupied]
                    
                    # 1. 通識強制約束
                    if is_ge:
                        if d != self.ge_day or any(s_in_d not in self.ge_slots for s_in_d in slots_in_day):
                            continue
                    else:
                        if any(slot in ge_zone_indices for slot in occupied):
                            continue

                    # 2. 課程個別化限制
                    if course_allowed_slots:
                        if any(s_in_d not in course_allowed_slots for s_in_d in slots_in_day):
                            continue
                    else:
                        # 3. 節次限制 (僅針對一般課程，且排除已有個別限制者)
                        if self.setting.midweek_limit_enabled:
                            if not (d == 0): # 週二至週五
                                if any(s_in_d not in self.midweek_allowed for s_in_d in slots_in_day):
                                    continue
                    
                    # 4. 禁排與主任限制
                    if self.setting.thursday_afternoon_off and d == 3 and any(s_in_d >= 4 for s_in_d in slots_in_day):
                        continue
                    if self.setting.friday_all_day_off and d == 4: continue
                    # --- E. 系主任週二禁排 ---
                    if c.teacher and c.teacher.is_director and d == self.setting.director_off_day and any(s_in_d in self.dir_off_slots for s_in_d in slots_in_day):
                        continue

                    # --- F. 禁止跨越 4, 5 節 (午休隔斷) ---
                    # 如果課程起始於第 4 節之前(s<4)，但結束於第 4 節之後(s+duration > 4)，則視為跨越中午
                    if s < 4 and s + duration > 4:
                        continue

                    allowed_starts.append(t_idx)

            if not allowed_starts:
                print(f"!!! 警告：課程 {c.name} ({duration}節) 找不到合法起始點")
                continue

            time_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(allowed_starts), f't_{c.id}')
            
            # --- 【希望起始時段】軟限制 ---
            if c.fixed_day and c.fixed_slot:
                target_t = (c.fixed_day - 1) * SLOTS_PER_DAY + (c.fixed_slot - 1)
                if target_t in allowed_starts:
                    is_at_preferred = model.NewBoolVar(f'pref_{c.id}')
                    model.Add(time_var == target_t).OnlyEnforceIf(is_at_preferred)
                    model.Add(time_var != target_t).OnlyEnforceIf(is_at_preferred.Not())
                    obj_bool_vars.append(is_at_preferred)
                    obj_weights.append(1000)

            valid_rooms = [r.id for r in self.classrooms if r.room_type == c.room_type_required]
            if not valid_rooms: valid_rooms = [r.id for r in self.classrooms]
            room_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(valid_rooms), f'r_{c.id}')
            interval_var = model.NewIntervalVar(time_var, duration, time_var + duration, f'i_{c.id}')
            
            course_vars[c.id] = {
                "course": c, "time": time_var, "room": room_var, "interval": interval_var, "duration": duration
            }

        # 衝突檢查 (老師、班級、教室)
        teacher_intervals = collections.defaultdict(list)
        class_group_intervals = collections.defaultdict(list)
        for cv in course_vars.values():
            teacher_intervals[cv['course'].teacher_id].append(cv['interval'])
            for class_obj in cv['course'].classes:
                class_group_intervals[class_obj.id].append(cv['interval'])

        for t_ints in teacher_intervals.values(): model.AddNoOverlap(t_ints)
        for cg_ints in class_group_intervals.values(): model.AddNoOverlap(cg_ints)

        cv_list = list(course_vars.values())
        for i in range(len(cv_list)):
            for j in range(i + 1, len(cv_list)):
                v1, v2 = cv_list[i], cv_list[j]
                same_room = model.NewBoolVar(f'sr_{v1["course"].id}_{v2["course"].id}')
                model.Add(v1['room'] == v2['room']).OnlyEnforceIf(same_room)
                model.Add(v1['room'] != v2['room']).OnlyEnforceIf(same_room.Not())
                model.AddNoOverlap([v1['interval'], v2['interval']]).OnlyEnforceIf(same_room)

        # 加分目標
        if obj_bool_vars:
            model.Maximize(sum(obj_bool_vars[i] * obj_weights[i] for i in range(len(obj_bool_vars))))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 15.0
        status = solver.Solve(model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            print(f"成功找到方案！")
            final_res = []
            for cv in course_vars.values():
                room_name = next(r.name for r in self.classrooms if r.id == solver.Value(cv['room']))
                for class_obj in cv['course'].classes:
                    final_res.append({
                        "course_name": cv['course'].name,
                        "class_name": class_obj.name,
                        "teacher_name": cv['course'].teacher.name if cv['course'].teacher else "無",
                        "room_name": room_name,
                        "day": solver.Value(cv['time']) // 8,
                        "slot": (solver.Value(cv['time']) % 8) + 1,
                        "duration": cv['duration']
                    })
            return final_res
        print("!!! 求解失敗：無可行解")
        return None

if __name__ == "__main__":
    scheduler = CourseScheduler()
    res = scheduler.solve()
    if res: print(f"成功排定 {len(res)} 門課程。")
    scheduler.db.close()
