from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Department(Base):
    __tablename__ = 'departments'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

class Teacher(Base):
    __tablename__ = 'teachers'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    title = Column(String, default="一般教師") # 通識/專業/一般
    is_director = Column(Boolean, default=False)
    department_id = Column(Integer, ForeignKey('departments.id'))
    
    courses = relationship("Course", back_populates="teacher")

class Classroom(Base):
    __tablename__ = 'classrooms'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    room_type = Column(String, nullable=False) # 一般, 電腦, 專題, 體育

class ClassGroup(Base):
    __tablename__ = 'class_groups'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    department_id = Column(Integer, ForeignKey('departments.id'))
    default_classroom_id = Column(Integer, ForeignKey('classrooms.id'), nullable=True)

    default_classroom = relationship("Classroom")

class Course(Base):
    __tablename__ = 'courses'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    credits = Column(Integer, default=2)
    room_type_required = Column(String, default="一般")
    teacher_id = Column(Integer, ForeignKey('teachers.id'))
    class_group_id = Column(Integer, ForeignKey('class_groups.id'))
    
    teacher = relationship("Teacher", back_populates="courses")
    class_group = relationship("ClassGroup")
