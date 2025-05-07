from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(100), nullable=True)  # ФИО (опционально)
    group = db.Column(db.String(50), nullable=True)  # Группа (опционально)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    olympiad_participations = db.relationship('Participation', backref='user', lazy=True)


class Olympiad(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    welcome_pdf = db.Column(db.String(255), nullable=True)  # Путь к PDF файлу
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    blocks = db.relationship('Block', backref='olympiad', lazy=True, order_by='Block.order')
    participants = db.relationship('Participation', backref='olympiad', lazy=True)

    creator = db.relationship('User', backref='created_olympiads')


class Block(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    olympiad_id = db.Column(db.Integer, db.ForeignKey('olympiad.id'), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    order = db.Column(db.Integer, nullable=False)  # Порядок блока в олимпиаде
    total_points = db.Column(db.Integer, default=0)  # Общее количество баллов за блок
    threshold_percentage = db.Column(db.Integer, default=0)  # Порог в процентах для допуска к следующему блоку

    questions = db.relationship('Question', backref='block', lazy=True)


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    block_id = db.Column(db.Integer, db.ForeignKey('block.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # test, matching, etc.
    points = db.Column(db.Integer, nullable=False, default=0)  # Баллы за вопрос

    options = db.relationship('Option', backref='question', lazy=True)
    answers = db.relationship('Answer', backref='question', lazy=True)


class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    is_correct = db.Column(db.Boolean, default=False)  # Для тестов
    match_id = db.Column(db.Integer, nullable=True)  # Для заданий на соответствие


class Participation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    olympiad_id = db.Column(db.Integer, db.ForeignKey('olympiad.id'), nullable=False)
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime, nullable=True)
    current_block = db.Column(db.Integer, nullable=True)  # ID текущего блока
    is_completed = db.Column(db.Boolean, default=False)
    is_disqualified = db.Column(db.Boolean, default=False)  # Флаг дисквалификации
    disqualification_reason = db.Column(db.String(255), nullable=True)  # Причина дисквалификации
    total_score = db.Column(db.Integer, default=0)
    completion_time = db.Column(db.Integer, nullable=True)  # Время прохождения в секундах

    block_results = db.relationship('BlockResult', backref='participation', lazy=True)


class BlockResult(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participation_id = db.Column(db.Integer, db.ForeignKey('participation.id'), nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey('block.id'), nullable=False)
    score = db.Column(db.Integer, default=0)
    percentage = db.Column(db.Float, default=0.0)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)
    passed_threshold = db.Column(db.Boolean, default=False)

    block = db.relationship('Block')


class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    participation_id = db.Column(db.Integer, db.ForeignKey('participation.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    selected_option_id = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=True)  # Для тестов
    matching_data = db.Column(db.Text, nullable=True)  # JSON для заданий на соответствие
    is_correct = db.Column(db.Boolean, default=False)
    points_earned = db.Column(db.Integer, default=0)

    selected_option = db.relationship('Option', foreign_keys=[selected_option_id])