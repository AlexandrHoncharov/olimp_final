from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import json
from docx.shared import Inches, Pt, RGBColor
import pdfkit
from io import BytesIO
import uuid
from docx import Document
from docx.shared import Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
import io
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows
import csv
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.shared import qn

from docx.enum.table import WD_TABLE_ALIGNMENT
import tempfile
import requests

# Инициализация приложения
app = Flask(__name__)
app.config['SECRET_KEY'] = 'olympiad-system-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///olympiad.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/pdf_files'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Инициализация расширений
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

import json


# Функция для получения текущего локального времени
def get_current_time():
    """Возвращает текущее локальное время"""
    return datetime.now()


@app.template_filter('fromjson')
def fromjson(value):
    return json.loads(value)


# Фильтры для шаблонов
@app.template_filter('tojson')
def to_json(value):
    return json.dumps(value)


# Функция для корректной обработки JSON-полей перед отправкой в шаблон
def prepare_question_data(questions):
    for q in questions:
        if q.question_type == 'test' and q.options:
            q.options_list = json.loads(q.options)
            if q.correct_answers:
                q.correct_answers_list = json.loads(q.correct_answers)
            else:
                q.correct_answers_list = []
        elif q.question_type == 'matching' and q.matches:
            q.matches_list = json.loads(q.matches)
        else:
            q.options_list = []
            q.matches_list = []
            q.correct_answers_list = []
    return questions


# Новые функции для расчета временного коэффициента
def calculate_time_bonus(actual_time, max_time, base_points):
    """
    Расчет временного бонуса

    Логика:
    - Если выполнил быстрее 25% от времени - максимальный бонус (20% от базовых баллов)
    - Если выполнил за 25-50% времени - хороший бонус (10% от базовых баллов)
    - Если выполнил за 50-75% времени - небольшой бонус (5% от базовых баллов)
    - Если выполнил за 75-100% времени - минимальный бонус (1% от базовых баллов)
    - Если превысил время - нет бонуса
    """

    if actual_time <= 0 or max_time <= 0 or base_points <= 0:
        return 0

    # Рассчитываем процент использованного времени
    time_percentage = (actual_time / max_time) * 100

    # Определяем размер бонуса в зависимости от скорости выполнения
    if time_percentage <= 25:
        bonus_percentage = 20  # Максимальный бонус за очень быстрое выполнение
    elif time_percentage <= 50:
        bonus_percentage = 10  # Хороший бонус за быстрое выполнение
    elif time_percentage <= 75:
        bonus_percentage = 5  # Небольшой бонус за нормальное выполнение
    elif time_percentage <= 100:
        bonus_percentage = 1  # Минимальный бонус за выполнение в срок
    else:
        bonus_percentage = 0  # Нет бонуса за превышение времени

    # Рассчитываем итоговый временной бонус
    time_bonus = (base_points * bonus_percentage) / 100

    return round(time_bonus, 2)


def get_time_performance_category(actual_time, max_time):
    """
    Определяет категорию производительности по времени
    """
    if actual_time <= 0 or max_time <= 0:
        return "unknown", "Время не определено"

    time_percentage = (actual_time / max_time) * 100

    if time_percentage <= 25:
        return "excellent", "⚡ Молниеносно"
    elif time_percentage <= 50:
        return "very_good", "🚀 Очень быстро"
    elif time_percentage <= 75:
        return "good", "⏱️ Быстро"
    elif time_percentage <= 100:
        return "normal", "✅ В срок"
    else:
        return "overtime", "⏰ Превышение времени"


# Добавляем функции в контекст шаблонов
@app.context_processor
def inject_time_functions():
    return dict(
        get_time_performance_category=get_time_performance_category,
        min=min,
        max=max
    )


def calculate_final_score(participation):
    """
    Рассчитывает итоговый балл с учетом времени выполнения
    Новая формула: быстрое выполнение = больше бонусных баллов
    """
    if not participation.start_time or not participation.finish_time:
        participation.final_score = participation.total_points
        participation.duration_seconds = None
        participation.time_bonus = 0
        return

    # Получаем олимпиаду для расчета максимального времени
    olympiad = Olympiad.query.get(participation.olympiad_id)
    if not olympiad:
        participation.final_score = participation.total_points
        participation.time_bonus = 0
        return

    # Рассчитываем время выполнения в секундах
    duration = participation.finish_time - participation.start_time
    participation.duration_seconds = duration.total_seconds()

    # Максимальное время олимпиады в секундах
    max_duration = (olympiad.end_time - olympiad.start_time).total_seconds()

    # Расчет временного бонуса
    time_bonus = calculate_time_bonus(participation.duration_seconds, max_duration, participation.total_points)

    # Сохраняем временной бонус отдельно для отображения
    participation.time_bonus = time_bonus

    # Итоговый балл = основные баллы + временной бонус
    participation.final_score = participation.total_points + time_bonus


def update_all_final_scores(olympiad_id):
    """
    Обновляет итоговые баллы для всех завершенных участников олимпиады
    """
    participations = Participation.query.filter_by(
        olympiad_id=olympiad_id,
        status='completed'
    ).all()

    for participation in participations:
        calculate_final_score(participation)

    db.session.commit()


def recalculate_all_time_scores():
    """
    Пересчитывает временные коэффициенты для всех завершенных участий
    """
    completed_participations = Participation.query.filter_by(status='completed').all()

    for participation in completed_participations:
        if participation.start_time and participation.finish_time:
            calculate_final_score(participation)

    db.session.commit()
    return len(completed_participations)


# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    study_group = db.Column(db.String(50), nullable=True)
    speciality = db.Column(db.Text, nullable=True)  # JSON с информацией о специальности
    is_admin = db.Column(db.Boolean, default=False)
    participations = db.relationship('Participation', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def get_speciality_info(self):
        """Возвращает информацию о специальности пользователя"""
        if self.speciality:
            try:
                return json.loads(self.speciality)
            except:
                return None
        return None


class Olympiad(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    welcome_pdf = db.Column(db.String(200), nullable=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    blocks = db.relationship('Block', backref='olympiad', lazy=True, cascade="all, delete-orphan")
    participations = db.relationship('Participation', backref='olympiad', lazy=True, cascade="all, delete-orphan")


class Block(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    olympiad_id = db.Column(db.Integer, db.ForeignKey('olympiad.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    max_points = db.Column(db.Float, nullable=False)
    threshold_percentage = db.Column(db.Float, nullable=False)  # % для перехода на следующий блок
    order = db.Column(db.Integer, nullable=False)
    questions = db.relationship('Question', backref='block', lazy=True, cascade="all, delete-orphan")


class BlockResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participation_id = db.Column(db.Integer, db.ForeignKey('participation.id'), nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey('block.id'), nullable=False)
    points_earned = db.Column(db.Float, default=0)
    completed_at = db.Column(db.DateTime, default=get_current_time)

    participation = db.relationship('Participation', backref='block_results')
    block = db.relationship('Block', backref='results')


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey('block.id'), nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # 'test' или 'matching'
    text = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text, nullable=True)  # JSON строка для вариантов ответа
    correct_answers = db.Column(db.Text, nullable=True)  # JSON строка для правильных ответов
    matches = db.Column(db.Text, nullable=True)  # JSON строка для пар соответствия
    points = db.Column(db.Float, nullable=False)
    answers = db.relationship('Answer', backref='question', lazy=True, cascade="all, delete-orphan")


class Participation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    olympiad_id = db.Column(db.Integer, db.ForeignKey('olympiad.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=True)
    finish_time = db.Column(db.DateTime, nullable=True)
    total_points = db.Column(db.Float, default=0)  # Основные баллы за правильные ответы
    final_score = db.Column(db.Float, default=0)  # Итоговый балл с учетом времени
    duration_seconds = db.Column(db.Float, nullable=True)  # Время выполнения в секундах
    time_bonus = db.Column(db.Float, default=0)  # Временной бонус отдельно
    status = db.Column(db.String(20), default='registered')  # 'registered', 'in_progress', 'completed'
    current_block = db.Column(db.Integer, nullable=True)
    answers = db.relationship('Answer', backref='participation', lazy=True, cascade="all, delete-orphan")


class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participation_id = db.Column(db.Integer, db.ForeignKey('participation.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    answer_data = db.Column(db.Text, nullable=False)  # JSON строка для ответа
    is_correct = db.Column(db.Boolean, default=False)
    points_earned = db.Column(db.Float, default=0)
    answered_at = db.Column(db.DateTime, default=get_current_time)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@app.context_processor  # runs for every template render
def inject_now():
    # ИСПРАВЛЕНО: используем локальное время вместо UTC
    return {'now': get_current_time}


# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            olympiads = Olympiad.query.all()
        else:
            # ИСПРАВЛЕНО: используем локальное время
            current_time = get_current_time()
            olympiads = Olympiad.query.filter(
                Olympiad.end_time > current_time
            ).all()
    else:
        olympiads = []
    return render_template('index.html', olympiads=olympiads)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        flash('Неверный email или пароль', 'error')

    return render_template('login.html')


@app.route('/api/specialities', methods=['GET'])
def get_specialities():
    """API роут для получения списка специальностей"""
    try:
        response = requests.get('https://melsu.ru/api/specialities/list', timeout=10)
        if response.status_code == 200:
            return jsonify(response.json())
        else:
            return jsonify({'error': 'Не удалось получить список специальностей'}), 500
    except requests.RequestException:
        return jsonify({'error': 'Ошибка соединения с сервером'}), 500


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        study_group = request.form.get('study_group')
        speciality_id = request.form.get('speciality_id')

        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован', 'error')
            return redirect(url_for('register'))

        # Получаем информацию о специальности
        speciality_info = None
        if speciality_id:
            try:
                response = requests.get('https://melsu.ru/api/specialities/list', timeout=10)
                if response.status_code == 200:
                    specialities = response.json()
                    if speciality_id in specialities:
                        spec = specialities[speciality_id]
                        speciality_info = {
                            'id': spec['id'],
                            'spec_code': spec['spec_code'],
                            'name': spec['name'],
                            'department_name': spec['department_name'],
                            'faculty_name': spec['faculty_name'],
                            'faculty_acronym': spec['faculty_acronym'],
                            'level': spec['level']
                        }
            except requests.RequestException:
                flash('Не удалось сохранить информацию о специальности', 'warning')

        user = User(
            email=email,
            full_name=full_name,
            study_group=study_group,
            speciality=json.dumps(speciality_info) if speciality_info else None
        )
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        login_user(user)
        return redirect(url_for('index'))

    return render_template('register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/profile')
@login_required
def profile():
    participations = Participation.query.filter_by(user_id=current_user.id).all()
    return render_template('profile.html', participations=participations)


# Admin routes
@app.route('/admin/olympiads', methods=['GET'])
@login_required
def admin_olympiads():
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    olympiads = Olympiad.query.all()
    return render_template('admin/olympiads.html', olympiads=olympiads)


# Маршрут для управления пользователями
@app.route('/admin/users', methods=['GET'])
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    users = User.query.all()
    return render_template('admin/users.html', users=users)


# Маршрут для аналитики
@app.route('/admin/analytics', methods=['GET'])
@login_required
def admin_analytics():
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    # Общая статистика
    total_olympiads = Olympiad.query.count()
    total_users = User.query.count()
    total_participations = Participation.query.count()
    completed_participations = Participation.query.filter_by(status='completed').count()

    # Статистика по олимпиадам
    current_time = get_current_time()
    active_olympiads = Olympiad.query.filter(
        Olympiad.start_time <= current_time,
        Olympiad.end_time > current_time
    ).count()

    upcoming_olympiads = Olympiad.query.filter(
        Olympiad.start_time > current_time
    ).count()

    # Топ олимпиад по участникам
    olympiad_stats = db.session.query(
        Olympiad.title,
        db.func.count(Participation.id).label('participants')
    ).join(Participation).group_by(Olympiad.id).order_by(
        db.func.count(Participation.id).desc()
    ).limit(10).all()

    return render_template('admin/analytics.html',
                           total_olympiads=total_olympiads,
                           total_users=total_users,
                           total_participations=total_participations,
                           completed_participations=completed_participations,
                           active_olympiads=active_olympiads,
                           upcoming_olympiads=upcoming_olympiads,
                           olympiad_stats=olympiad_stats)


# Маршрут для настроек системы
@app.route('/admin/settings', methods=['GET'])
@login_required
def admin_settings():
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    return render_template('admin/settings.html')


# Добавить роут для ручного пересчета временных коэффициентов
@app.route('/admin/recalculate_time_scores', methods=['POST'])
@login_required
def recalculate_time_scores():
    """Ручной пересчет временных коэффициентов"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    try:
        count = recalculate_all_time_scores()
        return jsonify({
            'success': True,
            'message': f'Пересчитаны временные коэффициенты для {count} участий'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Ошибка при пересчете: {str(e)}'
        }), 500


# Маршрут для генерации DOCX документа с результатами
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


@app.route('/admin/olympiad/<int:olympiad_id>/export_docx', methods=['GET'])
@login_required
def export_rankings_docx(olympiad_id):
    """Экспорт результатов в формате DOCX с официальным оформлением МелГУ"""
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Обновляем итоговые баллы перед экспортом
    update_all_final_scores(olympiad_id)

    # Получаем всех участников с результатами, сортируем по итоговому баллу
    participations = Participation.query.filter_by(
        olympiad_id=olympiad_id,
        status='completed'
    ).order_by(Participation.final_score.desc()).all()

    # Создаем новый документ
    doc = Document()

    # Настройка стилей документа
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Times New Roman'
    font.size = Pt(14)

    # Заголовок организации
    header1 = doc.add_paragraph()
    header1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run1 = header1.add_run('ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ ВЫСШЕГО ОБРАЗОВАНИЯ')
    run1.font.name = 'Times New Roman'
    run1.font.size = Pt(14)
    run1.font.bold = True

    header2 = doc.add_paragraph()
    header2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run2 = header2.add_run('МЕЛИТОПОЛЬСКИЙ ГОСУДАРСТВЕННЫЙ УНИВЕРСИТЕТ')
    run2.font.name = 'Times New Roman'
    run2.font.size = Pt(14)
    run2.font.bold = True

    # Пустая строка
    doc.add_paragraph()

    # Факультет и кафедра
    faculty = doc.add_paragraph()
    faculty.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run3 = faculty.add_run('Технический факультет')
    run3.font.name = 'Times New Roman'
    run3.font.size = Pt(14)
    run3.font.bold = True

    department = doc.add_paragraph()
    department.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run4 = department.add_run('кафедра «Гражданская безопасность»')
    run4.font.name = 'Times New Roman'
    run4.font.size = Pt(14)
    run4.font.bold = True

    # 5 пустых строк
    for _ in range(5):
        doc.add_paragraph()

    # Заголовок результатов
    results_title = doc.add_paragraph()
    results_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run5 = results_title.add_run('РЕЗУЛЬТАТЫ ПОБЕДИТЕЛЕЙ')
    run5.font.name = 'Times New Roman'
    run5.font.size = Pt(14)
    run5.font.bold = True

    # Пустая строка
    doc.add_paragraph()

    # Название олимпиады
    olympiad_title = doc.add_paragraph()
    olympiad_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run6 = olympiad_title.add_run('предметной студенческой Олимпиады')
    run6.font.name = 'Times New Roman'
    run6.font.size = Pt(14)
    run6.font.bold = True

    discipline1 = doc.add_paragraph()
    discipline1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run7 = discipline1.add_run('по дисциплине')
    run7.font.name = 'Times New Roman'
    run7.font.size = Pt(14)
    run7.font.bold = True

    # Используем название олимпиады из системы
    discipline2 = doc.add_paragraph()
    discipline2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run8 = discipline2.add_run(f'«{olympiad.title}»')
    run8.font.name = 'Times New Roman'
    run8.font.size = Pt(14)
    run8.font.bold = True

    # Пустая строка
    doc.add_paragraph()

    # Дата проведения
    date_conducted = doc.add_paragraph()
    date_conducted.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run9 = date_conducted.add_run(
        f'проведенной «{olympiad.start_time.day}» {_get_month_name(olympiad.start_time.month)} {olympiad.start_time.year} г.')
    run9.font.name = 'Times New Roman'
    run9.font.size = Pt(14)
    run9.font.bold = True

    # Пустая строка
    doc.add_paragraph()

    # Таблица с результатами
    # Определяем количество столбцов (только топ-10 или все, если меньше 10)
    top_participants = participations[:3] if len(participations) > 3 else participations

    if top_participants:
        table = doc.add_table(rows=1, cols=7)  # Увеличиваем до 7 колонок для временного бонуса
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.style = 'Table Grid'

        # Заголовки таблицы
        hdr_cells = table.rows[0].cells
        headers = ['Место', 'ФИО студента', 'Группа', 'Направление подготовки',
                   'Баллы за задания', 'Временной бонус', 'Итоговый балл']

        for i, header in enumerate(headers):
            hdr_cells[i].text = header
            # Форматирование заголовков
            for paragraph in hdr_cells[i].paragraphs:
                for run in paragraph.runs:
                    run.font.name = 'Times New Roman'
                    run.font.size = Pt(14)
                    run.font.bold = True
                paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

        # Заполнение данными
        for i, participation in enumerate(top_participants, 1):
            user = User.query.get(participation.user_id)
            row_cells = table.add_row().cells

            # Получаем информацию о специальности
            speciality_info = user.get_speciality_info()

            # Формируем строку с кодом и названием специальности
            if speciality_info:
                speciality_text = f"{speciality_info['spec_code']} - {speciality_info['name']}"
            else:
                speciality_text = '-'

            # Данные строки
            row_data = [
                str(i),
                user.full_name,
                user.study_group or '-',
                speciality_text,
                f"{participation.total_points:.1f}",  # Баллы за задания
                f"+{participation.time_bonus:.1f}" if participation.time_bonus else "+0.0",  # Временной бонус
                f"{participation.final_score:.1f}"  # Итоговый балл с учетом времени
            ]

            for j, data in enumerate(row_data):
                row_cells[j].text = data
                # Форматирование ячеек
                for paragraph in row_cells[j].paragraphs:
                    for run in paragraph.runs:
                        run.font.name = 'Times New Roman'
                        run.font.size = Pt(14)
                    # Центрирование для места и баллов, левое выравнивание для остальных
                    if j in [0, 4, 5, 6]:  # Место и баллы
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    else:  # ФИО, группа и направление
                        paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT

        # Настройка ширины столбцов
        for i, width in enumerate(
                [Inches(0.6), Inches(2.2), Inches(1.0), Inches(2.5), Inches(1.0), Inches(1.0), Inches(1.0)]):
            for row in table.rows:
                row.cells[i].width = width

    # 4 пустые строки
    for _ in range(4):
        doc.add_paragraph()

    # Дата подписания
    signature_date = doc.add_paragraph()
    signature_date.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run10 = signature_date.add_run(f'«___»____________ {datetime.now().year} г.')
    run10.font.name = 'Times New Roman'
    run10.font.size = Pt(14)

    # Пустая строка
    doc.add_paragraph()

    # Таблица для подписей жюри
    jury_title = doc.add_paragraph()
    jury_title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run11 = jury_title.add_run('Члены жюри:')
    run11.font.name = 'Times New Roman'
    run11.font.size = Pt(14)
    run11.font.bold = True

    doc.add_paragraph()

    # Создаем таблицу для подписей (3 строки по 4 столбца: пустой, подпись, пустой, ФИО)
    jury_table = doc.add_table(rows=3, cols=4)
    jury_table.style = None  # Убираем границы

    # Устанавливаем ширину столбцов
    for i, width in enumerate([Inches(1), Inches(1.5), Inches(1), Inches(3.5)]):
        for row in jury_table.rows:
            row.cells[i].width = width

    jury_signatures = [
        ['', '(подпись)', '', '(инициалы, фамилия уч. степень, должность)'],
        ['', '(подпись)', '', '(инициалы, фамилия уч. степень, должность)'],
        ['', '(подпись)', '', '(инициалы, фамилия уч. степень, должность)']
    ]

    for row_idx, row_data in enumerate(jury_signatures):
        # Добавляем пустые строки для подписей
        for _ in range(3):
            doc.add_paragraph()

        row = jury_table.rows[row_idx]

        for col_idx, cell_text in enumerate(row_data):
            cell = row.cells[col_idx]

            if cell_text:  # Если ячейка не пустая (столбцы 1 и 3 - подпись и ФИО)
                # Добавляем текст
                cell.text = cell_text

                # Форматируем текст
                for paragraph in cell.paragraphs:
                    for run in paragraph.runs:
                        run.font.name = 'Times New Roman'
                        run.font.size = Pt(14)
                    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

                # Добавляем верхнее подчеркивание (границу)
                tc = cell._tc
                tcPr = tc.get_or_add_tcPr()
                tcBorders = OxmlElement('w:tcBorders')
                top_border = OxmlElement('w:top')
                top_border.set(qn('w:val'), 'single')
                top_border.set(qn('w:sz'), '4')
                top_border.set(qn('w:space'), '0')
                top_border.set(qn('w:color'), '000000')
                tcBorders.append(top_border)
                tcPr.append(tcBorders)

    # Сохраняем документ в память
    doc_io = BytesIO()
    doc.save(doc_io)
    doc_io.seek(0)

    filename = f'results_{olympiad.title}_{datetime.now().strftime("%Y%m%d_%H%M")}.docx'

    return send_file(
        doc_io,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    )


from flask import request, jsonify
import json
import re


@app.route('/admin/block/<int:block_id>/upload_questions', methods=['POST'])
@login_required
def upload_questions(block_id):
    """
    Загрузка вопросов для блока из файла
    Поддерживаемые форматы:
    1. Тесты:
       "1. Название вопроса" затем варианты ответа, правильные ответы начинаются с 4-х пробелов
    2. Сопоставление:
       "1. Название вопроса" затем пары для сопоставления в формате "Вариант 1 | Ответ 1"
    """
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    block = Block.query.get_or_404(block_id)

    # Проверяем, что файл есть в запросе
    if 'questions_file' not in request.files:
        return jsonify({'success': False, 'message': 'Файл не найден в запросе'})

    file = request.files['questions_file']
    if file.filename == '':
        return jsonify({'success': False, 'message': 'Файл не выбран'})

    # Читаем содержимое файла
    try:
        content = file.read().decode('utf-8')
    except UnicodeDecodeError:
        try:
            # Пробуем другую кодировку, если UTF-8 не работает
            file.seek(0)
            content = file.read().decode('windows-1251')
        except:
            return jsonify({'success': False,
                            'message': 'Не удалось прочитать файл. Проверьте кодировку (поддерживаются UTF-8 и Windows-1251)'})

    # Определяем тип блока по содержимому
    block_type = request.form.get('block_type')
    if not block_type:
        # Автоопределение типа блока по содержимому
        if '|' in content:
            block_type = 'matching'
        else:
            block_type = 'test'

    # Обработка содержимого в зависимости от типа блока
    questions_created = 0
    try:
        if block_type == 'test':
            questions_created = parse_test_questions(content, block_id)
        elif block_type == 'matching':
            questions_created = parse_matching_questions(content, block_id)
        else:
            return jsonify({'success': False, 'message': f'Неизвестный тип блока: {block_type}'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Ошибка при обработке файла: {str(e)}'})

    # Обновляем равномерно баллы за все вопросы в блоке
    update_question_points(block_id)

    return jsonify({
        'success': True,
        'message': f'Успешно загружено {questions_created} вопросов в блок',
        'questions_count': questions_created
    })


def parse_test_questions(content, block_id):
    """Разбор содержимого файла с тестовыми вопросами"""
    lines = content.splitlines()

    questions = []
    current_question = None
    current_options = []
    current_correct = []

    for line in lines:
        line = line.rstrip()
        if not line:  # Пропускаем пустые строки
            continue

        # Новый вопрос начинается с номера и точки
        if re.match(r'^\d+\.', line):
            # Сохраняем предыдущий вопрос, если он есть
            if current_question:
                questions.append({
                    'text': current_question,
                    'options': current_options,
                    'correct_answers': current_correct
                })

            # Начинаем новый вопрос
            current_question = line.split('.', 1)[1].strip()
            current_options = []
            current_correct = []
        elif line.startswith('    '):  # Правильный ответ (4 пробела в начале)
            option = line.strip()
            if option not in current_options:
                current_options.append(option)
            current_correct.append(option)
        else:  # Обычный вариант ответа
            option = line.strip()
            if option and option not in current_options:
                current_options.append(option)

    # Добавляем последний вопрос
    if current_question:
        questions.append({
            'text': current_question,
            'options': current_options,
            'correct_answers': current_correct
        })

    # Сохраняем вопросы в базу данных
    questions_created = 0
    for q_data in questions:
        if not q_data['options'] or not q_data['correct_answers']:
            continue  # Пропускаем некорректные вопросы

        question = Question(
            block_id=block_id,
            question_type='test',
            text=q_data['text'],
            options=json.dumps(q_data['options']),
            correct_answers=json.dumps(q_data['correct_answers']),
            points=1.0  # Временное значение, будет обновлено позже
        )
        db.session.add(question)
        questions_created += 1

    db.session.commit()
    return questions_created


def parse_matching_questions(content, block_id):
    """Разбор содержимого файла с вопросами на сопоставление"""
    lines = content.splitlines()

    questions = []
    current_question = None
    current_matches = []

    for line in lines:
        line = line.rstrip()
        if not line:  # Пропускаем пустые строки
            continue

        # Новый вопрос начинается с номера и точки
        if re.match(r'^\d+\.', line):
            # Сохраняем предыдущий вопрос, если он есть
            if current_question:
                questions.append({
                    'text': current_question,
                    'matches': current_matches
                })

            # Начинаем новый вопрос
            current_question = line.split('.', 1)[1].strip()
            current_matches = []
        elif '|' in line:  # Строка с парой для сопоставления
            parts = line.split('|', 1)
            if len(parts) == 2:
                left = parts[0].strip()
                right = parts[1].strip()
                if left and right:
                    current_matches.append({'left': left, 'right': right})

    # Добавляем последний вопрос
    if current_question:
        questions.append({
            'text': current_question,
            'matches': current_matches
        })

    # Сохраняем вопросы в базу данных
    questions_created = 0
    for q_data in questions:
        if not q_data['matches']:
            continue  # Пропускаем некорректные вопросы

        question = Question(
            block_id=block_id,
            question_type='matching',
            text=q_data['text'],
            matches=json.dumps(q_data['matches']),
            points=1.0  # Временное значение, будет обновлено позже
        )
        db.session.add(question)
        questions_created += 1

    db.session.commit()
    return questions_created


def update_question_points(block_id):
    """Обновление баллов за вопросы, чтобы их сумма равнялась max_points блока"""
    block = Block.query.get(block_id)
    questions = Question.query.filter_by(block_id=block_id).all()

    if not questions:
        return

    # Распределяем баллы поровну между всеми вопросами
    points_per_question = block.max_points / len(questions)

    for question in questions:
        question.points = points_per_question

    db.session.commit()


QUESTION_FILE_FORMAT = """
Формат файла для тестовых вопросов:
1. Название вопроса
Вариант ответа 1
Вариант ответа 2
    Правильный вариант ответа (начинается с 4 пробелов)
Вариант ответа 4

2. Еще один вопрос
Вариант ответа 1
    Правильный вариант 2
Вариант ответа 3

Формат файла для вопросов на сопоставление:
1. Название вопроса на сопоставление
Левая часть 1 | Правая часть 1
Левая часть 2 | Правая часть 2
Левая часть 3 | Правая часть 3

2. Еще один вопрос на сопоставление
Понятие 1 | Определение 1
Понятие 2 | Определение 2
"""


@app.route('/admin/block/<int:block_id>/file_format', methods=['GET'])
@login_required
def get_question_file_format(block_id):
    """Возвращает образец формата файла для загрузки вопросов"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    return jsonify({
        'success': True,
        'format': QUESTION_FILE_FORMAT
    })


def _get_month_name(month_num):
    """Возвращает название месяца на русском языке"""
    months = {
        1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
        5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
        9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
    }
    return months.get(month_num, '')


@app.route('/admin/block/<int:block_id>/get_question', methods=['GET'])
@login_required
def get_question(block_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'У вас нет доступа к этой функции'}), 403

    question_id = request.args.get('question_id')
    if not question_id:
        return jsonify({'success': False, 'message': 'Не указан ID вопроса'}), 400

    question = Question.query.get_or_404(int(question_id))

    # Проверяем, принадлежит ли вопрос указанному блоку
    if question.block_id != block_id:
        return jsonify({'success': False, 'message': 'Вопрос не принадлежит указанному блоку'}), 403

    # Подготавливаем данные вопроса для отправки
    question_data = {
        'id': question.id,
        'text': question.text,
        'question_type': question.question_type,
        'points': question.points
    }

    # Добавляем специфичные для типа вопроса данные
    if question.question_type == 'test':
        question_data['options'] = question.options
        question_data['correct_answers'] = question.correct_answers

        # Для удобства работы с данными в JavaScript
        try:
            question_data['options_list'] = json.loads(question.options) if question.options else []
            question_data['correct_answers_list'] = json.loads(
                question.correct_answers) if question.correct_answers else []
        except json.JSONDecodeError:
            question_data['options_list'] = []
            question_data['correct_answers_list'] = []

    elif question.question_type == 'matching':
        question_data['matches'] = question.matches

        # Для удобства работы с данными в JavaScript
        try:
            question_data['matches_list'] = json.loads(question.matches) if question.matches else []
        except json.JSONDecodeError:
            question_data['matches_list'] = []

    return jsonify({
        'success': True,
        'question': question_data
    })


@app.route('/admin/block/<int:block_id>/update_question', methods=['POST'])
@login_required
def update_question(block_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'У вас нет доступа к этой функции'}), 403

    question_id = request.form.get('question_id')
    if not question_id:
        return jsonify({'success': False, 'message': 'Не указан ID вопроса'}), 400

    question = Question.query.get_or_404(int(question_id))

    # Проверяем, принадлежит ли вопрос указанному блоку
    if question.block_id != block_id:
        return jsonify({'success': False, 'message': 'Вопрос не принадлежит указанному блоку'}), 403

    # Обновляем общие поля
    question.text = request.form.get('text', question.text)

    # Обновляем специфичные для типа вопроса поля
    if question.question_type == 'test':
        options = request.form.getlist('options[]')
        correct_answers = request.form.getlist('correct_answers[]')

        if not options:
            return jsonify({'success': False, 'message': 'Необходимо указать хотя бы два варианта ответа'}), 400

        if len(options) < 2:
            return jsonify({'success': False, 'message': 'Необходимо указать хотя бы два варианта ответа'}), 400

        if not correct_answers:
            return jsonify({'success': False, 'message': 'Необходимо указать хотя бы один правильный ответ'}), 400

        # Убеждаемся, что все правильные ответы присутствуют в списке вариантов
        for answer in correct_answers:
            if answer not in options:
                return jsonify({'success': False, 'message': 'Правильный ответ должен быть в списке вариантов'}), 400

        question.options = json.dumps(options)
        question.correct_answers = json.dumps(correct_answers)

    elif question.question_type == 'matching':
        left_items = request.form.getlist('left_items[]')
        right_items = request.form.getlist('right_items[]')

        if not left_items or not right_items:
            return jsonify({'success': False, 'message': 'Необходимо указать хотя бы две пары для сопоставления'}), 400

        if len(left_items) != len(right_items):
            return jsonify(
                {'success': False, 'message': 'Количество элементов в левой и правой колонках должно совпадать'}), 400

        if len(left_items) < 2:
            return jsonify({'success': False, 'message': 'Необходимо указать хотя бы две пары для сопоставления'}), 400

        # Формируем пары
        matches = []
        for i in range(len(left_items)):
            matches.append({
                'left': left_items[i],
                'right': right_items[i]
            })

        question.matches = json.dumps(matches)

    # Сохраняем изменения
    try:
        db.session.commit()
        return jsonify({'success': True, 'message': 'Вопрос успешно обновлен'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Ошибка при обновлении вопроса: {str(e)}")
        return jsonify({'success': False, 'message': f'Ошибка при обновлении вопроса: {str(e)}'}), 500


@app.route('/admin/block/<int:block_id>/delete_question', methods=['POST'])
@login_required
def delete_question(block_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'У вас нет доступа к этой функции'}), 403

    data = request.get_json()
    if not data or 'question_id' not in data:
        return jsonify({'success': False, 'message': 'Не указан ID вопроса'}), 400

    question_id = data['question_id']
    question = Question.query.get_or_404(int(question_id))

    # Проверяем, принадлежит ли вопрос указанному блоку
    if question.block_id != block_id:
        return jsonify({'success': False, 'message': 'Вопрос не принадлежит указанному блоку'}), 403

    # Удаляем вопрос
    try:
        db.session.delete(question)
        db.session.commit()

        # Пересчитываем баллы для оставшихся вопросов в блоке
        recalculate_points_for_block(block_id)

        return jsonify({'success': True, 'message': 'Вопрос успешно удален'})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Ошибка при удалении вопроса: {str(e)}")
        return jsonify({'success': False, 'message': f'Ошибка при удалении вопроса: {str(e)}'}), 500


def recalculate_points_for_block(block_id):
    """
    Пересчитывает баллы для всех вопросов в блоке,
    равномерно распределяя максимальное количество баллов блока.
    """
    block = Block.query.get_or_404(block_id)
    questions = Question.query.filter_by(block_id=block_id).all()

    if not questions:
        return

    # Равномерно распределяем баллы между всеми вопросами
    points_per_question = block.max_points / len(questions)

    for question in questions:
        question.points = points_per_question

    db.session.commit()


@app.route('/admin/olympiad/<int:olympiad_id>/export_excel', methods=['GET'])
@login_required
def export_rankings_excel(olympiad_id):
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Обновляем итоговые баллы перед экспортом
    update_all_final_scores(olympiad_id)

    # Получаем всех участников с результатами, сортируем по итоговому баллу
    participations = Participation.query.filter_by(
        olympiad_id=olympiad_id,
        status='completed'
    ).order_by(Participation.final_score.desc()).all()

    # Создаем workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Результаты"

    # Заголовки с временной информацией
    headers = ['Место', 'ФИО', 'Группа', 'Специальность', 'Баллы за задания',
               'Временной бонус', 'Итоговый балл', 'Время (мин)', 'Скорость', 'Начало', 'Завершение']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="820000", end_color="820000", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    # Максимальное время олимпиады для расчета процентов
    olympiad_duration = (olympiad.end_time - olympiad.start_time).total_seconds()

    # Заполняем данными
    for row, participation in enumerate(participations, 2):
        user = User.query.get(participation.user_id)
        speciality_info = user.get_speciality_info()
        speciality_name = speciality_info['name'] if speciality_info else '-'

        duration = None
        speed_category = 'Неизвестно'
        if participation.duration_seconds:
            duration = participation.duration_seconds / 60
            time_percentage = (participation.duration_seconds / olympiad_duration) * 100

            # Определяем категорию скорости
            if time_percentage <= 25:
                speed_category = '⚡ Молниеносно'
            elif time_percentage <= 50:
                speed_category = '🚀 Очень быстро'
            elif time_percentage <= 75:
                speed_category = '⏱️ Быстро'
            elif time_percentage <= 100:
                speed_category = '✅ В срок'
            else:
                speed_category = '⏰ Превышение времени'

        time_bonus = participation.time_bonus if participation.time_bonus else 0

        data = [
            row - 1,  # Место
            user.full_name,
            user.study_group or '-',
            speciality_name,
            f"{participation.total_points:.2f}",  # Баллы за задания
            f"+{time_bonus:.2f}",  # Временной бонус
            f"{participation.final_score:.2f}",  # Итоговый балл
            f"{duration:.1f}" if duration else '-',
            speed_category,
            participation.start_time.strftime('%d.%m.%Y %H:%M') if participation.start_time else '-',
            participation.finish_time.strftime('%d.%m.%Y %H:%M') if participation.finish_time else '-'
        ]

        for col, value in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(horizontal="center")

    # Автоподгонка ширины колонок
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    # Добавляем информацию об олимпиаде на отдельный лист
    info_ws = wb.create_sheet("Информация об олимпиаде")
    info_data = [
        ['Название олимпиады', olympiad.title],
        ['Описание', olympiad.description],
        ['Дата начала', olympiad.start_time.strftime('%d.%m.%Y %H:%M')],
        ['Дата окончания', olympiad.end_time.strftime('%d.%m.%Y %H:%M')],
        ['Всего участников', len(participations)],
        ['Дата экспорта', datetime.now().strftime('%d.%m.%Y %H:%M')],
        ['Применена система временных бонусов', 'Да'],
        ['', ''],
        ['Система временных бонусов:', ''],
        ['≤25% времени', '+20% от базовых баллов'],
        ['25-50% времени', '+10% от базовых баллов'],
        ['50-75% времени', '+5% от базовых баллов'],
        ['75-100% времени', '+1% от базовых баллов'],
        ['>100% времени', 'Нет бонуса'],
    ]

    for row, (key, value) in enumerate(info_data, 1):
        info_ws.cell(row=row, column=1, value=key).font = Font(bold=True)
        info_ws.cell(row=row, column=2, value=value)

    # Сохраняем в память
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f'results_with_time_{olympiad.title}_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@app.route('/admin/olympiad/<int:olympiad_id>/export_csv', methods=['GET'])
@login_required
def export_rankings_csv(olympiad_id):
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Обновляем итоговые баллы перед экспортом
    update_all_final_scores(olympiad_id)

    # Получаем всех участников с результатами, сортируем по итоговому баллу
    participations = Participation.query.filter_by(
        olympiad_id=olympiad_id,
        status='completed'
    ).order_by(Participation.final_score.desc()).all()

    # Создаем CSV в памяти
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')

    # Заголовки с временной информацией
    writer.writerow(['Место', 'ФИО', 'Группа', 'Специальность', 'Баллы за задания',
                     'Временной бонус', 'Итоговый балл', 'Время (мин)', 'Скорость', 'Начало', 'Завершение'])

    # Максимальное время олимпиады
    olympiad_duration = (olympiad.end_time - olympiad.start_time).total_seconds()

    # Данные
    for i, participation in enumerate(participations, 1):
        user = User.query.get(participation.user_id)
        speciality_info = user.get_speciality_info()
        speciality_name = speciality_info['name'] if speciality_info else '-'

        duration = None
        speed_category = 'Неизвестно'
        if participation.duration_seconds:
            duration = participation.duration_seconds / 60
            time_percentage = (participation.duration_seconds / olympiad_duration) * 100

            if time_percentage <= 25:
                speed_category = 'Молниеносно'
            elif time_percentage <= 50:
                speed_category = 'Очень быстро'
            elif time_percentage <= 75:
                speed_category = 'Быстро'
            elif time_percentage <= 100:
                speed_category = 'В срок'
            else:
                speed_category = 'Превышение времени'

        time_bonus = participation.time_bonus if participation.time_bonus else 0

        writer.writerow([
            i,
            user.full_name,
            user.study_group or '-',
            speciality_name,
            f"{participation.total_points:.2f}",
            f"+{time_bonus:.2f}",
            f"{participation.final_score:.2f}",
            f"{duration:.1f}" if duration else '-',
            speed_category,
            participation.start_time.strftime('%d.%m.%Y %H:%M') if participation.start_time else '-',
            participation.finish_time.strftime('%d.%m.%Y %H:%M') if participation.finish_time else '-'
        ])

    output.seek(0)
    filename = f'results_with_time_{olympiad.title}_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'

    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8-sig')),
        as_attachment=True,
        download_name=filename,
        mimetype='text/csv'
    )


@app.route('/admin/olympiad/<int:olympiad_id>/export_detailed', methods=['GET'])
@login_required
def export_detailed_results(olympiad_id):
    """Детальный экспорт с результатами по блокам"""
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Обновляем итоговые баллы перед экспортом
    update_all_final_scores(olympiad_id)

    # Получаем все блоки олимпиады
    blocks = Block.query.filter_by(olympiad_id=olympiad_id).order_by(Block.order).all()

    # Получаем всех участников, сортируем по итоговому баллу
    participations = Participation.query.filter_by(
        olympiad_id=olympiad_id,
        status='completed'
    ).order_by(Participation.final_score.desc()).all()

    # Создаем workbook с детальным анализом
    wb = Workbook()

    # Основной лист с результатами
    ws = wb.active
    ws.title = "Сводные результаты"

    # Формируем заголовки
    headers = ['Место', 'ФИО', 'Группа', 'Специальность', 'Баллы за задания', 'Временной бонус', 'Итоговый балл']
    for block in blocks:
        headers.append(f'Блок {block.order}: {block.title}')
    headers.extend(['Время (мин)', 'Скорость', 'Начало', 'Завершение'])

    # Записываем заголовки
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="820000", end_color="820000", fill_type="solid")
        cell.alignment = Alignment(horizontal="center")

    # Максимальное время олимпиады
    olympiad_duration = (olympiad.end_time - olympiad.start_time).total_seconds()

    # Заполняем данными
    for row, participation in enumerate(participations, 2):
        user = User.query.get(participation.user_id)
        speciality_info = user.get_speciality_info()
        speciality_name = speciality_info['name'] if speciality_info else '-'

        duration = None
        speed_category = 'Неизвестно'
        if participation.duration_seconds:
            duration = participation.duration_seconds / 60
            time_percentage = (participation.duration_seconds / olympiad_duration) * 100

            if time_percentage <= 25:
                speed_category = 'Молниеносно'
            elif time_percentage <= 50:
                speed_category = 'Очень быстро'
            elif time_percentage <= 75:
                speed_category = 'Быстро'
            elif time_percentage <= 100:
                speed_category = 'В срок'
            else:
                speed_category = 'Превышение времени'

        time_bonus = participation.time_bonus if participation.time_bonus else 0

        # Основные данные
        data = [
            row - 1,  # Место
            user.full_name,
            user.study_group or '-',
            speciality_name,
            f"{participation.total_points:.2f}",  # Баллы за задания
            f"+{time_bonus:.2f}",  # Временной бонус
            f"{participation.final_score:.2f}"  # Итоговый балл
        ]

        # Баллы по блокам
        for block in blocks:
            block_result = BlockResult.query.filter_by(
                participation_id=participation.id,
                block_id=block.id
            ).first()

            if block_result:
                data.append(f"{block_result.points_earned:.1f}")
            else:
                # Подсчитываем из ответов, если нет записи в BlockResult
                questions = Question.query.filter_by(block_id=block.id).all()
                answers = Answer.query.filter(
                    Answer.participation_id == participation.id,
                    Answer.question_id.in_([q.id for q in questions])
                ).all()

                if answers:
                    total_points = sum(answer.points_earned for answer in answers)
                    data.append(f"{total_points:.1f}")
                else:
                    data.append("0.0")

        # Время и статус
        data.extend([
            f"{duration:.1f}" if duration else '-',
            speed_category,
            participation.start_time.strftime('%d.%m.%Y %H:%M') if participation.start_time else '-',
            participation.finish_time.strftime('%d.%m.%Y %H:%M') if participation.finish_time else '-'
        ])

        for col, value in enumerate(data, 1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.alignment = Alignment(horizontal="center")

    # Автоподгонка ширины
    for column in ws.columns:
        max_length = 0
        column_letter = column[0].column_letter
        for cell in column:
            try:
                if len(str(cell.value)) > max_length:
                    max_length = len(str(cell.value))
            except:
                pass
        adjusted_width = min(max_length + 2, 50)
        ws.column_dimensions[column_letter].width = adjusted_width

    # Добавляем статистику по блокам
    stats_ws = wb.create_sheet("Статистика по блокам")

    # Заголовки статистики
    stats_headers = ['Блок', 'Средний балл', 'Максимум', 'Минимум', 'Прошли порог', 'Процент прохождения']
    for col, header in enumerate(stats_headers, 1):
        cell = stats_ws.cell(row=1, column=col, value=header)
        cell.font = Font(bold=True)

    # Статистика по каждому блоку
    for row, block in enumerate(blocks, 2):
        block_results = BlockResult.query.filter_by(block_id=block.id).all()

        if block_results:
            points = [br.points_earned for br in block_results]
            avg_points = sum(points) / len(points)
            max_points = max(points)
            min_points = min(points)

            # Считаем сколько прошли порог
            threshold_points = block.max_points * (block.threshold_percentage / 100)
            passed_threshold = len([p for p in points if p >= threshold_points])
            pass_percentage = (passed_threshold / len(points)) * 100
        else:
            avg_points = max_points = min_points = 0
            passed_threshold = 0
            pass_percentage = 0

        stats_data = [
            f'Блок {block.order}: {block.title}',
            f"{avg_points:.1f}",
            f"{max_points:.1f}",
            f"{min_points:.1f}",
            f"{passed_threshold}/{len(block_results) if block_results else 0}",
            f"{pass_percentage:.1f}%"
        ]

        for col, value in enumerate(stats_data, 1):
            stats_ws.cell(row=row, column=col, value=value)

    # Сохраняем файл
    output = BytesIO()
    wb.save(output)
    output.seek(0)

    filename = f'detailed_results_with_time_{olympiad.title}_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


def get_month_name(month_num):
    """Возвращает название месяца на русском языке"""
    months = {
        1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля',
        5: 'мая', 6: 'июня', 7: 'июля', 8: 'августа',
        9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'
    }
    return months.get(month_num, 'месяца')


# Маршрут для изменения статуса пользователя
@app.route('/admin/users/<int:user_id>/toggle_admin', methods=['POST'])
@login_required
def toggle_user_admin(user_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    user = User.query.get_or_404(user_id)

    # Защита от отключения админки у самого себя
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': 'Нельзя изменить собственный статус администратора'})

    user.is_admin = not user.is_admin
    db.session.commit()

    status = 'добавлены' if user.is_admin else 'отозваны'
    return jsonify({'success': True, 'message': f'Права администратора {status}'})


# Маршрут для удаления пользователя
@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    user = User.query.get_or_404(user_id)

    # Защита от удаления самого себя
    if user.id == current_user.id:
        return jsonify({'success': False, 'message': 'Нельзя удалить собственного пользователя'})

    # Удаляем связанные участия в олимпиадах
    Participation.query.filter_by(user_id=user.id).delete()

    db.session.delete(user)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Пользователь успешно удален'})


@app.route('/admin/olympiad/create', methods=['POST'])
@login_required
def create_olympiad():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    title = request.form.get('title')
    description = request.form.get('description')

    # ИСПРАВЛЕНО: парсим время как локальное
    start_time = datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M')
    end_time = datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M')

    pdf_file = request.files.get('welcome_pdf')
    welcome_pdf = None

    if pdf_file and pdf_file.filename:
        filename = secure_filename(f"{uuid.uuid4()}_{pdf_file.filename}")
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        pdf_file.save(pdf_path)
        welcome_pdf = filename

    olympiad = Olympiad(
        title=title,
        description=description,
        start_time=start_time,
        end_time=end_time,
        welcome_pdf=welcome_pdf,
        created_by=current_user.id
    )

    db.session.add(olympiad)
    db.session.commit()

    return jsonify({'success': True, 'olympiad_id': olympiad.id})


@app.route('/admin/olympiad/<int:olympiad_id>', methods=['GET'])
@login_required
def edit_olympiad(olympiad_id):
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    olympiad = Olympiad.query.get_or_404(olympiad_id)
    blocks = Block.query.filter_by(olympiad_id=olympiad_id).order_by(Block.order).all()

    return render_template('admin/edit_olympiad.html', olympiad=olympiad, blocks=blocks)


@app.route('/admin/olympiad/<int:olympiad_id>/update', methods=['POST'])
@login_required
def update_olympiad(olympiad_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    olympiad = Olympiad.query.get_or_404(olympiad_id)

    olympiad.title = request.form.get('title')
    olympiad.description = request.form.get('description')

    # ИСПРАВЛЕНО: парсим время как локальное
    olympiad.start_time = datetime.strptime(request.form.get('start_time'), '%Y-%m-%dT%H:%M')
    olympiad.end_time = datetime.strptime(request.form.get('end_time'), '%Y-%m-%dT%H:%M')

    pdf_file = request.files.get('welcome_pdf')
    if pdf_file and pdf_file.filename:
        # Удаляем старый файл, если он есть
        if olympiad.welcome_pdf:
            old_path = os.path.join(app.config['UPLOAD_FOLDER'], olympiad.welcome_pdf)
            if os.path.exists(old_path):
                os.remove(old_path)

        filename = secure_filename(f"{uuid.uuid4()}_{pdf_file.filename}")
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        pdf_file.save(pdf_path)
        olympiad.welcome_pdf = filename

    db.session.commit()

    return jsonify({'success': True})


@app.route('/admin/olympiad/<int:olympiad_id>/add_block', methods=['POST'])
@login_required
def add_block(olympiad_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Получаем максимальный order для блоков в олимпиаде
    max_order = db.session.query(db.func.max(Block.order)).filter(Block.olympiad_id == olympiad_id).scalar() or 0

    title = request.form.get('title')
    description = request.form.get('description')
    max_points = float(request.form.get('max_points'))
    threshold_percentage = float(request.form.get('threshold_percentage'))

    block = Block(
        olympiad_id=olympiad_id,
        title=title,
        description=description,
        max_points=max_points,
        threshold_percentage=threshold_percentage,
        order=max_order + 1
    )

    db.session.add(block)
    db.session.commit()

    return jsonify({'success': True, 'block_id': block.id})


@app.route('/admin/block/<int:block_id>/edit', methods=['GET'])
@login_required
def edit_block(block_id):
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    block = Block.query.get_or_404(block_id)
    questions = Question.query.filter_by(block_id=block_id).all()

    # Предварительная обработка данных вопросов
    questions = prepare_question_data(questions)

    return render_template('admin/edit_block.html', block=block, questions=questions)


@app.route('/admin/block/<int:block_id>/add_question', methods=['POST'])
@login_required
def add_question(block_id):
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    block = Block.query.get_or_404(block_id)

    question_type = request.form.get('question_type')
    text = request.form.get('text')

    # Подсчет количества вопросов в блоке для равномерного распределения баллов
    questions_count = Question.query.filter_by(block_id=block_id).count() + 1
    points_per_question = block.max_points / questions_count

    # Обновляем баллы для существующих вопросов
    for q in Question.query.filter_by(block_id=block_id).all():
        q.points = points_per_question

    if question_type == 'test':
        options = request.form.getlist('options[]')
        correct_answers = request.form.getlist('correct_answers[]')

        question = Question(
            block_id=block_id,
            question_type=question_type,
            text=text,
            options=json.dumps(options),
            correct_answers=json.dumps(correct_answers),
            points=points_per_question
        )
    elif question_type == 'matching':
        left_items = request.form.getlist('left_items[]')
        right_items = request.form.getlist('right_items[]')
        matches = []

        for i in range(len(left_items)):
            matches.append({
                'left': left_items[i],
                'right': right_items[i]
            })

        question = Question(
            block_id=block_id,
            question_type=question_type,
            text=text,
            matches=json.dumps(matches),
            points=points_per_question
        )

    db.session.add(question)
    db.session.commit()

    return jsonify({'success': True, 'question_id': question.id})


@app.route('/olympiad/<int:olympiad_id>/view', methods=['GET'])
@login_required
def view_olympiad(olympiad_id):
    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # ИСПРАВЛЕНО: используем локальное время для проверки доступности
    current_time = get_current_time()
    if not current_user.is_admin and olympiad.end_time < current_time:
        flash('Олимпиада завершена', 'error')
        return redirect(url_for('index'))

    # Проверяем, зарегистрирован ли пользователь на эту олимпиаду
    participation = Participation.query.filter_by(
        user_id=current_user.id,
        olympiad_id=olympiad_id
    ).first()

    return render_template('olympiad/view.html', olympiad=olympiad, participation=participation)


@app.route('/olympiad/<int:olympiad_id>/register', methods=['POST'])
@login_required
def register_olympiad(olympiad_id):
    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Проверяем, не зарегистрирован ли пользователь уже
    existing = Participation.query.filter_by(
        user_id=current_user.id,
        olympiad_id=olympiad_id
    ).first()

    if existing:
        return jsonify({'success': False, 'message': 'Вы уже зарегистрированы на эту олимпиаду'})

    participation = Participation(
        user_id=current_user.id,
        olympiad_id=olympiad_id,
        status='registered'
    )

    db.session.add(participation)
    db.session.commit()

    return jsonify({'success': True})


@app.route('/olympiad/<int:olympiad_id>/start', methods=['POST'])
@login_required
def start_olympiad(olympiad_id):
    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Проверяем, не начата ли уже олимпиада
    participation = Participation.query.filter_by(
        user_id=current_user.id,
        olympiad_id=olympiad_id
    ).first()

    if not participation:
        return jsonify({'success': False, 'message': 'Вы не зарегистрированы на эту олимпиаду'})

    if participation.status == 'in_progress':
        return jsonify({'success': True, 'redirect': url_for('take_olympiad', olympiad_id=olympiad_id)})

    if participation.status == 'completed':
        return jsonify({'success': False, 'message': 'Вы уже завершили эту олимпиаду'})

    # ИСПРАВЛЕНО: используем локальное время для проверки времени начала
    current_time = get_current_time()
    if current_time < olympiad.start_time:
        return jsonify({
            'success': False,
            'message': f'Олимпиада начнется {olympiad.start_time.strftime("%d.%m.%Y в %H:%M")}'
        })

    if current_time > olympiad.end_time:
        return jsonify({'success': False, 'message': 'Время олимпиады истекло'})

    # Ищем первый блок
    first_block = Block.query.filter_by(olympiad_id=olympiad_id, order=1).first()
    if not first_block:
        return jsonify({'success': False, 'message': 'Олимпиада не содержит блоков'})

    participation.status = 'in_progress'
    participation.start_time = current_time
    participation.current_block = first_block.id

    db.session.commit()

    return jsonify({'success': True, 'redirect': url_for('take_olympiad', olympiad_id=olympiad_id)})


@app.route('/olympiad/<int:olympiad_id>/take', methods=['GET'])
@login_required
def take_olympiad(olympiad_id):
    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Проверяем участие пользователя
    participation = Participation.query.filter_by(
        user_id=current_user.id,
        olympiad_id=olympiad_id,
        status='in_progress'
    ).first()

    if not participation:
        flash('Вы не участвуете в этой олимпиаде или она уже завершена', 'error')
        return redirect(url_for('view_olympiad', olympiad_id=olympiad_id))

    # Получаем текущий блок
    current_block = Block.query.get(participation.current_block)
    if not current_block:
        flash('Ошибка: блок не найден', 'error')
        return redirect(url_for('view_olympiad', olympiad_id=olympiad_id))

    # Получаем вопросы текущего блока
    questions = Question.query.filter_by(block_id=current_block.id).all()

    # Подготавливаем данные вопросов для корректного отображения
    questions = prepare_question_data(questions)

    # Получаем ответы пользователя на вопросы этого блока
    user_answers = {}
    for question in questions:
        answer = Answer.query.filter_by(
            participation_id=participation.id,
            question_id=question.id
        ).first()
        if answer:
            try:
                user_answers[question.id] = json.loads(answer.answer_data)
            except:
                user_answers[question.id] = []

    return render_template(
        'olympiad/take.html',
        olympiad=olympiad,
        block=current_block,
        questions=questions,
        user_answers=user_answers,
        participation=participation
    )


@app.route('/olympiad/<int:olympiad_id>/submit_answer', methods=['POST'])
@login_required
def submit_answer(olympiad_id):
    data = request.get_json()
    question_id = data.get('question_id')
    answer_data = data.get('answer_data')

    question = Question.query.get_or_404(question_id)

    # Проверяем участие пользователя
    participation = Participation.query.filter_by(
        user_id=current_user.id,
        olympiad_id=olympiad_id,
        status='in_progress'
    ).first()

    if not participation:
        return jsonify({'success': False, 'message': 'Вы не участвуете в этой олимпиаде'}), 403

    # Проверяем, относится ли вопрос к текущему блоку
    if question.block_id != participation.current_block:
        return jsonify({'success': False, 'message': 'Вопрос не принадлежит текущему блоку'}), 403

    # Проверяем правильность ответа
    is_correct = False
    points_earned = 0

    if question.question_type == 'test':
        correct_answers = set(json.loads(question.correct_answers))
        user_answers = set(answer_data)

        if correct_answers == user_answers:
            is_correct = True
            points_earned = question.points

    elif question.question_type == 'matching':
        matches = json.loads(question.matches)
        correct_matches = {match['left']: match['right'] for match in matches}

        user_correct_count = 0
        for pair in answer_data:
            if pair['left'] in correct_matches and correct_matches[pair['left']] == pair['right']:
                user_correct_count += 1

        # Если все пары совпали
        if user_correct_count == len(matches):
            is_correct = True
            points_earned = question.points
        else:
            # Частичные баллы за частично правильные ответы
            points_earned = (user_correct_count / len(matches)) * question.points

    # Проверяем, есть ли уже ответ на этот вопрос
    existing_answer = Answer.query.filter_by(
        participation_id=participation.id,
        question_id=question_id
    ).first()

    if existing_answer:
        # Обновляем существующий ответ
        existing_answer.answer_data = json.dumps(answer_data)
        existing_answer.is_correct = is_correct
        existing_answer.points_earned = points_earned
        existing_answer.answered_at = get_current_time()
    else:
        # Создаем новый ответ
        answer = Answer(
            participation_id=participation.id,
            question_id=question_id,
            answer_data=json.dumps(answer_data),
            is_correct=is_correct,
            points_earned=points_earned
        )
        db.session.add(answer)

    # Обновляем общий балл пользователя
    if existing_answer:
        participation.total_points = participation.total_points - existing_answer.points_earned + points_earned
    else:
        participation.total_points += points_earned

    db.session.commit()

    return jsonify({'success': True, 'points': points_earned})


@app.route('/olympiad/<int:olympiad_id>/ranking', methods=['GET'])
@login_required
def get_ranking(olympiad_id):
    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Проверяем участие пользователя
    participation = Participation.query.filter_by(
        user_id=current_user.id,
        olympiad_id=olympiad_id
    ).first()

    if not participation:
        return jsonify({'success': False, 'message': 'Вы не участвуете в этой олимпиаде'})

    # Получаем текущий блок
    current_block = Block.query.get(participation.current_block)
    if not current_block:
        return jsonify({'success': False, 'message': 'Ошибка: блок не найден'})

    # Получаем предыдущий блок, который завершил пользователь
    prev_block = None
    if current_block.order > 1:
        prev_block = Block.query.filter_by(
            olympiad_id=olympiad_id,
            order=current_block.order - 1
        ).first()
    else:
        # Если это первый блок, то берем его же
        prev_block = current_block

    # Получаем результаты блока
    block_result = BlockResult.query.filter_by(
        participation_id=participation.id,
        block_id=prev_block.id
    ).first()

    # Устанавливаем значения баллов
    block_points = 0
    block_max_points = prev_block.max_points

    if block_result:
        block_points = block_result.points_earned
    else:
        # Если нет результатов блока, подсчитываем из ответов
        questions = Question.query.filter_by(block_id=prev_block.id).all()
        answers = Answer.query.filter(
            Answer.participation_id == participation.id,
            Answer.question_id.in_([q.id for q in questions])
        ).all()

        if answers:
            block_points = sum(answer.points_earned for answer in answers)

    # Рассчитываем место только на основе завершенных участий
    completed_participations = Participation.query.filter(
        Participation.olympiad_id == olympiad_id,
        Participation.status == 'completed'
    ).order_by(Participation.final_score.desc()).all()

    # Если участник еще не завершил олимпиаду, добавляем в список и для него
    if participation.status != 'completed' and participation not in completed_participations:
        completed_participations.append(participation)
        # Пересортируем список - для незавершенных используем total_points
        completed_participations.sort(key=lambda p: p.final_score if p.status == 'completed' else p.total_points,
                                      reverse=True)

    # Находим место текущего пользователя
    user_rank = 0
    prev_points = None
    skip_ranks = 0

    for i, p in enumerate(completed_participations):
        # Получаем баллы для сравнения
        current_points = p.final_score if p.status == 'completed' else p.total_points

        # Если у участников одинаковое количество баллов, они делят место
        if prev_points is not None and current_points == prev_points:
            skip_ranks += 1
        else:
            skip_ranks = 0

        prev_points = current_points

        if p.id == participation.id:
            user_rank = i + 1 - skip_ranks
            break

    # Подсчитываем общее количество участников и участников с непустыми баллами
    all_participations = Participation.query.filter_by(olympiad_id=olympiad_id).all()
    participations_with_points = [p for p in all_participations if p.total_points > 0]

    # Вычисляем процент от максимально возможного места
    rank_percentage = 0
    if len(participations_with_points) > 0:
        rank_percentage = 100 - ((user_rank - 1) / len(participations_with_points) * 100)

    # Для первого блока всегда возвращаем рейтинг 0, но сохраняем остальные данные
    if prev_block.order == 1:
        user_rank = 0

    # Количество участников должно быть не менее 1 (сам пользователь)
    total_participants = max(1, len(all_participations))

    # Используем итоговый балл для завершенных участий, иначе обычный
    display_points = participation.final_score if participation.status == 'completed' else participation.total_points

    response_data = {
        'success': True,
        'rank_position': user_rank,
        'rank_percentage': round(rank_percentage, 1),
        'block_points': round(block_points, 1),
        'block_max_points': round(block_max_points, 1),
        'total_points': round(display_points, 1),
        'total_participants': total_participants
    }

    return jsonify(response_data)


@app.route('/olympiad/<int:olympiad_id>/submit_block', methods=['POST'])
@login_required
def submit_block(olympiad_id):
    # Проверяем участие пользователя
    participation = Participation.query.filter_by(
        user_id=current_user.id,
        olympiad_id=olympiad_id,
        status='in_progress'
    ).first()

    if not participation:
        return jsonify({'success': False, 'message': 'Вы не участвуете в этой олимпиаде'}), 403

    current_block = Block.query.get(participation.current_block)
    if not current_block:
        return jsonify({'success': False, 'message': 'Текущий блок не найден'}), 404

    # Проверяем, ответил ли пользователь на все вопросы блока
    questions = Question.query.filter_by(block_id=current_block.id).all()
    answered_questions = Answer.query.filter(
        Answer.participation_id == participation.id,
        Answer.question_id.in_([q.id for q in questions])
    ).count()

    if answered_questions < len(questions):
        return jsonify({
            'success': False,
            'message': f'Вы ответили только на {answered_questions} из {len(questions)} вопросов'
        })

    # Подсчитываем процент правильных ответов и баллы
    total_points_possible = sum(q.points for q in questions)

    # Получаем баллы за все ответы в текущем блоке
    block_answers = Answer.query.filter(
        Answer.participation_id == participation.id,
        Answer.question_id.in_([q.id for q in questions])
    ).all()

    user_points = sum(answer.points_earned for answer in block_answers)

    # Сохраняем баллы за блок
    block_result = BlockResult.query.filter_by(
        participation_id=participation.id,
        block_id=current_block.id
    ).first()

    if not block_result:
        block_result = BlockResult(
            participation_id=participation.id,
            block_id=current_block.id,
            points_earned=user_points,
            completed_at=get_current_time()
        )
        db.session.add(block_result)
    else:
        block_result.points_earned = user_points
        block_result.completed_at = get_current_time()

    percentage_correct = (user_points / total_points_possible) * 100 if total_points_possible > 0 else 0

    # Проверяем, достаточно ли баллов для перехода к следующему блоку
    if percentage_correct < current_block.threshold_percentage:
        # Недостаточно баллов, завершаем олимпиаду
        participation.status = 'completed'
        participation.finish_time = get_current_time()

        # Рассчитываем итоговый балл с учетом времени
        calculate_final_score(participation)

        db.session.commit()

        return jsonify({
            'success': True,
            'completed': True,
            'message': f'Вы набрали {percentage_correct:.1f}%, что меньше порогового значения {current_block.threshold_percentage}%. Олимпиада завершена.',
            'redirect': url_for('olympiad_results', olympiad_id=olympiad_id),
            'block_data': {
                'block_id': current_block.id,
                'points_earned': user_points,
                'total_points_possible': total_points_possible
            }
        })

    # Ищем следующий блок
    next_block = Block.query.filter_by(
        olympiad_id=olympiad_id,
        order=current_block.order + 1
    ).first()

    if not next_block:
        # Это был последний блок, завершаем олимпиаду
        participation.status = 'completed'
        participation.finish_time = get_current_time()

        # Рассчитываем итоговый балл с учетом времени
        calculate_final_score(participation)

        db.session.commit()

        return jsonify({
            'success': True,
            'completed': True,
            'message': 'Поздравляем! Вы успешно завершили все блоки олимпиады.',
            'redirect': url_for('olympiad_results', olympiad_id=olympiad_id),
            'block_data': {
                'block_id': current_block.id,
                'points_earned': user_points,
                'total_points_possible': total_points_possible
            }
        })

    # Переходим к следующему блоку
    participation.current_block = next_block.id

    # Обязательно фиксируем изменения в базе данных перед ответом
    db.session.commit()

    return jsonify({
        'success': True,
        'completed': False,
        'message': f'Вы успешно завершили блок и набрали {percentage_correct:.1f}%. Переходим к следующему блоку.',
        'redirect': url_for('take_olympiad', olympiad_id=olympiad_id),
        'block_data': {
            'block_id': current_block.id,
            'points_earned': user_points,
            'total_points_possible': total_points_possible
        }
    })


@app.route('/olympiad/<int:olympiad_id>/results', methods=['GET'])
@login_required
def olympiad_results(olympiad_id):
    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Получаем участие пользователя
    participation = Participation.query.filter_by(
        user_id=current_user.id,
        olympiad_id=olympiad_id
    ).first()

    if not participation or participation.status != 'completed':
        flash('Вы еще не завершили эту олимпиаду', 'error')
        return redirect(url_for('view_olympiad', olympiad_id=olympiad_id))

    # Обновляем итоговые баллы для всех участников
    update_all_final_scores(olympiad_id)

    # Получаем рейтинг на основе итогового балла
    rankings = Participation.query.filter_by(
        olympiad_id=olympiad_id,
        status='completed'
    ).order_by(Participation.final_score.desc()).all()

    user_rank = None
    for i, p in enumerate(rankings, 1):
        if p.id == participation.id:
            user_rank = i
            break

    # Детальная статистика по блокам
    blocks = Block.query.filter_by(olympiad_id=olympiad_id).order_by(Block.order).all()
    block_stats = []

    for block in blocks:
        questions = Question.query.filter_by(block_id=block.id).all()

        # Получаем ответы пользователя на вопросы этого блока
        answers = Answer.query.filter(
            Answer.participation_id == participation.id,
            Answer.question_id.in_([q.id for q in questions])
        ).all()

        # Если нет ответов на этот блок, значит пользователь до него не дошел
        if not answers:
            block_stats.append({
                'block': block,
                'attempted': False,
                'total_possible': sum(q.points for q in questions),
                'user_points': 0,
                'percentage': 0
            })
            continue

        total_possible = sum(q.points for q in questions)
        user_points = sum(a.points_earned for a in answers)
        percentage = (user_points / total_possible) * 100 if total_possible > 0 else 0

        block_stats.append({
            'block': block,
            'attempted': True,
            'total_possible': total_possible,
            'user_points': user_points,
            'percentage': percentage
        })

    return render_template(
        'olympiad/results.html',
        olympiad=olympiad,
        participation=participation,
        rankings=rankings,
        user_rank=user_rank,
        block_stats=block_stats,
        total_participants=len(rankings)
    )


@app.route('/admin/olympiad/<int:olympiad_id>/rankings', methods=['GET'])
@login_required
def admin_rankings(olympiad_id):
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Обновляем итоговые баллы перед отображением
    update_all_final_scores(olympiad_id)

    # Получаем все завершенные участия, сортируем по итоговому баллу
    participations = Participation.query.filter_by(
        olympiad_id=olympiad_id,
        status='completed'
    ).order_by(Participation.final_score.desc()).all()

    # Получаем информацию о пользователях
    user_ids = [p.user_id for p in participations]
    users = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()}

    return render_template(
        'admin/rankings.html',
        olympiad=olympiad,
        participations=participations,
        users=users
    )


@app.route('/admin/olympiad/<int:olympiad_id>/export_pdf', methods=['GET'])
@login_required
def export_rankings_pdf(olympiad_id):
    if not current_user.is_admin:
        flash('У вас нет доступа к этой странице', 'error')
        return redirect(url_for('index'))

    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Обновляем итоговые баллы перед экспортом
    update_all_final_scores(olympiad_id)

    # Получаем все завершенные участия, сортируем по итоговому баллу
    participations = Participation.query.filter_by(
        olympiad_id=olympiad_id,
        status='completed'
    ).order_by(Participation.final_score.desc()).all()

    # Получаем информацию о пользователях
    user_ids = [p.user_id for p in participations]
    users = {u.id: u for u in User.query.filter(User.id.in_(user_ids)).all()}

    # Создаем HTML для PDF
    html = render_template(
        'admin/rankings_pdf.html',
        olympiad=olympiad,
        participations=participations,
        users=users
    )

    # Генерируем PDF
    pdf = pdfkit.from_string(html, False)

    # Отправляем PDF как файл
    buffer = BytesIO(pdf)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f'rankings_{olympiad.title}_{datetime.now().strftime("%Y%m%d")}.pdf',
        mimetype='application/pdf'
    )


# Добавляем роут для принудительного пересчета временных коэффициентов
@app.route('/admin/olympiad/<int:olympiad_id>/recalculate_scores', methods=['POST'])
@login_required
def recalculate_scores(olympiad_id):
    """Принудительный пересчет итоговых баллов с временным коэффициентом"""
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    try:
        update_all_final_scores(olympiad_id)
        return jsonify({'success': True, 'message': 'Итоговые баллы успешно пересчитаны'})
    except Exception as e:
        return jsonify({'success': False, 'message': f'Ошибка при пересчете: {str(e)}'}), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()

        # Проверяем и добавляем новые столбцы, если их нет
        try:
            # Попробуем выполнить запрос к новым столбцам
            db.session.execute('SELECT final_score, duration_seconds, time_bonus FROM participation LIMIT 1')
        except:
            # Если столбцы не существуют, добавляем их
            try:
                db.session.execute('ALTER TABLE participation ADD COLUMN final_score FLOAT DEFAULT 0')
                db.session.execute('ALTER TABLE participation ADD COLUMN duration_seconds FLOAT DEFAULT NULL')
                db.session.execute('ALTER TABLE participation ADD COLUMN time_bonus FLOAT DEFAULT 0')
                db.session.commit()
                print("Добавлены новые столбцы для временного коэффициента")
            except:
                print("Столбцы уже существуют или произошла ошибка при добавлении")

        # Создаем администратора, если его нет
        admin = User.query.filter_by(email='admin@example.com').first()
        if not admin:
            admin = User(
                email='admin@example.com',
                full_name='Administrator',
                is_admin=True
            )
            admin.set_password('admin')
            db.session.add(admin)
            db.session.commit()
            print("Создан администратор: admin@example.com / admin")

        # Пересчитываем итоговые баллы для всех существующих завершенных участий
        try:
            completed_participations = Participation.query.filter_by(status='completed').all()
            for participation in completed_participations:
                if participation.final_score == 0:  # Если еще не рассчитан
                    calculate_final_score(participation)
            db.session.commit()
            print(f"Пересчитаны итоговые баллы для {len(completed_participations)} участий")
        except Exception as e:
            print(f"Ошибка при пересчете существующих баллов: {e}")

    app.run(debug=True)