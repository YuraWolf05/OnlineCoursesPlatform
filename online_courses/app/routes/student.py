from datetime import datetime
from flask import Blueprint, redirect, url_for, flash, request
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Course, Lesson, Module, Enrollment, LessonProgress, AnswerOption, QuizResult
from ..helpers import require_student, ensure_progress_rows

from flask import Blueprint, redirect, url_for, flash, request, render_template

student_bp = Blueprint("student", __name__)


@student_bp.post("/courses/<int:course_id>/enroll")
@login_required
def enroll(course_id):
    require_student()
    Course.query.get_or_404(course_id)

    exists = Enrollment.query.filter_by(student_id=current_user.id, course_id=course_id).first()
    if exists:
        return redirect(url_for("main.course_view", course_id=course_id))

    e = Enrollment(student_id=current_user.id, course_id=course_id)
    db.session.add(e)
    db.session.commit()
    ensure_progress_rows(e.id, course_id)

    flash("Ти записався на курс ✅")
    return redirect(url_for("main.course_view", course_id=course_id))


@student_bp.post("/lessons/<int:lesson_id>/complete")
@login_required
def complete_lesson(lesson_id):
    require_student()

    lesson = Lesson.query.get_or_404(lesson_id)
    module = Module.query.get_or_404(lesson.module_id)
    course_id = module.course_id

    enroll = Enrollment.query.filter_by(student_id=current_user.id, course_id=course_id).first()
    if not enroll:
        flash("Спочатку запишись на курс")
        return redirect(url_for("main.course_view", course_id=course_id))

    ensure_progress_rows(enroll.id, course_id)

    if lesson.quiz:
        flash("Для цього уроку потрібно пройти тест")
        return redirect(url_for("main.course_view", course_id=course_id))

    row = LessonProgress.query.filter_by(enrollment_id=enroll.id, lesson_id=lesson.id).first()
    if not row:
        row = LessonProgress(enrollment_id=enroll.id, lesson_id=lesson.id)

    row.is_completed = True
    row.completed_at = datetime.utcnow()

    db.session.add(row)
    db.session.commit()

    flash("Урок позначено як пройдений ✅")
    return redirect(url_for("main.course_view", course_id=course_id))


@student_bp.route("/quiz/<int:quiz_id>", methods=["GET", "POST"])
@login_required
def quiz_view(quiz_id):
    from ..models import Quiz
    quiz = Quiz.query.get_or_404(quiz_id)
    require_student()

    if request.method == "POST":
        correct = 0
        total = len(quiz.questions)

        for question in quiz.questions:
            selected_option_id = request.form.get(f"question_{question.id}")
            if selected_option_id:
                option = AnswerOption.query.get(int(selected_option_id))
                if option and option.is_correct:
                    correct += 1

        score_percent = int((correct / total) * 100) if total > 0 else 0
        passed = score_percent >= 60

        result = QuizResult(
            quiz_id=quiz.id,
            student_id=current_user.id,
            score=score_percent,
            passed=passed,
            completed_at=datetime.utcnow()
        )
        db.session.add(result)

        if passed:
            lesson = quiz.lesson
            enroll = Enrollment.query.filter_by(
                student_id=current_user.id,
                course_id=lesson.module.course_id
            ).first()

            if enroll:
                ensure_progress_rows(enroll.id, lesson.module.course_id)
                row = LessonProgress.query.filter_by(
                    enrollment_id=enroll.id,
                    lesson_id=lesson.id
                ).first()

                if not row:
                    row = LessonProgress(enrollment_id=enroll.id, lesson_id=lesson.id)

                row.is_completed = True
                row.completed_at = datetime.utcnow()
                db.session.add(row)

        db.session.commit()

        flash(f"Тест завершено. Ваш результат: {score_percent}%")
        return redirect(url_for("main.course_view", course_id=quiz.lesson.module.course_id))

    return render_template("quiz.html", quiz=quiz)