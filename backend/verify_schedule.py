import json
import collections

def verify():
    with open('schedule_result.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    classes_schedule = collections.defaultdict(list)
    for item in data:
        cl = item.get('class_name')
        if cl:
            classes_schedule[cl].append(item)

    print(f"{'班級名稱':<25} | {'總節數':<5} | {'衝堂':<4} | {'跨午休':<5} | {'週五違規':<6}")
    print("-" * 65)

    all_passed = True
    for cl, schedule in classes_schedule.items():
        slots_occupied = set()
        conflicts = 0
        total_hours = 0
        cross_lunch = 0
        friday_violation = 0
        
        for course in schedule:
            day = course['day']
            start = course['slot'] # 1-indexed, e.g., 1 for 1st period
            dur = course['duration']
            total_hours += dur
            
            # 午休檢查 (假設第4節為上午最後一節，第5節為下午第一節)
            # 如果 start <= 4 且 start + dur - 1 >= 5，則跨午休
            if start <= 4 and (start + dur - 1) >= 5:
                cross_lunch += 1
                
            for s in range(start, start + dur):
                if (day, s) in slots_occupied:
                    conflicts += 1
                slots_occupied.add((day, s))
                
        # 週五違規檢查：非產專班且總學分較低者，不應排在週五
        if "產專" not in cl and total_hours < 25:
            for course in schedule:
                if course['day'] == 4:
                    friday_violation += 1
                    
        passed = (conflicts == 0) and (cross_lunch == 0) and (friday_violation == 0)
        if not passed: all_passed = False
        
        status_flag = "PASS" if passed else "FAIL"
        print(f"{cl:25} | {total_hours:<7} | {conflicts:<6} | {cross_lunch:<7} | {friday_violation:<8} | {status_flag}")
        
    print("-" * 65)
    if all_passed:
        print("All passed! 所有班級排課驗證通過！完全沒有衝堂與違規。")
    else:
        print("Warning! 發現排課違規項目，請檢查日誌。")

if __name__ == '__main__':
    verify()
