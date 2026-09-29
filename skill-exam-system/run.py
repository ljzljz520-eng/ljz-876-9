"""启动入口：python3 run.py"""
from app import create_app
from app.seed import init_db

app = create_app()

if __name__ == '__main__':
    import os
    if not os.path.exists(os.path.join(os.path.dirname(__file__), 'exam_system.db')):
        init_db(app)
    app.run(host='0.0.0.0', port=5000, debug=True)
