"""启动入口：python run.py"""
from app import create_app
from app.seed import seed

app = create_app()


@app.cli.command('init-db')
def init_db_command():
    """重建数据库并写入种子数据"""
    with app.app_context():
        seed()


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
