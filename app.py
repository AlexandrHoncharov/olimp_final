# app.py

from flask import Flask, render_template, redirect, url_for
from flask_login import LoginManager
from models import db, User
from routes import auth_bp, admin_bp, participant_bp
import os
from datetime import datetime


def create_app():
    app = Flask(__name__)

    # Конфигурация приложения
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///olympiad.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['UPLOAD_FOLDER'] = os.environ.get('UPLOAD_FOLDER', 'uploads/pdfs')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 МБ

    # Создаем папку для загрузок, если она не существует
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Добавляем переменную для получения текущего времени в шаблонах
    @app.context_processor
    def inject_now():
        return {'now': datetime.utcnow()}

    # Добавляем фильтр для определения статуса олимпиады
    @app.template_filter('olympiad_status')
    def olympiad_status_filter(olympiad):
        now = datetime.utcnow()
        if olympiad.start_time > now:
            return 'scheduled'  # Запланирована
        elif olympiad.end_time < now:
            return 'finished'  # Завершена
        elif olympiad.is_active:
            return 'active'  # Активна
        else:
            return 'suspended'  # Приостановлена

    # Инициализация базы данных
    db.init_app(app)

    # Инициализация Flask-Login
    login_manager = LoginManager()
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'
    login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Регистрация блюпринтов
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(participant_bp, url_prefix='/participant')

    # Главная страница
    @app.route('/')
    def index():
        return redirect(url_for('participant.dashboard'))

    # Обработчик ошибки 404
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404

    # Обработчик ошибки 403
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    # Обработчик ошибки 500
    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    # Создаем базу данных при первом запуске
    with app.app_context():
        db.create_all()
        # Создаем администратора, если его нет
        create_admin_if_not_exists()

    return app


def create_admin_if_not_exists():
    from werkzeug.security import generate_password_hash

    # Проверяем, есть ли хотя бы один администратор
    admin = User.query.filter_by(is_admin=True).first()
    if not admin:
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@example.com')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'adminpassword')

        admin = User(
            email=admin_email,
            password=generate_password_hash(admin_password),
            full_name='Администратор',
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print(f'Создан администратор с email: {admin_email}')


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)