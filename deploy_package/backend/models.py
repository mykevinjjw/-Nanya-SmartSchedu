from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, Table
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# 課程與班級的多對多關聯表
course_class_association = Table(
    'course_class_association',
    Base.metadata,
    Column('course_id', Integer, ForeignKey('courses.id'), primary_key=True),
    Column('class_group_id', Integer, ForeignKey('class_groups.id'), primary_key=True)
)

class Department(Base):
    __tablename__ = 'departments'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

class Teacher(Base):
    __tablename__ = 'teachers'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    title = Column(String, default="一般教師")
    is_director = Column(Boolean, default=False)
    department_id = Column(Integer, ForeignKey('departments.id'))
    courses = relationship("Course", back_populates="teacher")

class Classroom(Base):
    __tablename__ = 'classrooms'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    room_type = Column(String, nullable=False)

class ClassGroup(Base):
    __tablename__ = 'class_groups'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey('departments.id'))
    default_classroom_id = Column(Integer, ForeignKey('classrooms.id'), nullable=True)
    
    courses = relationship("Course", secondary=course_class_association, back_populates="classes")

class Course(Base):
    __tablename__ = 'courses'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    credits = Column(Integer, default=2)
    room_type_required = Column(String, default="一般")
    teacher_id = Column(Integer, ForeignKey('teachers.id'))
    
    # 支援多選班級
    classes = relationship("ClassGroup", secondary=course_class_association, back_populates="courses")
    
    fixed_day = Column(Integer, nullable=True)
    fixed_slot = Column(Integer, nullable=True)
    allowed_slots = Column(String, nullable=True) # 新增：特定課程允許的節次列表 (例如 1,8)
    teacher = relationship("Teacher", back_populates="courses")

    @property
    def class_ids(self):
        return [c.id for c in self.classes]

class SystemSetting(Base):
    __tablename__ = 'system_settings'
    id = Column(Integer, primary_key=True, index=True)
    thursday_afternoon_off = Column(Boolean, default=True)
    friday_all_day_off = Column(Boolean, default=True)
    ge_zone_day = Column(Integer, default=0) 
    ge_zone_slots = Column(String, default="5,6,7,8")
    labor_slots = Column(String, default="1,8")
    director_off_day = Column(Integer, default=1)
    director_off_slots = Column(String, default="1,2,3,4")
    midweek_limit_enabled = Column(Boolean, default=True)
    midweek_allowed_slots = Column(String, default="2,3,4,5,6,7")
