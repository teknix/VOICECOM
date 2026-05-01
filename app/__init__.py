import os
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect
from .middleware import login_required

csrf = CSRFProtect()


def create_app():
    app = Flask(__name__, template_folder="templates", static_folder="../static")
    app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]

    from .auth import limiter
    limiter.init_app(app)

    csrf.init_app(app)

    from .models import init_db
    init_db(app)

    from .auth import auth_bp
    from .rooms import rooms_bp
    from .recordings import recordings_bp
    from .webhook import webhook_bp
    from .admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(rooms_bp)
    app.register_blueprint(recordings_bp)
    app.register_blueprint(webhook_bp)
    app.register_blueprint(admin_bp)

    # Exempt JSON API and webhook routes from CSRF — authenticated by session
    csrf.exempt(rooms_bp)
    csrf.exempt(recordings_bp)
    csrf.exempt(webhook_bp)

    @app.route("/")
    @login_required
    def index():
        return render_template("voice.html", livekit_url=os.environ["LIVEKIT_HOST"])

    return app
