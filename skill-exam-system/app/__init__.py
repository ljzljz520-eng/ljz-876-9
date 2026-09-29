"""应用工厂"""
import os
from flask import Flask, g, redirect, render_template, url_for


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev-secret-change-me-in-production',
        DATABASE=os.path.join(app.instance_path, 'exam.sqlite'),
    )
    if test_config:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    from . import db
    db.init_app(app)

    from . import auth, candidate, examiner, admin
    app.register_blueprint(auth.bp)
    app.register_blueprint(candidate.bp)
    app.register_blueprint(examiner.bp)
    app.register_blueprint(admin.bp)

    @app.route('/')
    def index():
        if g.user is None:
            return render_template('index.html')
        # 按角色跳转到各自工作台
        return redirect(url_for(f'{g.user["role"]}.dashboard'))

    return app
