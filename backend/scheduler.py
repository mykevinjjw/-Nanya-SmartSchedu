from ortools.sat.python import cp_model
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from models import Teacher, Classroom, ClassGroup, Course
import collections

# 資料庫連線
DATABASE_URL = "sqlite:///backend/course_schedule.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

# 常數設定
DAYS = 5
SLOTS_PER_DAY = 8
TOTAL_SLOTS = DAYS * SLOTS_PER_DAY

# 限制時段定義 (索引 0-39)
# 週一: 0-7, 週二: 8-15, 週三: 16-23, 週四: 24-31, 週五: 32-39
TUESDAY_MORNING = [8, 9, 10, 11]      # 週二 1-4 節
GE_ZONE = [4, 5, 6, 7]                # 週一 5-8 節 (通識專屬)
THURSDAY_AFTERNOON = [28, 29, 30, 31] # 週四第 5-8 節 (嚴禁排課)
FRIDAY_ALL_DAY = list(range(32, 40))   # 週五全天 (嚴禁排課)

class CourseScheduler:
    def __init__(self):
        from models import Base
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.load_data()

    def load_data(self):
        self.teachers = self.db.query(Teacher).all()
        self.classrooms = self.db.query(Classroom).all()
        self.class_groups = self.db.query(ClassGroup).all()
        self.courses = self.db.query(Course).all()
        
    def solve(self):
        model = cp_model.CpModel()
        course_vars = {}

        for c in self.courses:
            duration = c.credits
            is_ge = "通識" in c.name
            
            allowed_starts = []
            for d in range(DAYS):
                for s in range(SLOTS_PER_DAY - duration + 1):
                    t_idx = d * SLOTS_PER_DAY + s
                    # 該課程佔用的所有節次索引
                    occupied_slots = list(range(t_idx, t_idx + duration))
                    
                    # 1. 嚴禁排入週五全天或週四下午
                    if any(slot in FRIDAY_ALL_DAY or slot in THURSDAY_AFTERNOON for slot in occupied_slots):
                        continue
                    
                    # 2. 通識課程限制
                    if is_ge:
                        # 通識課「必須」完全在週一 5-8 節
                        if not all(slot in GE_ZONE for slot in occupied_slots):
                            continue
                    else:
                        # 其他課「禁止」進入週一 5-8 節
                        if any(slot in GE_ZONE for slot in occupied_slots):
                            continue

                    # 3. 系主任限制 (週二 1-4 節)
                    if c.teacher.is_director and any(slot in TUESDAY_MORNING for slot in occupied_slots):
                        continue
                    
                    # 4. 勞作教育限制：僅限第 1 節 或 第 8 節
                    # 5. 其他課程限制：禁止佔用第 1 節 (必須從第二節開始)
                    if "勞作教育" in c.name:
                        start_slot_in_day = (t_idx % SLOTS_PER_DAY) + 1
                        if start_slot_in_day not in [1, 8]:
                            continue
                    else:
                        # 非勞作教育課程，所佔用的任何一節都不能是第 1 節
                        # 也就是說，這門課的任何一個 slot % 8 都不可以等於 0
                        if any((slot % SLOTS_PER_DAY) == 0 for slot in occupied_slots):
                            continue

                    allowed_starts.append(t_idx)

            if not allowed_starts:
                print(f"警告：課程 {c.name} 找不到合法時段")
                continue

            time_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(allowed_starts), f't_{c.id}')
            
            valid_rooms = [r.id for r in self.classrooms if r.room_type == c.room_type_required]
            if not valid_rooms: valid_rooms = [r.id for r in self.classrooms]
            room_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(valid_rooms), f'r_{c.id}')
            
            interval_var = model.NewIntervalVar(time_var, duration, time_var + duration, f'i_{c.id}')
            
            course_vars[c.id] = {
                "course": c, "time": time_var, "room": room_var, 
                "interval": interval_var, "duration": duration
            }

        # 硬限制：教師、班級不衝堂
        teacher_map = collections.defaultdict(list)
        class_map = collections.defaultdict(list)
        
        # 輔助變數：確保下午課程從第 5 節開始
        afternoon_active = {}

        for cv in course_vars.values():
            teacher_map[cv['course'].teacher_id].append(cv['interval'])
            class_map[cv['course'].class_group_id].append(cv['interval'])
            
            cg_id = cv['course'].class_group_id
            for d in range(DAYS):
                if (cg_id, d) not in afternoon_active:
                    afternoon_active[(cg_id, d)] = {
                        "has_afternoon": model.NewBoolVar(f'aft_{cg_id}_{d}'),
                        "s5_occupied": model.NewBoolVar(f's5_{cg_id}_{d}')
                    }
                
                # 判斷這門課是否在該天
                is_this_day = model.NewBoolVar(f'd_{cv["course"].id}_{d}')
                day_start = d * SLOTS_PER_DAY
                day_end = (d + 1) * SLOTS_PER_DAY - 1
                
                # 建立兩個輔助變數來表示是否在區間內
                after_start = model.NewBoolVar(f'ge_{cv["course"].id}_{d}')
                before_end = model.NewBoolVar(f'le_{cv["course"].id}_{d}')
                model.Add(cv['time'] >= day_start).OnlyEnforceIf(after_start)
                model.Add(cv['time'] < day_start).OnlyEnforceIf(after_start.Not())
                model.Add(cv['time'] <= day_end).OnlyEnforceIf(before_end)
                model.Add(cv['time'] > day_end).OnlyEnforceIf(before_end.Not())
                
                model.AddBoolAnd([after_start, before_end]).OnlyEnforceIf(is_this_day)
                model.AddBoolOr([after_start.Not(), before_end.Not()]).OnlyEnforceIf(is_this_day.Not())
                
                # 判斷是否佔用第 5 節 (index 4)
                start_in_day = model.NewIntVar(0, SLOTS_PER_DAY - 1, f'sid_{cv["course"].id}_{d}')
                model.AddModuloEquality(start_in_day, cv['time'], SLOTS_PER_DAY)
                
                is_s5 = model.NewBoolVar(f'iss5_{cv["course"].id}_{d}')
                # condition: start <= 4 AND start + duration > 4
                c1 = model.NewBoolVar(f'c1_{cv["course"].id}_{d}')
                c2 = model.NewBoolVar(f'c2_{cv["course"].id}_{d}')
                model.Add(start_in_day <= 4).OnlyEnforceIf(c1)
                model.Add(start_in_day > 4).OnlyEnforceIf(c1.Not())
                model.Add(start_in_day + cv['duration'] > 4).OnlyEnforceIf(c2)
                model.Add(start_in_day + cv['duration'] <= 4).OnlyEnforceIf(c2.Not())
                model.AddBoolAnd([c1, c2, is_this_day]).OnlyEnforceIf(is_s5)
                model.AddBoolOr([c1.Not(), c2.Not(), is_this_day.Not()]).OnlyEnforceIf(is_s5.Not())
                
                model.Add(afternoon_active[(cg_id, d)]['s5_occupied'] == 1).OnlyEnforceIf(is_s5)
                
                # 判斷是否佔用下午 (index 4,5,6,7)
                is_aft = model.NewBoolVar(f'isaft_{cv["course"].id}_{d}')
                # 如果這門課在該天，且結束時間 > 4 (第 5 節或之後)
                # 使用 >= 5 來表示結束時間 (start + duration)
                afternoon_end = model.NewBoolVar(f'aft_e_{cv["course"].id}_{d}')
                model.Add(start_in_day + cv['duration'] >= 5).OnlyEnforceIf(afternoon_end)
                model.Add(start_in_day + cv['duration'] < 5).OnlyEnforceIf(afternoon_end.Not())
                
                model.AddBoolAnd([afternoon_end, is_this_day]).OnlyEnforceIf(is_aft)
                model.AddBoolOr([afternoon_end.Not(), is_this_day.Not()]).OnlyEnforceIf(is_aft.Not())
                
                model.Add(afternoon_active[(cg_id, d)]['has_afternoon'] == 1).OnlyEnforceIf(is_aft)

        # 限制：如果有下午課，第 5 節 (Slot 5) 必須被佔用
        for key, info in afternoon_active.items():
            model.Add(info['s5_occupied'] == 1).OnlyEnforceIf(info['has_afternoon'])

        for ints in teacher_map.values(): model.AddNoOverlap(ints)
        for ints in class_map.values(): model.AddNoOverlap(ints)

        # 教室不衝堂
        cv_list = list(course_vars.values())
        for i in range(len(cv_list)):
            for j in range(i + 1, len(cv_list)):
                v1, v2 = cv_list[i], cv_list[j]
                same_room = model.NewBoolVar(f'sr_{i}_{j}')
                model.Add(v1['room'] == v2['room']).OnlyEnforceIf(same_room)
                model.Add(v1['room'] != v2['room']).OnlyEnforceIf(same_room.Not())
                model.AddNoOverlap([v1['interval'], v2['interval']]).OnlyEnforceIf(same_room)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10.0
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            return [{
                "course_id": v['course'].id,
                "course_name": v['course'].name,
                "teacher_name": v['course'].teacher.name,
                "class_group_id": v['course'].class_group_id,
                "class_name": v['course'].class_group.name,
                "room_name": next(r.name for r in self.classrooms if r.id == solver.Value(v['room'])),
                "time_slot": solver.Value(v['time']),
                "day": solver.Value(v['time']) // SLOTS_PER_DAY,
                "slot": (solver.Value(v['time']) % SLOTS_PER_DAY) + 1,
                "duration": v['duration']
            } for v in course_vars.values()]
        return None
