from datetime import datetime
from flask import Blueprint, render_template, make_response, request, redirect, url_for, flash
from flask_login import login_required, current_user
from weasyprint import HTML

from ..models import Course, Enrollment
from ..helpers import course_progress, get_course_tree, is_course_completed
from ..extensions import db

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    courses = Course.query.filter_by(is_published=True).order_by(Course.created_at.desc()).all()
    return render_template("index.html", courses=courses)


@main_bp.get("/dashboard")
@login_required
def dashboard():
    from ..models import User  # не обов'язково, але якщо треба локально

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


@main_bp.get("/courses/<int:course_id>")
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


@main_bp.get("/certificate/<int:course_id>")
@login_required
def certificate(course_id):
    from ..helpers import require_student
    require_student()

    course = Course.query.get_or_404(course_id)

    if not is_course_completed(current_user.id, course.id):
        flash("Диплом доступний після завершення 100% курсу")
        return redirect(url_for("main.course_view", course_id=course.id))

    rendered_html = render_template(
        "certificate.html",
        student=current_user,
        course=course,
        issued_at=datetime.utcnow(),
        certificate_id=f"CERT-{course.id}-{current_user.id}-{datetime.utcnow().strftime('%Y%m%d')}"
    )

    pdf = HTML(string=rendered_html, base_url=request.base_url).write_pdf()

    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f'inline; filename=certificate_course_{course.id}.pdf'
    return response