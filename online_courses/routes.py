from datetime import datetime
import os
from flask import render_template, request, redirect, url_for, flash, abort, make_response
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from weasyprint import HTML
from patterns import get_user_factory, CertificateIdGenerator

from app_core import app, db, allowed_file, ALLOWED_IMAGE_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS
from models import (
    User, Course, Module, Lesson, Enrollment, LessonProgress,
    Quiz, Question, AnswerOption, QuizResult
)
from helpers import (
    require_teacher, require_student, seed_once, is_course_completed,
    must_own_course, get_course_tree, ensure_progress_rows, course_progress
)


@app.before_request
def _seed():
    seed_once()


@app.get("/")
def index():
    courses = Course.query.filter_by(is_published=True).order_by(Course.created_at.desc()).all()
    return render_template("index.html", courses=courses)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Невірний email або пароль")
            return redirect(url_for("login"))

        login_user(user)
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "student").strip()

        if not full_name or not email or not password:
            flash("Заповни всі поля")
            return redirect(url_for("register"))

        if role not in ("student", "teacher"):
            role = "student"

        if User.query.filter_by(email=email).first():
            flash("Такий email вже зареєстрований")
            return redirect(url_for("register"))

        factory = get_user_factory(role)
        user = factory.create_user(full_name, email, password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("Реєстрація успішна ")
        return redirect(url_for("dashboard"))

    return render_template("register.html")


@app.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.get("/dashboard")
@login_required
def dashboard():
    if current_user.role == "student":
        enrolls = Enrollment.query.filter_by(student_id=current_user.id).order_by(Enrollment.enrolled_at.desc()).all()

        ongoing = []
        completed = []

        for e in enrolls:
            course = Course.query.get(e.course_id)
            if not course:
                continue

            prog = course_progress(current_user.id, course.id)

            item = {
                "course": course,
                "percent": prog["percent"],
                "enrolled_at": e.enrolled_at,
                "is_done": prog["percent"] >= 100,
            }

            if item["is_done"]:
                completed.append(item)
            else:
                ongoing.append(item)

        return render_template("dashboard_student.html", ongoing=ongoing, completed=completed)

    my_courses = Course.query.filter_by(teacher_id=current_user.id).order_by(Course.created_at.desc()).all()
    return render_template("dashboard_teacher.html", my_courses=my_courses)


@app.get("/certificate/<int:course_id>")
@login_required
def certificate(course_id):
    require_student()
    course = Course.query.get_or_404(course_id)

    if not is_course_completed(current_user.id, course.id):
        flash("Диплом доступний після завершення 100% курсу")
        return redirect(url_for("course_view", course_id=course.id))

    rendered_html = render_template(
        "certificate.html",
        student=current_user,
        course=course,
        issued_at=datetime.utcnow(),
        certificate_id=CertificateIdGenerator().generate(course.id, current_user.id)
    )

    pdf = HTML(string=rendered_html, base_url=request.base_url).write_pdf()

    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'inline; filename=certificate_course_{course.id}.pdf'
    return response


@app.get("/courses/<int:course_id>")
def course_view(course_id):
    course, tree = get_course_tree(course_id)

    prog = {"enrolled": False, "percent": 0, "completed_ids": set(), "enrollment": None}
    if current_user.is_authenticated and current_user.role == "student":
        prog = course_progress(current_user.id, course.id)

    is_owner_teacher = (
        current_user.is_authenticated
        and current_user.role == "teacher"
        and current_user.id == course.teacher_id
    )

    return render_template(
        "course.html",
        course=course,
        tree=tree,
        prog=prog,
        is_owner_teacher=is_owner_teacher,
    )


@app.route("/quiz/<int:quiz_id>", methods=["GET", "POST"])
@login_required
def quiz_view(quiz_id):
    require_student()
    quiz = Quiz.query.get_or_404(quiz_id)

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
            course_id = lesson.module.course_id
            enroll = Enrollment.query.filter_by(student_id=current_user.id, course_id=course_id).first()

            if enroll:
                ensure_progress_rows(enroll.id, course_id)
                row = LessonProgress.query.filter_by(enrollment_id=enroll.id, lesson_id=lesson.id).first()

                if not row:
                    row = LessonProgress(enrollment_id=enroll.id, lesson_id=lesson.id)

                row.is_completed = True
                row.completed_at = datetime.utcnow()
                db.session.add(row)

        db.session.commit()

        flash(f"Тест завершено. Ваш результат: {score_percent}%")
        return redirect(url_for("course_view", course_id=quiz.lesson.module.course_id))

    return render_template("quiz.html", quiz=quiz)


@app.post("/courses/<int:course_id>/enroll")
@login_required
def enroll(course_id):
    require_student()
    Course.query.get_or_404(course_id)

    exists = Enrollment.query.filter_by(student_id=current_user.id, course_id=course_id).first()
    if exists:
        return redirect(url_for("course_view", course_id=course_id))

    e = Enrollment(student_id=current_user.id, course_id=course_id)
    db.session.add(e)
    db.session.commit()
    ensure_progress_rows(e.id, course_id)

    flash("Ти записався на курс ")
    return redirect(url_for("course_view", course_id=course_id))


@app.post("/lessons/<int:lesson_id>/complete")
@login_required
def complete_lesson(lesson_id):
    require_student()

    lesson = Lesson.query.get_or_404(lesson_id)
    module = Module.query.get_or_404(lesson.module_id)
    course_id = module.course_id

    enroll = Enrollment.query.filter_by(student_id=current_user.id, course_id=course_id).first()

    if not enroll:
        flash("Спочатку запишись на курс")
        return redirect(url_for("course_view", course_id=course_id))

    ensure_progress_rows(enroll.id, course_id)

    if lesson.quiz:
        flash("Для цього уроку потрібно пройти тест")
        return redirect(url_for("course_view", course_id=course_id))

    row = LessonProgress.query.filter_by(enrollment_id=enroll.id, lesson_id=lesson.id).first()

    if not row:
        row = LessonProgress(enrollment_id=enroll.id, lesson_id=lesson.id)

    row.is_completed = True
    row.completed_at = datetime.utcnow()

    db.session.add(row)
    db.session.commit()

    flash("Урок позначено як пройдений ")
    return redirect(url_for("course_view", course_id=course_id))


@app.post("/lesson/<int:lesson_id>/quiz/submit")
@login_required
def submit_lesson_quiz(lesson_id):
    require_student()

    lesson = Lesson.query.get_or_404(lesson_id)
    module = Module.query.get_or_404(lesson.module_id)
    course_id = module.course_id

    if not lesson.quiz:
        flash("Для цього уроку тест не знайдено")
        return redirect(url_for("course_view", course_id=course_id))

    enroll = Enrollment.query.filter_by(
        student_id=current_user.id,
        course_id=course_id
    ).first()

    if not enroll:
        flash("Спочатку запишись на курс")
        return redirect(url_for("course_view", course_id=course_id))

    ensure_progress_rows(enroll.id, course_id)

    questions = lesson.quiz.questions
    if not questions:
        flash("У тесті немає питань")
        return redirect(url_for("course_view", course_id=course_id))

    wrong_questions = []
    unanswered_questions = []

    for index, question in enumerate(questions, start=1):
        answer_id = request.form.get(f"question_{question.id}")

        if not answer_id:
            unanswered_questions.append(index)
            continue

        option = AnswerOption.query.get(int(answer_id))

        if not option or option.question_id != question.id or not option.is_correct:
            wrong_questions.append(index)

    if unanswered_questions:
        flash(
            "Тест не зараховано. Не вибрано відповідь у питаннях: "
            + ", ".join(map(str, unanswered_questions))
        )
        return redirect(url_for("course_view", course_id=course_id))

    if wrong_questions:
        flash(
            "Тест не зараховано. Є помилки у питаннях: "
            + ", ".join(map(str, wrong_questions))
        )
        return redirect(url_for("course_view", course_id=course_id))

    result = QuizResult(
        quiz_id=lesson.quiz.id,
        student_id=current_user.id,
        score=100,
        passed=True,
        completed_at=datetime.utcnow()
    )
    db.session.add(result)

    row = LessonProgress.query.filter_by(
        enrollment_id=enroll.id,
        lesson_id=lesson.id
    ).first()

    if not row:
        row = LessonProgress(
            enrollment_id=enroll.id,
            lesson_id=lesson.id
        )

    row.is_completed = True
    row.completed_at = datetime.utcnow()

    db.session.add(row)
    db.session.commit()

    flash("Тест складено успішно  Усі відповіді правильні.")
    return redirect(url_for("course_view", course_id=course_id))



@app.route("/instructor/modules/<int:module_id>/lessons/new", methods=["GET", "POST"])
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
            return redirect(url_for("instructor_new_lesson", module_id=module_id))

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
            if allowed_file(image.filename, ALLOWED_IMAGE_EXTENSIONS):
                image_name = secure_filename(image.filename)
                image.save(os.path.join(app.config["UPLOAD_FOLDER"], image_name))
                lesson.image_filename = image_name
            else:
                flash("Непідтримуваний формат зображення")
                return redirect(url_for("instructor_new_lesson", module_id=module_id))

        video = request.files.get("video")
        if video and video.filename:
            if allowed_file(video.filename, ALLOWED_VIDEO_EXTENSIONS):
                video_name = secure_filename(video.filename)
                video.save(os.path.join(app.config["UPLOAD_FOLDER"], video_name))
                lesson.video_filename = video_name
            else:
                flash("Непідтримуваний формат відео")
                return redirect(url_for("instructor_new_lesson", module_id=module_id))

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

        db.session.commit()

         # ---------- створення тесту з динамічною кількістю питань ----------
        quiz = None
        created_questions = 0

        question_indexes = set()

        for key in request.form.keys():
            if key.startswith("question_text_"):
                idx = key.replace("question_text_", "").strip()
                if idx.isdigit():
                    question_indexes.add(int(idx))

        for i in sorted(question_indexes):
            question_text = request.form.get(f"question_text_{i}", "").strip()
            correct_answer = request.form.get(f"correct_answer_{i}", "").strip()

            answers = []
            for j in range(1, 5):
                ans = request.form.get(f"answer_{i}_{j}", "").strip()
                answers.append(ans)

            if not question_text:
                continue

            if not all(answers):
                flash(f"У питанні {i} не всі варіанти відповідей заповнені")
                return redirect(url_for("instructor_new_lesson", module_id=module_id))

            if correct_answer not in {"1", "2", "3", "4"}:
                flash(f"У питанні {i} вкажи правильну відповідь числом від 1 до 4")
                return redirect(url_for("instructor_new_lesson", module_id=module_id))

            if quiz is None:
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

            option_objects = []
            for idx, answer_text in enumerate(answers, start=1):
                option_objects.append(
                    AnswerOption(
                        question_id=question.id,
                        text=answer_text,
                        is_correct=(str(idx) == correct_answer)
                    )
                )

            db.session.add_all(option_objects)
            created_questions += 1

        db.session.commit()


@app.route("/instructor/courses/<int:course_id>/edit", methods=["GET", "POST"])
@login_required
def instructor_edit_course(course_id):
    course = must_own_course(course_id)

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        is_published = request.form.get("is_published") == "on"

        if not title:
            flash("Назва не може бути порожня")
            return redirect(url_for("instructor_edit_course", course_id=course.id))

        course.title = title
        course.description = description
        course.is_published = is_published
        db.session.commit()

        flash("Курс оновлено ✅")
        return redirect(url_for("course_view", course_id=course.id))

    return render_template("instructor_edit_course.html", course=course)


@app.post("/instructor/courses/<int:course_id>/delete")
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
        quizzes = Quiz.query.filter(Quiz.lesson_id.in_(lesson_ids)).all()
        quiz_ids = [q.id for q in quizzes]
        if quiz_ids:
            questions = Question.query.filter(Question.quiz_id.in_(quiz_ids)).all()
            question_ids = [q.id for q in questions]
            if question_ids:
                AnswerOption.query.filter(AnswerOption.question_id.in_(question_ids)).delete(synchronize_session=False)
            Question.query.filter(Question.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            QuizResult.query.filter(QuizResult.quiz_id.in_(quiz_ids)).delete(synchronize_session=False)
            Quiz.query.filter(Quiz.lesson_id.in_(lesson_ids)).delete(synchronize_session=False)

    if module_ids:
        Lesson.query.filter(Lesson.module_id.in_(module_ids)).delete(synchronize_session=False)

    Module.query.filter_by(course_id=course.id).delete(synchronize_session=False)
    Enrollment.query.filter_by(course_id=course.id).delete(synchronize_session=False)

    db.session.delete(course)
    db.session.commit()

    flash("Курс видалено 🗑️")
    return redirect(url_for("dashboard"))


@app.route("/instructor/courses/new", methods=["GET", "POST"])
@login_required
def instructor_new_course():
    require_teacher()

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        desc = request.form.get("description", "").strip()

        if not title:
            flash("Вкажи назву курсу")
            return redirect(url_for("instructor_new_course"))

        c = Course(title=title, description=desc, teacher_id=current_user.id, is_published=True)
        db.session.add(c)
        db.session.commit()

        flash("Курс створено ")
        return redirect(url_for("course_view", course_id=c.id))

    return render_template("instructor_new_course.html")


@app.route("/instructor/courses/<int:course_id>/modules/new", methods=["GET", "POST"])
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
            return redirect(url_for("instructor_new_module", course_id=course_id))

        m = Module(
            title=title,
            description=description,
            course_id=course.id,
            order_index=order_index
        )
        db.session.add(m)
        db.session.commit()

        flash("Модуль додано ")
        return redirect(url_for("course_view", course_id=course.id))

    return render_template("instructor_new_module.html", course=course)


@app.get("/instructor/courses/<int:course_id>/students")
@login_required
def instructor_students(course_id):
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

def get_embed_video_url(url):
    if not url:
        return None

    if "youtube.com/watch?v=" in url:
        video_id = url.split("watch?v=")[-1].split("&")[0]
        return f"https://www.youtube.com/embed/{video_id}"

    if "youtu.be/" in url:
        video_id = url.split("youtu.be/")[-1].split("?")[0]
        return f"https://www.youtube.com/embed/{video_id}"

    return None