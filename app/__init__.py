import os
from flask import Flask, render_template
from flask_wtf.csrf import CSRFProtect, CSRFError
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
    # csrf.exempt(rooms_bp)
    # csrf.exempt(recordings_bp)
    csrf.exempt(webhook_bp)

    @app.errorhandler(CSRFError)
    def handle_csrf_error(e):
        """Recover the login form instead of dead-ending on a raw 400.

        A successful login calls session.clear() (auth.py), which drops
        Flask-WTF's csrf_token along with everything else. A login form that
        was not freshly fetched — back button, bfcache, restored tab — then
        posts a token against a session that has none, and Flask-WTF raises
        "The CSRF session token is missing." Re-rendering login.html mints a
        fresh token into the session, so the next submit works.
        """
        from flask import request, redirect, session
        if request.path == "/auth/login":
            if session.get("user_id"):
                return redirect("/")
            return render_template(
                "login.html",
                error="Your session expired. Please sign in again."), 400
        return e.get_response()

    @app.context_processor
    def branding():
        from .config import APP_NAME, ENABLE_SECTORS, ENABLE_MATRIX_AUTH
        return {"app_name": APP_NAME,
                "enable_sectors": ENABLE_SECTORS,
                "matrix_auth": ENABLE_MATRIX_AUTH}

    @app.route("/")
    @login_required
    def index():
        from flask import session
        user = {
            "user_id": session.get("user_id"),
            "display_name": session.get("display_name"),
            "role": session.get("role"),
            "avatar_url": session.get("avatar_url")
        }
        return render_template("voice.html",
                               livekit_url=os.environ["LIVEKIT_HOST"],
                               me=user)

    @app.route("/user_avatars/<path:filename>")
    def user_avatars(filename):
        # Absorb Zulip-style avatar requests (relative URLs stored in participant metadata)
        return "", 204

    try:
        import os as _o
        if _o.getenv("ANGINX_API_KEY") and _o.getenv("ANGINX_DOMAIN"):
            from .register_on_start import register_with_anginx
            register_with_anginx(anginx_url=_o.getenv("ANGINX_URL","http://anginx"),key=_o.getenv("ANGINX_API_KEY"),domain=_o.getenv("ANGINX_DOMAIN"),port=int(_o.getenv("ANGINX_PORT","5010")),name=_o.getenv("ANGINX_NAME","voicecom-flask"),host=_o.getenv("ANGINX_HOST") or None)
    except Exception as _e:
        print(f"[anginx] announce skipped: {_e}")
    return app
