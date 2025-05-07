# routes.py

from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, jsonify, session
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from models import db, User, Olympiad, Block, Question, Option, Participation, BlockResult, Answer
from forms import LoginForm, RegistrationForm, OlympiadForm, BlockForm, QuestionForm
import os
from datetime import datetime, timedelta
import json
import csv
import io
from datetime import datetime

# Создаем блюпринты для разных частей приложения
auth_bp = Blueprint('auth', __name__)
admin_bp = Blueprint('admin', __name__)
participant_bp = Blueprint('participant', __name__)

# --------------------------------
# Авторизация и регистрация
# --------------------------------

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('participant.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('participant.dashboard'))
        else:
            flash('Неверный email или пароль', 'danger')

    return render_template('auth/login.html', form=form)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('participant.dashboard'))

    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        user = User(
            email=form.email.data,
            password=hashed_password,
            full_name=form.full_name.data,
            group=form.group.data
        )
        db.session.add(user)
        db.session.commit()

        flash('Ваш аккаунт создан! Теперь вы можете войти.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html', form=form)

# --------------------------------
# Административная панель
# --------------------------------

@admin_bp.route('/dashboard')
@login_required
def dashboard():
    if not current_user.is_admin:
        abort(403)

    olympiads = Olympiad.query.filter_by(created_by=current_user.id).all()
    now = datetime.utcnow()  # Получаем текущее время
    return render_template('admin/dashboard.html', olympiads=olympiads, now=now)

@admin_bp.route('/olympiad/new', methods=['GET', 'POST'])
@login_required
def new_olympiad():
    if not current_user.is_admin:
        abort(403)

    form = OlympiadForm()
    if form.validate_on_submit():
        # Обработка PDF файла
        pdf_path = None
        if form.welcome_pdf.data:
            filename = secure_filename(form.welcome_pdf.data.filename)
            pdf_path = os.path.join('uploads/pdfs', filename)
            form.welcome_pdf.data.save(pdf_path)

        olympiad = Olympiad(
            title=form.title.data,
            description=form.description.data,
            welcome_pdf=pdf_path,
            start_time=form.start_time.data,
            end_time=form.end_time.data,
            created_by=current_user.id
        )

        db.session.add(olympiad)
        db.session.commit()

        flash('Олимпиада успешно создана!', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/new_olympiad.html', form=form)

@admin_bp.route('/olympiad/<int:olympiad_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_olympiad(olympiad_id):
    if not current_user.is_admin:
        abort(403)

    olympiad = Olympiad.query.get_or_404(olympiad_id)
    if olympiad.created_by != current_user.id:
        abort(403)

    form = OlympiadForm(obj=olympiad)
    if form.validate_on_submit():
        # Обработка PDF файла
        if form.welcome_pdf.data:
            filename = secure_filename(form.welcome_pdf.data.filename)
            pdf_path = os.path.join('uploads/pdfs', filename)
            form.welcome_pdf.data.save(pdf_path)
            olympiad.welcome_pdf = pdf_path

        olympiad.title = form.title.data
        olympiad.description = form.description.data
        olympiad.start_time = form.start_time.data
        olympiad.end_time = form.end_time.data

        db.session.commit()

        flash('Олимпиада успешно обновлена!', 'success')
        return redirect(url_for('admin.dashboard'))

    return render_template('admin/edit_olympiad.html', form=form, olympiad=olympiad)

@admin_bp.route('/olympiad/<int:olympiad_id>/block/new', methods=['GET', 'POST'])
@login_required
def new_block(olympiad_id):
    if not current_user.is_admin:
        abort(403)

    olympiad = Olympiad.query.get_or_404(olympiad_id)
    if olympiad.created_by != current_user.id:
        abort(403)

    form = BlockForm()
    if form.validate_on_submit():
        # Определяем порядок нового блока
        max_order = db.session.query(db.func.max(Block.order)).filter_by(olympiad_id=olympiad_id).scalar() or 0

        block = Block(
            olympiad_id=olympiad_id,
            title=form.title.data,
            description=form.description.data,
            order=max_order + 1,
            total_points=form.total_points.data,
            threshold_percentage=form.threshold_percentage.data
        )

        db.session.add(block)
        db.session.commit()

        flash('Блок успешно создан!', 'success')
        return redirect(url_for('admin.manage_olympiad', olympiad_id=olympiad_id))

    return render_template('admin/new_block.html', form=form, olympiad=olympiad)

@admin_bp.route('/olympiad/<int:olympiad_id>')
@login_required
def manage_olympiad(olympiad_id):
    if not current_user.is_admin:
        abort(403)

    olympiad = Olympiad.query.get_or_404(olympiad_id)
    if olympiad.created_by != current_user.id:
        abort(403)

    blocks = Block.query.filter_by(olympiad_id=olympiad_id).order_by(Block.order).all()
    now = datetime.utcnow()  # Получаем текущее время

    return render_template('admin/manage_olympiad.html', olympiad=olympiad, blocks=blocks, now=now)

@admin_bp.route('/block/<int:block_id>/question/new', methods=['GET', 'POST'])
@login_required
def new_question(block_id):
    if not current_user.is_admin:
        abort(403)

    block = Block.query.get_or_404(block_id)
    olympiad = Olympiad.query.get_or_404(block.olympiad_id)

    if olympiad.created_by != current_user.id:
        abort(403)

    form = QuestionForm()
    if form.validate_on_submit():
        question = Question(
            block_id=block_id,
            question_text=form.question_text.data,
            question_type=form.question_type.data,
            points=form.points.data
        )

        db.session.add(question)
        db.session.commit()

        # Обработка опций в зависимости от типа вопроса
        if form.question_type.data == 'test':
            # Для тестовых вопросов добавляем варианты ответов
            options_data = json.loads(form.options.data)
            for opt_data in options_data:
                option = Option(
                    question_id=question.id,
                    text=opt_data['text'],
                    is_correct=opt_data['is_correct']
                )
                db.session.add(option)

        elif form.question_type.data == 'matching':
            # Для вопросов на соответствие добавляем пары
            pairs_data = json.loads(form.matching_pairs.data)
            for pair in pairs_data:
                # Левая часть пары
                left_option = Option(
                    question_id=question.id,
                    text=pair['left'],
                    match_id=pair['pair_id']
                )
                db.session.add(left_option)

                # Правая часть пары
                right_option = Option(
                    question_id=question.id,
                    text=pair['right'],
                    match_id=pair['pair_id']
                )
                db.session.add(right_option)

        db.session.commit()

        flash('Вопрос успешно добавлен!', 'success')
        return redirect(url_for('admin.manage_block', block_id=block_id))

    return render_template('admin/new_question.html', form=form, block=block)

@admin_bp.route('/block/<int:block_id>')
@login_required
def manage_block(block_id):
    if not current_user.is_admin:
        abort(403)

    block = Block.query.get_or_404(block_id)
    olympiad = Olympiad.query.get_or_404(block.olympiad_id)

    if olympiad.created_by != current_user.id:
        abort(403)

    questions = Question.query.filter_by(block_id=block_id).all()

    return render_template('admin/manage_block.html', block=block, olympiad=olympiad, questions=questions)

@admin_bp.route('/olympiad/<int:olympiad_id>/stats')
@login_required
def olympiad_stats(olympiad_id):
    if not current_user.is_admin:
        abort(403)

    olympiad = Olympiad.query.get_or_404(olympiad_id)
    if olympiad.created_by != current_user.id:
        abort(403)

    participations = Participation.query.filter_by(olympiad_id=olympiad_id).all()
    blocks = Block.query.filter_by(olympiad_id=olympiad_id).order_by(Block.order).all()

    # Готовим данные для статистики
    stats = {
        'total_participants': len(participations),
        'completed': sum(1 for p in participations if p.is_completed),
        'disqualified': sum(1 for p in participations if p.is_disqualified),
        'in_progress': sum(1 for p in participations if not p.is_completed and not p.is_disqualified),
        'avg_score': sum(p.total_score for p in participations if p.is_completed) / len([p for p in participations if p.is_completed]) if len([p for p in participations if p.is_completed]) > 0 else 0,
        'blocks_stats': []
    }

    # Статистика по блокам
    for block in blocks:
        block_results = BlockResult.query.filter_by(block_id=block.id).all()
        block_stat = {
            'block_id': block.id,
            'block_title': block.title,
            'attempts': len(block_results),
            'avg_score': sum(br.score for br in block_results) / len(block_results) if len(block_results) > 0 else 0,
            'passed_threshold': sum(1 for br in block_results if br.passed_threshold),
            'failed_threshold': sum(1 for br in block_results if not br.passed_threshold)
        }
        stats['blocks_stats'].append(block_stat)

    return render_template('admin/olympiad_stats.html', olympiad=olympiad, stats=stats, participations=participations)

@admin_bp.route('/olympiad/<int:olympiad_id>/export')
@login_required
def export_results(olympiad_id):
    if not current_user.is_admin:
        abort(403)

    olympiad = Olympiad.query.get_or_404(olympiad_id)
    if olympiad.created_by != current_user.id:
        abort(403)

    # Создаем CSV файл в памяти
    output = io.StringIO()
    writer = csv.writer(output)

    # Заголовок таблицы
    header = ['ID', 'Email', 'ФИО', 'Группа', 'Итоговый балл', 'Дисквалификация', 'Время начала', 'Время завершения', 'Затраченное время (мин)']

    # Добавляем заголовки для каждого блока
    blocks = Block.query.filter_by(olympiad_id=olympiad_id).order_by(Block.order).all()
    for block in blocks:
        header.append(f'Блок {block.order}: {block.title} (баллы)')
        header.append(f'Блок {block.order}: процент')
        header.append(f'Блок {block.order}: прохождение порога')

    writer.writerow(header)

    # Данные участников
    participations = Participation.query.filter_by(olympiad_id=olympiad_id).all()
    for p in participations:
        user = User.query.get(p.user_id)

        row = [
            p.id,
            user.email,
            user.full_name,
            user.group,
            p.total_score,
            'Да' if p.is_disqualified else 'Нет',
            p.start_time.strftime('%Y-%m-%d %H:%M:%S'),
            p.end_time.strftime('%Y-%m-%d %H:%M:%S') if p.end_time else 'Не завершено',
            round((p.completion_time or 0) / 60, 2) if p.completion_time else 'Не завершено'
        ]

        # Добавляем результаты по блокам
        for block in blocks:
            block_result = BlockResult.query.filter_by(participation_id=p.id, block_id=block.id).first()
            if block_result:
                row.append(block_result.score)
                row.append(f'{block_result.percentage:.2f}%')
                row.append('Да' if block_result.passed_threshold else 'Нет')
            else:
                row.extend(['Н/Д', 'Н/Д', 'Н/Д'])

        writer.writerow(row)

    # Готовим ответ с CSV файлом
    output.seek(0)
    return output.getvalue(), 200, {
        'Content-Type': 'text/csv',
        'Content-Disposition': f'attachment; filename=olympiad_{olympiad_id}_results.csv'
    }

# --------------------------------
# Участие в олимпиадах
# --------------------------------

@participant_bp.route('/dashboard')
@login_required
def dashboard():
    # Доступные олимпиады (текущие и будущие)
    current_time = datetime.utcnow()
    available_olympiads = Olympiad.query.filter(
        Olympiad.end_time > current_time,
        Olympiad.is_active == True
    ).all()

    # Олимпиады, в которых пользователь уже участвует
    participations = Participation.query.filter_by(user_id=current_user.id).all()
    participation_olympiad_ids = [p.olympiad_id for p in participations]

    # История завершенных олимпиад
    completed_participations = [p for p in participations if p.is_completed]

    # Передаем текущее время в шаблон
    now = datetime.utcnow()

    return render_template(
        'participant/dashboard.html',
        available_olympiads=available_olympiads,
        participations=participations,
        participation_olympiad_ids=participation_olympiad_ids,
        completed_participations=completed_participations,
        now=now
    )

@participant_bp.route('/olympiad/<int:olympiad_id>/start')
@login_required
def start_olympiad(olympiad_id):
    olympiad = Olympiad.query.get_or_404(olympiad_id)

    # Проверка доступности олимпиады
    current_time = datetime.utcnow()
    if current_time < olympiad.start_time:
        flash('Олимпиада еще не началась!', 'warning')
        return redirect(url_for('participant.dashboard'))

    if current_time > olympiad.end_time:
        flash('Олимпиада уже завершена!', 'warning')
        return redirect(url_for('participant.dashboard'))

    # Проверка, участвует ли пользователь уже в олимпиаде
    participation = Participation.query.filter_by(
        user_id=current_user.id,
        olympiad_id=olympiad_id
    ).first()

    if participation:
        # Если пользователь уже завершил олимпиаду, редирект на результаты
        if participation.is_completed:
            return redirect(url_for('participant.olympiad_results', participation_id=participation.id))

        # Если дисквалифицирован
        if participation.is_disqualified:
            flash('Вы были дисквалифицированы!', 'danger')
            return redirect(url_for('participant.dashboard'))

        # Если уже участвует, но не завершил, продолжаем с текущего блока
        current_block_id = participation.current_block
        if current_block_id:
            return redirect(url_for('participant.solve_block', participation_id=participation.id, block_id=current_block_id))
        else:
            # Если текущий блок не определен, начинаем с первого блока
            first_block = Block.query.filter_by(olympiad_id=olympiad_id).order_by(Block.order).first()
            if first_block:
                participation.current_block = first_block.id
                db.session.commit()
                return redirect(url_for('participant.solve_block', participation_id=participation.id, block_id=first_block.id))
    else:
        # Создаем новое участие
        participation = Participation(
            user_id=current_user.id,
            olympiad_id=olympiad_id,
            start_time=current_time
        )
        db.session.add(participation)
        db.session.commit()

        # Перенаправляем на страницу с приветственным PDF
        return redirect(url_for('participant.olympiad_welcome', participation_id=participation.id))

@participant_bp.route('/participation/<int:participation_id>/welcome')
@login_required
def olympiad_welcome(participation_id):
    participation = Participation.query.get_or_404(participation_id)

    # Проверка прав доступа
    if participation.user_id != current_user.id:
        abort(403)

    olympiad = Olympiad.query.get_or_404(participation.olympiad_id)

    return render_template('participant/welcome.html', participation=participation, olympiad=olympiad)

@participant_bp.route('/participation/<int:participation_id>/block/<int:block_id>')
@login_required
def solve_block(participation_id, block_id):
    participation = Participation.query.get_or_404(participation_id)

    # Проверка прав доступа
    if participation.user_id != current_user.id:
        abort(403)

    if participation.is_disqualified:
        flash('Вы были дисквалифицированы!', 'danger')
        return redirect(url_for('participant.dashboard'))

    if participation.is_completed:
        return redirect(url_for('participant.olympiad_results', participation_id=participation_id))

    block = Block.query.get_or_404(block_id)
    questions = Question.query.filter_by(block_id=block_id).all()

    # Проверяем, есть ли доступ к блоку
    if participation.current_block != block_id:
        # Если пользователь пытается перейти к блоку, который не является текущим
        flash('У вас нет доступа к этому блоку!', 'danger')
        return redirect(url_for('participant.dashboard'))

    # Получаем все вопросы и их опции
    questions_data = []
    for question in questions:
        options = Option.query.filter_by(question_id=question.id).all()
        questions_data.append({
            'question': question,
            'options': options
        })

    # Устанавливаем сессионную переменную для контроля полноэкранного режима
    session['fullscreen_required'] = True

    return render_template(
        'participant/solve_block.html',
        participation=participation,
        block=block,
        questions_data=questions_data
    )

@participant_bp.route('/participation/<int:participation_id>/block/<int:block_id>/submit', methods=['POST'])
@login_required
def submit_block(participation_id, block_id):
    participation = Participation.query.get_or_404(participation_id)

    # Проверка прав доступа
    if participation.user_id != current_user.id:
        abort(403)

    if participation.is_disqualified:
        flash('Вы были дисквалифицированы!', 'danger')
        return redirect(url_for('participant.dashboard'))

    if participation.is_completed:
        return redirect(url_for('participant.olympiad_results', participation_id=participation_id))

    # Проверяем, является ли блок текущим для участника
    if participation.current_block != block_id:
        flash('У вас нет доступа к этому блоку!', 'danger')
        return redirect(url_for('participant.dashboard'))

    block = Block.query.get_or_404(block_id)
    questions = Question.query.filter_by(block_id=block_id).all()

    # Обрабатываем ответы
    total_points = 0
    possible_points = block.total_points

    for question in questions:
        if question.question_type == 'test':
            # Обработка тестовых вопросов
            selected_option_id = request.form.get(f'question_{question.id}')
            if selected_option_id:
                selected_option = Option.query.get(selected_option_id)
                is_correct = selected_option.is_correct

                # Рассчет баллов
                points_earned = question.points if is_correct else 0
                total_points += points_earned

                # Сохраняем ответ
                answer = Answer(
                    participation_id=participation.id,
                    question_id=question.id,
                    selected_option_id=selected_option_id,
                    is_correct=is_correct,
                    points_earned=points_earned
                )
                db.session.add(answer)

        elif question.question_type == 'matching':
            # Обработка заданий на соответствие
            matching_data = {}
            correct_pairs = 0
            total_pairs = 0

            # Получаем все пары для вопроса
            options = Option.query.filter_by(question_id=question.id).all()
            match_ids = set(opt.match_id for opt in options)
            total_pairs = len(match_ids)

            # Обрабатываем ответы на соответствие
            for match_id in match_ids:
                user_match = request.form.get(f'question_{question.id}_match_{match_id}')
                if user_match:
                    # Преобразуем в формат "id_левого:id_правого"
                    matching_data[str(match_id)] = user_match

                    # Проверяем правильность соответствия
                    left_id, right_id = user_match.split(':')
                    left_option = Option.query.get(left_id)
                    right_option = Option.query.get(right_id)

                    if left_option.match_id == right_option.match_id:
                        correct_pairs += 1

            # Рассчет баллов с учетом частично правильных ответов
            accuracy = correct_pairs / total_pairs if total_pairs > 0 else 0
            points_earned = int(question.points * accuracy)
            total_points += points_earned

            # Сохраняем ответ
            answer = Answer(
                participation_id=participation.id,
                question_id=question.id,
                matching_data=json.dumps(matching_data),
                is_correct=accuracy == 1.0,
                points_earned=points_earned
            )
            db.session.add(answer)

    # Рассчитываем процент правильных ответов
    percentage = (total_points / possible_points * 100) if possible_points > 0 else 0
    passed_threshold = percentage >= block.threshold_percentage

    # Сохраняем результат блока
    block_result = BlockResult(
        participation_id=participation.id,
        block_id=block.id,
        score=total_points,
        percentage=percentage,
        passed_threshold=passed_threshold
    )
    db.session.add(block_result)

    # Обновляем общий счет участника
    participation.total_score += total_points

    # Определяем следующий блок, если пройден порог
    if passed_threshold:
        # Ищем следующий блок по порядку
        next_block = Block.query.filter(
            Block.olympiad_id == block.olympiad_id,
            Block.order > block.order
        ).order_by(Block.order).first()

        if next_block:
            participation.current_block = next_block.id
        else:
            # Если это был последний блок, завершаем олимпиаду
            participation.is_completed = True
            participation.end_time = datetime.utcnow()
            participation.completion_time = (participation.end_time - participation.start_time).total_seconds()
    else:
        # Если не пройден порог, олимпиада завершается
        participation.is_completed = True
        participation.end_time = datetime.utcnow()
        participation.completion_time = (participation.end_time - participation.start_time).total_seconds()

    db.session.commit()

    # Очищаем сессионную переменную полноэкранного режима
    session.pop('fullscreen_required', None)

    # Перенаправляем на страницу с рейтингом
    return redirect(url_for('participant.block_leaderboard', participation_id=participation_id, block_id=block_id))

@participant_bp.route('/participation/<int:participation_id>/block/<int:block_id>/leaderboard')
@login_required
def block_leaderboard(participation_id, block_id):
    participation = Participation.query.get_or_404(participation_id)

    # Проверка прав доступа
    if participation.user_id != current_user.id:
        abort(403)

    block = Block.query.get_or_404(block_id)
    block_result = BlockResult.query.filter_by(participation_id=participation_id, block_id=block_id).first()

    if not block_result:
        flash('Вы еще не завершили этот блок!', 'warning')
        return redirect(url_for('participant.dashboard'))

    # Получаем все результаты этого блока для рейтинга
    all_block_results = BlockResult.query.filter_by(block_id=block_id).all()

    # Сортируем по баллам (в порядке убывания) и затем по времени выполнения
    leaderboard_data = []
    for br in all_block_results:
        user = User.query.get(Participation.query.get(br.participation_id).user_id)
        leaderboard_data.append({
            'user_name': user.full_name or user.email,
            'score': br.score,
            'percentage': br.percentage,
            'completed_at': br.completed_at,
            'is_current_user': user.id == current_user.id
        })

    # Сортировка по баллам (убывание) и времени (возрастание)
    leaderboard_data.sort(key=lambda x: (-x['score'], x['completed_at']))

    # Определяем, есть ли следующий блок
    next_block = None
    if block_result.passed_threshold:
        next_block = Block.query.filter(
            Block.olympiad_id == block.olympiad_id,
            Block.order > block.order
        ).order_by(Block.order).first()

    return render_template(
        'participant/block_leaderboard.html',
        participation=participation,
        block=block,
        block_result=block_result,
        leaderboard_data=leaderboard_data,
        next_block=next_block
    )

@participant_bp.route('/participation/<int:participation_id>/results')
@login_required
def olympiad_results(participation_id):
    participation = Participation.query.get_or_404(participation_id)

    # Проверка прав доступа
    if participation.user_id != current_user.id:
        abort(403)

    olympiad = Olympiad.query.get_or_404(participation.olympiad_id)

    # Получаем все результаты блоков
    block_results = BlockResult.query.filter_by(participation_id=participation_id).all()
    blocks = {block.id: block for block in Block.query.filter_by(olympiad_id=olympiad.id).all()}

    # Если олимпиада завершена, получаем итоговый рейтинг
    leaderboard_data = []
    if olympiad.end_time < datetime.utcnow() or participation.is_completed:
        all_participations = Participation.query.filter_by(olympiad_id=olympiad.id, is_completed=True).all()

        for p in all_participations:
            user = User.query.get(p.user_id)
            leaderboard_data.append({
                'user_name': user.full_name or user.email,
                'total_score': p.total_score,
                'completion_time': p.completion_time,
                'is_current_user': user.id == current_user.id
            })

        # Сортировка по очкам (убывание) и времени (возрастание)
        leaderboard_data.sort(key=lambda x: (-x['total_score'], x['completion_time']))

    return render_template(
        'participant/olympiad_results.html',
        participation=participation,
        olympiad=olympiad,
        block_results=block_results,
        blocks=blocks,
        leaderboard_data=leaderboard_data
    )

# API для контроля полноэкранного режима
@participant_bp.route('/api/fullscreen_exit', methods=['POST'])
@login_required
def fullscreen_exit():
    participation_id = request.json.get('participation_id')

    if participation_id:
        participation = Participation.query.get_or_404(participation_id)

        # Проверка прав доступа
        if participation.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403

        # Дисквалификация участника
        participation.is_disqualified = True
        participation.disqualification_reason = 'Выход из полноэкранного режима'
        participation.end_time = datetime.utcnow()
        db.session.commit()

        # Очищаем сессионную переменную полноэкранного режима
        session.pop('fullscreen_required', None)

        return jsonify({'status': 'disqualified'})

    return jsonify({'error': 'Invalid request'}), 400