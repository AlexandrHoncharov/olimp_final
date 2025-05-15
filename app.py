from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import os
import json
import pdfkit
from io import BytesIO
import uuid

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

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    study_group = db.Column(db.String(50), nullable=True)
    is_admin = db.Column(db.Boolean, default=False)
    participations = db.relationship('Participation', backref='user', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


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
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

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
    total_points = db.Column(db.Float, default=0)
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
    answered_at = db.Column(db.DateTime, default=datetime.utcnow)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_admin:
            olympiads = Olympiad.query.all()
        else:
            current_time = datetime.utcnow()
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


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        full_name = request.form.get('full_name')
        study_group = request.form.get('study_group')

        if User.query.filter_by(email=email).first():
            flash('Email уже зарегистрирован', 'error')
            return redirect(url_for('register'))

        user = User(email=email, full_name=full_name, study_group=study_group)
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


@app.route('/admin/olympiad/create', methods=['POST'])
@login_required
def create_olympiad():
    if not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Доступ запрещен'}), 403

    title = request.form.get('title')
    description = request.form.get('description')
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

    # Проверяем, может ли пользователь просматривать эту олимпиаду
    current_time = datetime.utcnow()
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

    # Проверяем, наступило ли время начала олимпиады
    current_time = datetime.utcnow()
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
        existing_answer.answered_at = datetime.utcnow()
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
    ).order_by(Participation.total_points.desc()).all()

    # Если участник еще не завершил олимпиаду, добавляем в список и для него
    if participation.status != 'completed' and participation not in completed_participations:
        completed_participations.append(participation)
        # Пересортируем список
        completed_participations.sort(key=lambda p: p.total_points, reverse=True)

    # Находим место текущего пользователя
    user_rank = 0
    prev_points = None
    skip_ranks = 0

    for i, p in enumerate(completed_participations):
        # Если у участников одинаковое количество баллов, они делят место
        if prev_points is not None and p.total_points == prev_points:
            skip_ranks += 1
        else:
            skip_ranks = 0

        prev_points = p.total_points

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

    response_data = {
        'success': True,
        'rank_position': user_rank,
        'rank_percentage': round(rank_percentage, 1),
        'block_points': round(block_points, 1),
        'block_max_points': round(block_max_points, 1),
        'total_points': round(participation.total_points, 1),
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

    # Сохраняем баллы за блок для отображения в модальном окне
    # Создаем запись с данными текущего блока (или обновляем существующую)
    block_result = BlockResult.query.filter_by(
        participation_id=participation.id,
        block_id=current_block.id
    ).first()

    if not block_result:
        block_result = BlockResult(
            participation_id=participation.id,
            block_id=current_block.id,
            points_earned=user_points,
            completed_at=datetime.utcnow()
        )
        db.session.add(block_result)
    else:
        block_result.points_earned = user_points
        block_result.completed_at = datetime.utcnow()

    percentage_correct = (user_points / total_points_possible) * 100 if total_points_possible > 0 else 0

    # Проверяем, достаточно ли баллов для перехода к следующему блоку
    if percentage_correct < current_block.threshold_percentage:
        # Недостаточно баллов, завершаем олимпиаду
        participation.status = 'completed'
        participation.finish_time = datetime.utcnow()
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
        participation.finish_time = datetime.utcnow()
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

    # Получаем рейтинг
    rankings = Participation.query.filter_by(
        olympiad_id=olympiad_id,
        status='completed'
    ).order_by(Participation.total_points.desc()).all()

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

    # Получаем все завершенные участия
    participations = Participation.query.filter_by(
        olympiad_id=olympiad_id,
        status='completed'
    ).order_by(Participation.total_points.desc()).all()

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

    # Получаем все завершенные участия
    participations = Participation.query.filter_by(
        olympiad_id=olympiad_id,
        status='completed'
    ).order_by(Participation.total_points.desc()).all()

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


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
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

    app.run(debug=True)