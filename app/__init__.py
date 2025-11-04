from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = "super_secret_key_change_me"
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///sports.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'dev-secret'
    db.init_app(app)

    with app.app_context():
        # import routes (which imports models)
        from . import routes, models
        db.create_all()

    return app
