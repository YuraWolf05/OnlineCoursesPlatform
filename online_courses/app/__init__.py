import os
from flask import Flask
from .extensions import db, login_manager
from .models import User
from .seed import seed_once

gtk_path = r"C:\Program Files\GTK3-Runtime Win64\bin"
os.environ["PATH"] = gtk_path + ";" + os.environ["PATH"]


def allowed_file(filename, allowed_extensions):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )

    app.config["SECRET_KEY"] = "dev-secret-key"
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///courses.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    upload_folder = os.path.join(app.root_path, "static", "uploads")
    os.makedirs(upload_folder, exist_ok=True)

    app.config["UPLOAD_FOLDER"] = upload_folder
    app.config["ALLOWED_IMAGE_EXTENSIONS"] = {"png", "jpg", "jpeg", "gif", "webp"}
    app.config["ALLOWED_VIDEO_EXTENSIONS"] = {"mp4", "webm", "ogg"}

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from .routes.auth import auth_bp
    from .routes.main import main_bp
    from .routes.student import student_bp
    from .routes.instructor import instructor_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(instructor_bp)

    @app.before_request
    def _seed():
        seed_once()

    return app