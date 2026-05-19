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
    is_director = Column(Boolean, default=False)
    department_id = Column(Integer, ForeignKey('departments.id'))
    courses = relationship("Course", back_populates="teacher")

class Classroom(Base):
    __tablename__ = 'classrooms'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

class ClassGroup(Base):
    __tablename__ = 'class_groups'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey('departments.id'))
    
    courses = relationship("Course", secondary=course_class_association, back_populates="classes")

class Course(Base):
    __tablename__ = 'courses'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    credits = Column(Integer, default=2)
    classroom_id = Column(Integer, ForeignKey('classrooms.id'), nullable=True)
    teacher_id = Column(Integer, ForeignKey('teachers.id'))
    
    # 支援多選班級
    classes = relationship("ClassGroup", secondary=course_class_association, back_populates="courses")
    
    fixed_day = Column(Integer, nullable=True)
    fixed_slot = Column(Integer, nullable=True)
    allowed_slots = Column(String, nullable=True) # 如 "1,8"
    note = Column(String, nullable=True) # 儲存 Excel 備註
    is_reserved = Column(Boolean, default=False) # 是否為保留課程
    should_schedule = Column(Boolean, default=True) # 使用者是否選擇要排這門課

    teacher = relationship("Teacher", back_populates="courses")
    classroom = relationship("Classroom")

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
