import json
import collections

def verify():
    # 讀取最後一次生成的結果
    try:
        with open("schedule_result.json", "r", encoding="utf-8") as f:
            results = json.load(f)
    except FileNotFoundError:
        print("❌ 找不到 schedule_result.json，請先執行 scheduler.py")
        return

    print(f"\n--- 開始執行 115-1 深度規則核校 (共 {len(results)} 筆分配) ---")
    
    teacher_slots = collections.defaultdict(list) 
    class_slots = collections.defaultdict(list)   
    room_slots = collections.defaultdict(list)    
    
    # 統計班級負載 (用於驗證規則例外)
    class_loads = collections.defaultdict(int)
    for res in results:
        class_loads[res['class_name']] += res['duration']

    errors = []
    warnings = []

    for res in results:
        day = res['day']
        start_slot = res['slot']
        duration = res['duration']
        course_name = res['course_name']
        teacher_name = res['teacher_name']
        class_name = res['class_name']
        room_name = res['room_name']
        
        # 佔用節次集合 (1-indexed)
        occupied_slots = list(range(start_slot, start_slot + duration))

        # 1. 基礎衝堂檢查 (收集時段佔用)
        for slot in occupied_slots:
            # 排除虛擬教師
            is_virtual = teacher_name and (teacher_name.startswith("(") or any(k in teacher_name for k in ["待聘", "共同", "共開", "班導師", "通識"]))
            if teacher_name and not is_virtual:
                teacher_slots[(teacher_name, day, slot)].append(course_name)
            class_slots[(class_name, day, slot)].append(course_name)
            room_slots[(room_name, day, slot)].append(course_name)

        # 2. 午休隔斷檢查 (不可同時佔用第 4 節與第 5 節)
        if 4 in occupied_slots and 5 in occupied_slots:
            errors.append(f"[午休違規] {course_name} ({class_name}) 橫跨第 4-5 節 (節次:{occupied_slots})")

        # 3. 週四下午禁排 (規則 1)
        if day == 3 and any(s > 4 for s in occupied_slots):
            # 只有極高負載 (>=32) 允許例外
            if class_loads[class_name] < 32:
                errors.append(f"[週四違規] {class_name} 在週四下午排課: {course_name} (節次:{occupied_slots})")

        # 4. 週五禁排 (規則 1)
        if day == 4 and "產專" not in class_name:
            if class_loads[class_name] <= 24:
                errors.append(f"[週五違規] 非產專且低負載班級排在週五: {class_name} ({course_name})")

        # 5. 特殊老師週二下午 (規則 1)
        if day == 1 and ("林金俊" in teacher_name or "藍中賢" in teacher_name):
            # 下午定義為 5-8 節 (slot 5-8)
            if any(s > 4 for s in occupied_slots):
                errors.append(f"[教師違規] {teacher_name} 於週二下午授課: {course_name} (節次:{occupied_slots})")

        # 6. 2學分奇數節起 (規則 3)
        if duration == 2 and start_slot % 2 == 0:
            warnings.append(f"[節次警告] 2學分課程起始於偶數節: {course_name} ({class_name}) 第{start_slot}節")

    # 8. 衝堂明細計算
    for (t, d, s), names in teacher_slots.items():
        if len(set(names)) > 1:
            errors.append(f"[衝堂] 老師 {t} 在 週{d+1} 第{s}節 重疊: {list(set(names))}")

    for (cl, d, s), names in class_slots.items():
        if len(set(names)) > 1:
            errors.append(f"[衝堂] 班級 {cl} 在 週{d+1} 第{s}節 重疊: {list(set(names))}")

    for (r, d, s), names in room_slots.items():
        if len(set(names)) > 1:
            errors.append(f"[衝堂] 教室 {r} 在 週{d+1} 第{s}節 重疊課程: {list(set(names))}")

    # 總結
    print(f"\n--- 核校結果 ---")
    if not errors:
        print("✅ 恭喜！所有硬性規則 (無衝突、週四五、午休、教師禁排) 均通過核校。")
    else:
        print(f"❌ 發現 {len(errors)} 項違規：")
        for e in sorted(list(set(errors))): print(f"  - {e}")

    if warnings:
        print(f"⚠️ 發現 {len(warnings)} 項軟限制警告 (系統已盡力避開)：")
        # 依課程名稱排序並去重
        unique_warnings = sorted(list(set(warnings)))
        for w in unique_warnings[:20]: print(f"  - {w}")
    
    print("\n--- 班級負載概況 ---")
    for cl, load in sorted(class_loads.items()):
        print(f"  {cl}: {load} 小時")

if __name__ == "__main__":
    verify()
