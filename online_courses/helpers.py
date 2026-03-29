from datetime import datetime
from flask import abort
from flask_login import current_user
#from werkzeug.security import generate_password_hash
from patterns import TeacherFactory, StudentFactory, get_progress_strategy
from app_core import db
from models import User, Course, Module, Lesson, Enrollment, LessonProgress


def require_teacher():
    if not current_user.is_authenticated or current_user.role != "teacher":
        abort(403)


def require_student():
    if not current_user.is_authenticated or current_user.role != "student":
        abort(403)


def seed_once():
    db.create_all()

    if User.query.first():
        return

    teacher_factory = TeacherFactory()
    student_factory = StudentFactory()

    teacher = teacher_factory.create_user("Викладач", "teacher@mail.com", "1234")
    student = student_factory.create_user("Студент", "student@mail.com", "1234")
    db.session.add_all([teacher, student])
    db.session.commit()

    course = Course(
        title="Flask-платформа онлайн-курсів",
        description="Мінімальна система: Викладач створює курс/модулі/уроки, Студент записується і відмічає прогрес.",
        teacher_id=teacher.id,
        is_published=True,
    )
    db.session.add(course)
    db.session.commit()

    m1 = Module(title="Модуль 1: Старт", course_id=course.id, order_index=1)
    m2 = Module(title="Модуль 2: Прогрес", course_id=course.id, order_index=2)
    db.session.add_all([m1, m2])
    db.session.commit()

    lessons = [
        Lesson(title="Вступ", content="Що таке Flask і як ми будуємо MVP.", module_id=m1.id, order_index=1, duration_minutes=8),
        Lesson(title="Ролі", content="Student/Teacher — проста авторизація.", module_id=m1.id, order_index=2, duration_minutes=12),
        Lesson(title="Enrollment", content="Запис студента на курс.", module_id=m2.id, order_index=1, duration_minutes=10),
        Lesson(title="LessonProgress", content="Позначення уроку виконаним.", module_id=m2.id, order_index=2, duration_minutes=15),
    ]
    db.session.add_all(lessons)
    db.session.commit()


def is_course_completed(student_id: int, course_id: int) -> bool:
    prog = course_progress(student_id, course_id)
    return prog["enrolled"] and prog["percent"] >= 100


def must_own_course(course_id: int):
    require_teacher()
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)
    return course


def get_course_tree(course_id: int):
    course = Course.query.get_or_404(course_id)
    modules = Module.query.filter_by(course_id=course.id).order_by(Module.order_index.asc()).all()
    tree = []
    for mod in modules:
        lessons = Lesson.query.filter_by(module_id=mod.id).order_by(Lesson.order_index.asc()).all()
        tree.append((mod, lessons))
    return course, tree


def ensure_progress_rows(enrollment_id: int, course_id: int):
    lessons = (
        db.session.query(Lesson)
        .join(Module, Lesson.module_id == Module.id)
        .filter(Module.course_id == course_id)
        .all()
    )

    existing = {p.lesson_id for p in LessonProgress.query.filter_by(enrollment_id=enrollment_id).all()}
    to_add = []

    for lesson in lessons:
        if lesson.id not in existing:
            to_add.append(
                LessonProgress(
                    enrollment_id=enrollment_id,
                    lesson_id=lesson.id,
                    is_completed=False
                )
            )

    if to_add:
        db.session.add_all(to_add)
        db.session.commit()

def course_progress(student_id: int, course_id: int) -> dict:
    strategy = get_progress_strategy(course_id)
    return strategy.calculate(student_id, course_id)

#def course_progress(student_id: int, course_id: int) -> dict:
    enroll = Enrollment.query.filter_by(student_id=student_id, course_id=course_id).first()
    if not enroll:
        return {"enrolled": False, "percent": 0, "completed_ids": set(), "enrollment": None}

    ensure_progress_rows(enroll.id, course_id)

    total = (
        db.session.query(Lesson)
        .join(Module, Lesson.module_id == Module.id)
        .filter(Module.course_id == course_id)
        .count()
    )

    if total == 0:
        return {"enrolled": True, "percent": 0, "completed_ids": set(), "enrollment": enroll}

    rows = LessonProgress.query.filter_by(enrollment_id=enroll.id).all()
    completed_ids = {r.lesson_id for r in rows if r.is_completed}
    completed = len(completed_ids)
    percent = int((completed / total) * 100)

    return {
        "enrolled": True,
        "percent": percent,
        "completed_ids": completed_ids,
        "enrollment": enroll
    }