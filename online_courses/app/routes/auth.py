from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email).first()
        if not user or not check_password_hash(user.password_hash, password):
            flash("Невірний email або пароль")
            return redirect(url_for("auth.login"))

        login_user(user)
        return redirect(url_for("main.index"))

    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "student").strip()

        if not full_name or not email or not password:
            flash("Заповни всі поля")
            return redirect(url_for("auth.register"))

        if role not in ("student", "teacher"):
            role = "student"

        if User.query.filter_by(email=email).first():
            flash("Такий email вже зареєстрований")
            return redirect(url_for("auth.register"))

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
        return redirect(url_for("main.dashboard"))

    return render_template("register.html")


@auth_bp.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.index"))