from models import Course, ClassGroup
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import collections

engine = create_engine('postgresql://admin:secretpassword@localhost:15432/course_schedule')
Session = sessionmaker(bind=engine)
db = Session()

cl_loads = collections.defaultdict(int)
courses_by_class = collections.defaultdict(list)

for c in db.query(Course).filter(Course.should_schedule == True).all():
    for cl in c.classes:
        cl_loads[cl.name] += c.credits
        courses_by_class[cl.name].append(f'{c.name}({c.credits})')

with open('loads.txt', 'w', encoding='utf-8') as f:
    for cl_name, load in cl_loads.items():
        f.write(f'Class: {cl_name}, Total Hours: {load}\n')
        f.write(', '.join(courses_by_class[cl_name]) + '\n')
        f.write('-'*50 + '\n')
