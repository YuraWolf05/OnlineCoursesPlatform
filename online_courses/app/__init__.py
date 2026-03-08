from flask import Flask
from .config import Config
from .extensions import db, migrate, login_manager

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # імпорт моделей, щоб Flask-Migrate бачив їх
    from . import models  # noqa: F401

    # якщо є blueprint courses (папка app/courses)
    # from .courses.routes import bp as courses_bp
    # app.register_blueprint(courses_bp)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app