from ortools.sat.python import cp_model
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from models import Teacher, Classroom, ClassGroup, Course, Base, SystemSetting
import collections
import os
import json

# 資料庫連線
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:secretpassword@localhost:15432/course_schedule")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# 常數設定
DAYS = 5
SLOTS_PER_DAY = 9

class CourseScheduler:
    def __init__(self):
        self.db = SessionLocal()
        self.load_data()

    def load_data(self):
        print("  [Step 1] 讀取資料庫資料...", flush=True)
        self.teachers = self.db.query(Teacher).all()
        self.classrooms = self.db.query(Classroom).all()
        self.class_groups = self.db.query(ClassGroup).all()
        self.courses = self.db.query(Course).all()
        self.setting = self.db.query(SystemSetting).first() or SystemSetting()
        print(f"  資料載入完成: {len(self.courses)} 門課程", flush=True)

    def solve(self):
        print(f"DEBUG: 執行 115-1 效能優化版排課引擎...", flush=True)
        model = cp_model.CpModel()
        course_vars = {}
        
        # 過濾幽靈班級
        for c in self.courses:
            c.classes = [cl for cl in c.classes if cl.name not in ["---", "學制年級"]]
            
        # 1. 預算負載
        cl_loads = collections.defaultdict(int)
        for c in self.courses:
            if not c.should_schedule: continue
            for cl in c.classes:
                cl_loads[cl.id] += c.credits
        
        print("  [DEBUG] 各班級負載情況:")
        pc_count = 0
        for c in self.courses:
            if not c.should_schedule: continue
            if (c.note and "電腦" in c.note) or "電腦" in c.name:
                pc_count += 1
        print(f"  [DEBUG] 電腦課程總數: {pc_count}")
        for cl in self.class_groups:
            print(f"    - {cl.name}: {cl_loads[cl.id]} 小時")

        # 2. 教室池設定
        pc_names = ["C407", "C501", "F301", "F302", "F317", "F407", "F409"]
        gen_names = ["C405", "C501", "C502"]
        rooms_pc = [r for r in self.classrooms if r.name in pc_names]
        rooms_gen = [r for r in self.classrooms if r.name in gen_names]
        rooms_all = [r for r in self.classrooms if r.name in (pc_names + gen_names)]
        
        room_gym = next((r for r in self.classrooms if "體育" in r.name or r.name == "體育館"), None)
        room_drone = next((r for r in self.classrooms if "無人機" in r.name or r.name == "無人機實作場"), None)

        # 智慧放寬機制：計算各設定下的可用節次
        midweek_limit = self.setting.midweek_limit_enabled
        midweek_slots = [int(x) for x in self.setting.midweek_allowed_slots.split(',')] if self.setting.midweek_allowed_slots else [2, 3, 4, 5, 6, 7]
        ge_zone_day = self.setting.ge_zone_day if self.setting.ge_zone_day is not None else 0
        ge_zone_slots = [int(x) for x in self.setting.ge_zone_slots.split(',')] if self.setting.ge_zone_slots else [5, 6, 7, 8]
        
        base_slots = 0
        slots_stage1 = 0
        slots_stage2 = 0
        slots_stage3 = 0
        
        for d in range(DAYS):
            for s in range(1, SLOTS_PER_DAY + 1):
                # 排除絕對禁區
                if d == ge_zone_day and s in ge_zone_slots: continue
                
                is_thu_pm = (d == 3 and s in [5, 6, 7, 8])
                is_fri = (d == 4)
                is_midweek_out = (d in [1, 2, 3] and s not in midweek_slots)
                
                if not is_fri: slots_stage3 += 1
                if not is_fri and not is_thu_pm: slots_stage2 += 1
                if not is_fri and not is_thu_pm and not (midweek_limit and is_midweek_out): slots_stage1 += 1
                if not (self.setting.friday_all_day_off and is_fri) and \
                   not (self.setting.thursday_afternoon_off and is_thu_pm) and \
                   not (midweek_limit and is_midweek_out):
                    base_slots += 1

        print(f"  [DEBUG] 可用節次評估: Base={base_slots}, Stage1(解限平時)={slots_stage1}, Stage2(+週四下午)={slots_stage2}, Stage3(+週五)={slots_stage3}")

        cl_relax_level = collections.defaultdict(int)
        for cl_id, load in cl_loads.items():
            req = load + 2 # 給予一點緩衝
            if req <= base_slots: cl_relax_level[cl_id] = 0
            elif req <= slots_stage1: cl_relax_level[cl_id] = 1
            elif req <= slots_stage2: cl_relax_level[cl_id] = 2
            else: cl_relax_level[cl_id] = 3
            
        for cl in self.class_groups:
            if cl_loads[cl.id] > 0:
                print(f"    - {cl.name}: 負載 {cl_loads[cl.id]} 小時 (放寬級別: Stage {cl_relax_level[cl.id]})")

        obj_terms = []

        # 3. 變數與約束
        for c in self.courses:
            if not c.should_schedule: continue
            
            duration = c.credits
            if duration <= 0 or duration > 9: continue
            
            is_industry = any("產專" in cl.name for cl in c.classes)
            is_common = any(k in c.name for k in ["中文", "英文", "體育", "電腦應用", "華語", "通識", "勞作"])
            is_labor = "勞作" in c.name
            
            # 動態取得放寬級別
            max_relax = max([cl_relax_level[cl.id] for cl in c.classes]) if c.classes else 0
            # 若為合班課，必須「所有」班級都是產專班才能獲得週五排課特權
            is_industry = all("產專" in cl.name for cl in c.classes) if c.classes else False
            if is_industry: max_relax = max(max_relax, 3) # 產專班預設可排週五
            
            # [修復] 方案A：拔除因高負載(max_relax)自動放寬週五與週四下午的特權，嚴格遵守全校禁排規定
            can_use_fri = is_industry or not self.setting.friday_all_day_off
            can_use_thu_pm = not self.setting.thursday_afternoon_off
            relax_midweek = (max_relax >= 1)
            
            is_special_teacher = c.teacher and c.teacher.is_director
            dir_off_slots = [int(x) for x in self.setting.director_off_slots.split(',')] if self.setting.director_off_slots else [1, 2, 3, 4]
            dir_off_day = self.setting.director_off_day if self.setting.director_off_day is not None else 1
            labor_slots = [int(x) for x in self.setting.labor_slots.split(',')] if self.setting.labor_slots else [1, 8]
            
            allowed = []
            for d in range(DAYS):
                # 規則 1: 週五禁排 (除非是產專班或高負載班級)
                if d == 4 and not can_use_fri: continue 
                
                for s in range(SLOTS_PER_DAY - duration + 1):
                    occupied_slots = range(s + 1, s + duration + 1)
                    
                    # 規則 2：午休隔斷 (4/5節禁跨)
                    if s < 4 and s + duration > 4: continue 
                    
                    # 規則 3: 週四下午 (5-8節) 禁排
                    if d == 3 and any(slot in [5, 6, 7, 8] for slot in occupied_slots):
                        if not can_use_thu_pm: continue

                    # 規則 4: 通識預留區 (嚴格執行非通識禁入，但一年級沒有通識，可豁免)
                    if d == ge_zone_day and any(slot in ge_zone_slots for slot in occupied_slots):
                        is_freshman = any("四技一" in cl.name for cl in c.classes)
                        if not is_freshman and "通識" not in c.name and "共同" not in (c.note or "") and not is_common: continue

                    # 規則 5: 特殊老師 (主任/副校長) 指定時段禁排
                    if d == dir_off_day and is_special_teacher:
                        if any(slot in dir_off_slots for slot in occupied_slots): continue
                        
                    # 規則 7: 週二至週四限縮節次 (預設 2-7)
                    if not relax_midweek and midweek_limit and d in [1, 2, 3] and not is_labor:
                        if any(slot not in midweek_slots for slot in occupied_slots): continue
                        
                    # 規則 8: 勞作教育特權
                    if is_labor:
                        if any(slot not in labor_slots for slot in occupied_slots): continue
                    
                    # 規則 6: 2學分科目必須安排在奇數堂開始 (1, 3, 5, 7 -> 索引 0, 2, 4, 6)
                    if duration == 2 and not is_labor:
                        if s % 2 != 0: continue

                    # [新增規則] 3學分上午連三節，強制從第 2 節開始 (即 s 必須等於 1，對應第 2 節)
                    if duration == 3 and s < 4:
                        if s != 1: continue

                    allowed.append(d * SLOTS_PER_DAY + s)
            
            if not allowed:
                print(f"[ERROR]: 課程 {c.name} (ID:{c.id}, 老師:{c.teacher.name if c.teacher else '無'}) 無可用時段！")
                continue

            start_var = model.NewIntVarFromDomain(cp_model.Domain.FromValues(allowed), f's_{c.id}')
            interval_var = model.NewIntervalVar(start_var, duration, start_var + duration, f'i_{c.id}')
            
            # 教室分配
            room_presences = {}
            room_intervals = {}
            
            # 優先使用指定教室
            if c.classroom_id:
                target_room = next((r for r in self.classrooms if r.id == c.classroom_id), None)
                if target_room:
                    potential_rooms = [target_room]
                else:
                    potential_rooms = self.classrooms # Fallback
            else:
                is_pc = (c.note and "電腦" in c.note) or "電腦" in c.name
                if "體育" in c.name and room_gym: potential_rooms = [room_gym]
                elif "無人機" in c.name and room_drone: potential_rooms = [room_drone]
                elif is_pc: potential_rooms = rooms_pc
                else: potential_rooms = rooms_all if rooms_all else self.classrooms
            
            for r in potential_rooms:
                p = model.NewBoolVar(f'p_{c.id}_{r.id}')
                oi = model.NewOptionalIntervalVar(start_var, duration, start_var + duration, p, f'oi_{c.id}_{r.id}')
                room_presences[r.id] = p
                room_intervals[r.id] = oi
            model.Add(sum(room_presences.values()) == 1)
            
            # 時段固定 (提高到 100000 分以確保接近硬限制)
            if c.fixed_day is not None and c.fixed_slot is not None:
                target = c.fixed_day * SLOTS_PER_DAY + (c.fixed_slot - 1)
                if target in allowed:
                    is_target = model.NewBoolVar(f'is_target_{c.id}')
                    model.Add(start_var == target).OnlyEnforceIf(is_target)
                    obj_terms.append(is_target * 100000)
            
            course_vars[c.id] = {
                "course": c, "start": start_var, "interval": interval_var, 
                "duration": duration, "room_presences": room_presences, "room_intervals": room_intervals
            }

        # 4. 資源衝突
        t_map = collections.defaultdict(list)
        cl_map = collections.defaultdict(list)
        r_map = collections.defaultdict(list)
        for cv in course_vars.values():
            t = cv['course'].teacher
            # 虛擬老師不佔用排課資源
            is_virtual = t and (t.name.startswith("(") or any(k in t.name for k in ["尚未", "保留", "待聘", "共同", "共開"]))
            if t and not is_virtual:
                t_map[t.id].append(cv['interval'])
            for cl in cv['course'].classes:
                cl_map[cl.id].append(cv['interval'])
            for rid, opt_int in cv['room_intervals'].items():
                r_map[rid].append(opt_int)
        
        # 嚴格執行教師衝突檢查
        for ints in t_map.values(): model.AddNoOverlap(ints)
        for ints in cl_map.values(): model.AddNoOverlap(ints)
        for rid, ints in r_map.items(): model.AddNoOverlap(ints)

        # 策略
        all_starts = [cv['start'] for cv in course_vars.values()]
        model.AddDecisionStrategy(all_starts, cp_model.CHOOSE_FIRST, cp_model.SELECT_MIN_VALUE)
        for cv in course_vars.values():
            obj_terms.append(-cv['start']) 

        model.Maximize(sum(obj_terms))

        # 5. 求解
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 300.0
        solver.parameters.num_search_workers = 16
        solver.parameters.log_search_progress = True
        status = solver.Solve(model)

        if status in [cp_model.OPTIMAL, cp_model.FEASIBLE]:
            print(f"[SUCCESS] 求解成功！(狀態: {solver.StatusName(status)})", flush=True)
            res = []
            rooms_dict = {r.id: r.name for r in self.classrooms}
            for cv in course_vars.values():
                t_val = solver.Value(cv['start'])
                sel_room = "未知"
                for rid, p_var in cv['room_presences'].items():
                    if solver.Value(p_var):
                        sel_room = rooms_dict[rid]; break
                for cl_obj in cv['course'].classes:
                    res.append({
                        "course_name": cv['course'].name, "class_name": cl_obj.name,
                        "teacher_name": cv['course'].teacher.name if cv['course'].teacher else "無",
                        "room_name": sel_room, "day": t_val // SLOTS_PER_DAY, "slot": (t_val % SLOTS_PER_DAY) + 1, "duration": cv['duration']
                    })
            with open("schedule_result.json", "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)
            return res
        
        print(f"[FAILED] 失敗：狀態 {solver.StatusName(status)}", flush=True)
        return None

if __name__ == "__main__":
    scheduler = CourseScheduler()
    result = scheduler.solve()
    if result: print(f"成功排定 {len(result)} 門課程次。結果已存至 schedule_result.json")
