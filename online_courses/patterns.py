from abc import ABC, abstractmethod
from datetime import datetime

from werkzeug.security import generate_password_hash

from app_core import db
from models import User, Quiz, Lesson, Module, LessonProgress, Enrollment


# -------------------- SINGLETON --------------------
class CertificateIdGenerator:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CertificateIdGenerator, cls).__new__(cls)
        return cls._instance

    def generate(self, course_id: int, student_id: int) -> str:
        return f"CERT-{course_id}-{student_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"


# -------------------- FACTORY METHOD --------------------
class UserFactory(ABC):
    @abstractmethod
    def create_user(self, full_name: str, email: str, password: str):
        pass


class StudentFactory(UserFactory):
    def create_user(self, full_name: str, email: str, password: str):
        return User(
            full_name=full_name,
            email=email,
            password_hash=generate_password_hash(password),
            role="student"
        )


class TeacherFactory(UserFactory):
    def create_user(self, full_name: str, email: str, password: str):
        return User(
            full_name=full_name,
            email=email,
            password_hash=generate_password_hash(password),
            role="teacher"
        )


def get_user_factory(role: str) -> UserFactory:
    if role == "teacher":
        return TeacherFactory()
    return StudentFactory()


# -------------------- STRATEGY --------------------
class ProgressStrategy(ABC):
    @abstractmethod
    def calculate(self, student_id: int, course_id: int) -> dict:
        pass


class SimpleProgressStrategy(ProgressStrategy):
    def calculate(self, student_id: int, course_id: int) -> dict:
        enroll = Enrollment.query.filter_by(student_id=student_id, course_id=course_id).first()
        if not enroll:
            return {"enrolled": False, "percent": 0, "completed_ids": set(), "enrollment": None}

        lessons = (
            db.session.query(Lesson)
            .join(Module, Lesson.module_id == Module.id)
            .filter(Module.course_id == course_id)
            .all()
        )

        existing = {
            p.lesson_id
            for p in LessonProgress.query.filter_by(enrollment_id=enroll.id).all()
        }

        to_add = []
        for lesson in lessons:
            if lesson.id not in existing:
                to_add.append(
                    LessonProgress(
                        enrollment_id=enroll.id,
                        lesson_id=lesson.id,
                        is_completed=False
                    )
                )

        if to_add:
            db.session.add_all(to_add)
            db.session.commit()

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


class QuizAwareProgressStrategy(ProgressStrategy):
    def calculate(self, student_id: int, course_id: int) -> dict:
        enroll = Enrollment.query.filter_by(student_id=student_id, course_id=course_id).first()
        if not enroll:
            return {"enrolled": False, "percent": 0, "completed_ids": set(), "enrollment": None}

        lessons = (
            db.session.query(Lesson)
            .join(Module, Lesson.module_id == Module.id)
            .filter(Module.course_id == course_id)
            .all()
        )

        existing = {
            p.lesson_id
            for p in LessonProgress.query.filter_by(enrollment_id=enroll.id).all()
        }

        to_add = []
        for lesson in lessons:
            if lesson.id not in existing:
                to_add.append(
                    LessonProgress(
                        enrollment_id=enroll.id,
                        lesson_id=lesson.id,
                        is_completed=False
                    )
                )

        if to_add:
            db.session.add_all(to_add)
            db.session.commit()

        if not lessons:
            return {"enrolled": True, "percent": 0, "completed_ids": set(), "enrollment": enroll}

        rows = LessonProgress.query.filter_by(enrollment_id=enroll.id).all()
        completed_ids = {r.lesson_id for r in rows if r.is_completed}

        total_weight = 0
        earned_weight = 0

        for lesson in lessons:
            has_quiz = lesson.quiz is not None
            weight = 2 if has_quiz else 1
            total_weight += weight

            if lesson.id in completed_ids:
                earned_weight += weight

        percent = int((earned_weight / total_weight) * 100) if total_weight > 0 else 0

        return {
            "enrolled": True,
            "percent": percent,
            "completed_ids": completed_ids,
            "enrollment": enroll
        }


def get_progress_strategy(course_id: int) -> ProgressStrategy:
    has_any_quiz = (
        db.session.query(Quiz.id)
        .join(Lesson, Quiz.lesson_id == Lesson.id)
        .join(Module, Lesson.module_id == Module.id)
        .filter(Module.course_id == course_id)
        .first()
        is not None
    )

    if has_any_quiz:
        return QuizAwareProgressStrategy()
    return SimpleProgressStrategy()