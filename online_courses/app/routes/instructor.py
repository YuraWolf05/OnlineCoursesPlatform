import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import Course, Module, Lesson, Enrollment, LessonProgress, Quiz, Question, AnswerOption, User
from ..helpers import require_teacher, must_own_course
from .. import allowed_file

instructor_bp = Blueprint("instructor", __name__)


@instructor_bp.route("/instructor/courses/new", methods=["GET", "POST"])
@login_required
def instructor_new_course():
    require_teacher()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        desc = request.form.get("description", "").strip()

        if not title:
            flash("Вкажи назву курсу")
            return redirect(url_for("instructor.instructor_new_course"))

        c = Course(title=title, description=desc, teacher_id=current_user.id, is_published=True)
        db.session.add(c)
        db.session.commit()

        flash("Курс створено ✅")
        return redirect(url_for("main.course_view", course_id=c.id))

    return render_template("instructor_new_course.html")


@instructor_bp.route("/instructor/courses/<int:course_id>/edit", methods=["GET", "POST"])
@login_required
def instructor_edit_course(course_id):
    course = must_own_course(course_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        is_published = request.form.get("is_published") == "on"

        if not title:
            flash("Назва не може бути порожня")
            return redirect(url_for("instructor.instructor_edit_course", course_id=course.id))

        course.title = title
        course.description = description
        course.is_published = is_published
        db.session.commit()

        flash("Курс оновлено ✅")
        return redirect(url_for("main.course_view", course_id=course.id))

    return render_template("instructor_edit_course.html", course=course)


@instructor_bp.post("/instructor/courses/<int:course_id>/delete")
@login_required
def instructor_delete_course(course_id):
    course = must_own_course(course_id)

    modules = Module.query.filter_by(course_id=course.id).all()
    module_ids = [m.id for m in modules]

    lessons = Lesson.query.filter(Lesson.module_id.in_(module_ids)).all() if module_ids else []
    lesson_ids = [l.id for l in lessons]

    enrolls = Enrollment.query.filter_by(course_id=course.id).all()
    enroll_ids = [e.id for e in enrolls]

    if enroll_ids:
        LessonProgress.query.filter(LessonProgress.enrollment_id.in_(enroll_ids)).delete(synchronize_session=False)
    if lesson_ids:
        LessonProgress.query.filter(LessonProgress.lesson_id.in_(lesson_ids)).delete(synchronize_session=False)

    if lesson_ids:
        Question.query.filter(Question.quiz_id.in_([q.id for q in Quiz.query.filter(Quiz.lesson_id.in_(lesson_ids)).all()])).delete(synchronize_session=False)

    Lesson.query.filter(Lesson.module_id.in_(module_ids)).delete(synchronize_session=False) if module_ids else None
    Module.query.filter_by(course_id=course.id).delete(synchronize_session=False)
    Enrollment.query.filter_by(course_id=course.id).delete(synchronize_session=False)

    db.session.delete(course)
    db.session.commit()

    flash("Курс видалено 🗑️")
    return redirect(url_for("main.dashboard"))


@instructor_bp.route("/instructor/courses/<int:course_id>/modules/new", methods=["GET", "POST"])
@login_required
def instructor_new_module(course_id):
    require_teacher()
    course = Course.query.get_or_404(course_id)

    if course.teacher_id != current_user.id:
        abort(403)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()

        try:
            order_index = int(request.form.get("order_index", "1"))
        except ValueError:
            order_index = 1

        if not title:
            flash("Вкажи назву модуля")
            return redirect(url_for("instructor.instructor_new_module", course_id=course.id))

        module = Module(
            title=title,
            description=description,
            order_index=order_index,
            course_id=course.id
        )

        db.session.add(module)
        db.session.commit()

        flash("Модуль додано ✅")
        return redirect(url_for("main.course_view", course_id=course.id))

    return render_template("instructor_new_module.html", course=course)


@instructor_bp.route("/instructor/modules/<int:module_id>/lessons/new", methods=["GET", "POST"])
@login_required
def instructor_new_lesson(module_id):
    require_teacher()

    module = Module.query.get_or_404(module_id)
    course = Course.query.get_or_404(module.course_id)

    if course.teacher_id != current_user.id:
        abort(403)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        content = request.form.get("content", "").strip()
        video_url = request.form.get("video_url", "").strip()

        try:
            order_index = int(request.form.get("order_index", "1"))
        except ValueError:
            order_index = 1

        try:
            duration = int(request.form.get("duration_minutes", "10"))
        except ValueError:
            duration = 10

        if not title:
            flash("Вкажи назву уроку")
            return redirect(url_for("instructor.instructor_new_lesson", module_id=module_id))

        lesson = Lesson(
            title=title,
            content=content,
            module_id=module.id,
            order_index=order_index,
            duration_minutes=duration,
            video_url=video_url or None
        )

        image = request.files.get("image")
        if image and image.filename:
            if allowed_file(image.filename, current_app.config["ALLOWED_IMAGE_EXTENSIONS"]):
                image_name = secure_filename(image.filename)
                image.save(os.path.join(current_app.config["UPLOAD_FOLDER"], image_name))
                lesson.image_filename = image_name
            else:
                flash("Непідтримуваний формат зображення")
                return redirect(url_for("instructor.instructor_new_lesson", module_id=module_id))

        video = request.files.get("video")
        if video and video.filename:
            if allowed_file(video.filename, current_app.config["ALLOWED_VIDEO_EXTENSIONS"]):
                video_name = secure_filename(video.filename)
                video.save(os.path.join(current_app.config["UPLOAD_FOLDER"], video_name))
                lesson.video_filename = video_name
            else:
                flash("Непідтримуваний формат відео")
                return redirect(url_for("instructor.instructor_new_lesson", module_id=module_id))

        db.session.add(lesson)
        db.session.commit()

        enrolls = Enrollment.query.filter_by(course_id=course.id).all()
        for e in enrolls:
            db.session.add(
                LessonProgress(
                    enrollment_id=e.id,
                    lesson_id=lesson.id,
                    is_completed=False
                )
            )

        question_text = request.form.get("question_text", "").strip()
        answer_1 = request.form.get("answer_1", "").strip()
        answer_2 = request.form.get("answer_2", "").strip()
        answer_3 = request.form.get("answer_3", "").strip()
        answer_4 = request.form.get("answer_4", "").strip()
        correct_answer = request.form.get("correct_answer", "").strip()

        if question_text and answer_1 and answer_2 and answer_3 and answer_4 and correct_answer:
            quiz = Quiz(
                title=f"Тест до уроку: {lesson.title}",
                lesson_id=lesson.id
            )
            db.session.add(quiz)
            db.session.commit()

            question = Question(
                quiz_id=quiz.id,
                text=question_text
            )
            db.session.add(question)
            db.session.commit()

            answers = [
                AnswerOption(question_id=question.id, text=answer_1, is_correct=(correct_answer == "1")),
                AnswerOption(question_id=question.id, text=answer_2, is_correct=(correct_answer == "2")),
                AnswerOption(question_id=question.id, text=answer_3, is_correct=(correct_answer == "3")),
                AnswerOption(question_id=question.id, text=answer_4, is_correct=(correct_answer == "4")),
            ]
            db.session.add_all(answers)

        db.session.commit()

        flash("Урок додано успішно ✅")
        return redirect(url_for("main.course_view", course_id=course.id))

    return render_template("instructor_new_lesson.html", course=course, module=module)


@instructor_bp.get("/instructor/courses/<int:course_id>/students")
@login_required
def instructor_students(course_id):
    from ..helpers import course_progress

    require_teacher()
    course = Course.query.get_or_404(course_id)

    if course.teacher_id != current_user.id:
        abort(403)

    enrolls = Enrollment.query.filter_by(course_id=course.id).all()
    rows = []

    for e in enrolls:
        student = User.query.get(e.student_id)
        prog = course_progress(student.id, course.id)
        rows.append({
            "full_name": student.full_name,
            "email": student.email,
            "percent": prog["percent"],
        })

    rows.sort(key=lambda x: x["percent"], reverse=True)
    return render_template("instructor_students.html", course=course, rows=rows)