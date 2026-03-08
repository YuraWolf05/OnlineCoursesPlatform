from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, abort, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///courses.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


# -------------------- MODELS (простий варіант по твоїй діаграмі) --------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(200), nullable=False, default="User")
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    role = db.Column(db.String(20), nullable=False, default="student")  # student / teacher


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_published = db.Column(db.Boolean, default=True)


class Module(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    order_index = db.Column(db.Integer, nullable=False, default=1)


class Lesson(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=True)
    module_id = db.Column(db.Integer, db.ForeignKey("module.id"), nullable=False)
    order_index = db.Column(db.Integer, nullable=False, default=1)
    duration_minutes = db.Column(db.Integer, nullable=False, default=10)


class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("course.id"), nullable=False)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    __table_args__ = (db.UniqueConstraint("student_id", "course_id", name="uq_enroll"),)


class LessonProgress(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey("enrollment.id"), nullable=False)
    lesson_id = db.Column(db.Integer, db.ForeignKey("lesson.id"), nullable=False)
    is_completed = db.Column(db.Boolean, default=False)
    completed_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.UniqueConstraint("enrollment_id", "lesson_id", name="uq_progress"),)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# -------------------- HELPERS --------------------
def require_teacher():
    if not current_user.is_authenticated or current_user.role != "teacher":
        abort(403)


def require_student():
    if not current_user.is_authenticated or current_user.role != "student":
        abort(403)


def seed_once():
    """Створити БД і демо-дані один раз (для курсової)."""
    db.create_all()
    if User.query.first():
        return

    teacher = User(
        full_name="Викладач",
        email="teacher@mail.com",
        password_hash=generate_password_hash("1234"),
        role="teacher",
    )
    student = User(
        full_name="Студент",
        email="student@mail.com",
        password_hash=generate_password_hash("1234"),
        role="student",
    )
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
    """Teacher може редагувати/видаляти тільки свої курси."""
    require_teacher()
    course = Course.query.get_or_404(course_id)
    if course.teacher_id != current_user.id:
        abort(403)
    return course

def get_course_tree(course_id: int):
    """Курс -> модулі -> уроки (відсортовано)."""
    course = Course.query.get_or_404(course_id)
    modules = Module.query.filter_by(course_id=course.id).order_by(Module.order_index.asc()).all()
    tree = []
    for mod in modules:
        lessons = Lesson.query.filter_by(module_id=mod.id).order_by(Lesson.order_index.asc()).all()
        tree.append((mod, lessons))
    return course, tree


def ensure_progress_rows(enrollment_id: int, course_id: int):
    """Створити рядки прогресу для всіх уроків курсу (щоб рахувати % легко)."""
    lessons = (
        db.session.query(Lesson)
        .join(Module, Lesson.module_id == Module.id)
        .filter(Module.course_id == course_id)
        .all()
    )
    existing = {p.lesson_id for p in LessonProgress.query.filter_by(enrollment_id=enrollment_id).all()}
    to_add = []
    for l in lessons:
        if l.id not in existing:
            to_add.append(LessonProgress(enrollment_id=enrollment_id, lesson_id=l.id, is_completed=False))
    if to_add:
        db.session.add_all(to_add)
        db.session.commit()


def course_progress(student_id: int, course_id: int) -> dict:
    enroll = Enrollment.query.filter_by(student_id=student_id, course_id=course_id).first()
    if not enroll:
        return {"enrolled": False, "percent": 0, "completed_ids": set(), "enrollment": None}

    ensure_progress_rows(enroll.id, course_id)

    # загальна кількість уроків
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
    return {"enrolled": True, "percent": percent, "completed_ids": completed_ids, "enrollment": enroll}


@app.before_request
def _seed():
    seed_once()


# -------------------- ROUTES --------------------
@app.get("/")
def index():
    courses = Course.query.filter_by(is_published=True).order_by(Course.created_at.desc()).all()
    return render_template("index.html", courses=courses)


@app.route("/login", methods=["GET", "POST"]) # логін+ маіл
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

@app.route("/register", methods=["GET", "POST"]) # регістрація
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

        user = User(
            full_name=full_name,
            email=email,
            password_hash=generate_password_hash(password),
            role=role
        )
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash("Реєстрація успішна ✅")
        return redirect(url_for("dashboard"))

    return render_template("register.html")

@app.get("/logout") #виход
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.get("/dashboard") # особистий кабінет 
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

    # teacher dashboard
    my_courses = Course.query.filter_by(teacher_id=current_user.id).order_by(Course.created_at.desc()).all()
    return render_template("dashboard_teacher.html", my_courses=my_courses)

@app.get("/certificate/<int:course_id>") #генерація диплома
@login_required
def certificate(course_id):
    require_student()
    course = Course.query.get_or_404(course_id)

    if not is_course_completed(current_user.id, course.id):
        flash("Диплом доступний після завершення 100% курсу")
        return redirect(url_for("course_view", course_id=course.id))

    html = render_template(
        "certificate.html",
        student=current_user,
        course=course,
        issued_at=datetime.utcnow(),
    )

    resp = make_response(html)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    resp.headers["Content-Disposition"] = f'attachment; filename="certificate_course_{course.id}.html"'
    return resp


@app.get("/courses/<int:course_id>")
def course_view(course_id):
    course, tree = get_course_tree(course_id)
    prog = {"enrolled": False, "percent": 0, "completed_ids": set(), "enrollment": None}
    if current_user.is_authenticated and current_user.role == "student":
        prog = course_progress(current_user.id, course.id)
    is_owner_teacher = current_user.is_authenticated and current_user.role == "teacher" and current_user.id == course.teacher_id
    return render_template(
        "course.html",
        course=course,
        tree=tree,
        prog=prog,
        is_owner_teacher=is_owner_teacher,
    )


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

    flash("Ти записався на курс ✅")
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

    row = LessonProgress.query.filter_by(enrollment_id=enroll.id, lesson_id=lesson.id).first()
    if not row:
        row = LessonProgress(enrollment_id=enroll.id, lesson_id=lesson.id)

    row.is_completed = True
    row.completed_at = datetime.utcnow()
    db.session.add(row)
    db.session.commit()

    flash("Урок позначено як пройдений ✅")
    return redirect(url_for("course_view", course_id=course_id))

@app.route("/instructor/courses/<int:course_id>/edit", methods=["GET", "POST"]) #РЕДАГУВАННЯ КУРСУ
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

@app.post("/instructor/courses/<int:course_id>/delete") #ВИДАЛЕННЯ КУРСУ
@login_required
def instructor_delete_course(course_id):
    course = must_own_course(course_id)

    # каскад “вручну” (простий варіант)
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

    Lesson.query.filter(Lesson.module_id.in_(module_ids)).delete(synchronize_session=False) if module_ids else None
    Module.query.filter_by(course_id=course.id).delete(synchronize_session=False)
    Enrollment.query.filter_by(course_id=course.id).delete(synchronize_session=False)

    db.session.delete(course)
    db.session.commit()

    flash("Курс видалено 🗑️")
    return redirect(url_for("dashboard"))

# ---- TEACHER pages (простий CRUD) ----
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
        flash("Курс створено ✅")
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
        order_index = int(request.form.get("order_index", "1"))
        if not title:
            flash("Вкажи назву модуля")
            return redirect(url_for("instructor_new_module", course_id=course_id))

        m = Module(title=title, course_id=course.id, order_index=order_index)
        db.session.add(m)
        db.session.commit()
        flash("Модуль додано ✅")
        return redirect(url_for("course_view", course_id=course.id))

    return render_template("instructor_new_module.html", course=course)


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
        order_index = int(request.form.get("order_index", "1"))
        duration = int(request.form.get("duration_minutes", "10"))

        if not title:
            flash("Вкажи назву уроку")
            return redirect(url_for("instructor_new_lesson", module_id=module_id))

        l = Lesson(
            title=title,
            content=content,
            module_id=module.id,
            order_index=order_index,
            duration_minutes=duration,
        )
        db.session.add(l)
        db.session.commit()

        # Додати прогрес-рядок новому уроку для всіх записаних студентів
        enrolls = Enrollment.query.filter_by(course_id=course.id).all()
        for e in enrolls:
            db.session.add(LessonProgress(enrollment_id=e.id, lesson_id=l.id, is_completed=False))
        db.session.commit()

        flash("Урок додано ✅")
        return redirect(url_for("course_view", course_id=course.id))

    return render_template("instructor_new_lesson.html", course=course, module=module)


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


if __name__ == "__main__":
    app.run(debug=True)