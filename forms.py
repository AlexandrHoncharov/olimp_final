# forms.py

from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, PasswordField, BooleanField, TextAreaField, IntegerField, SelectField, DateTimeField, \
    RadioField, HiddenField
from wtforms.validators import DataRequired, Email, Length, EqualTo, NumberRange, Optional
from datetime import datetime


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired()])
    remember = BooleanField('Запомнить меня')


class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Пароль', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Подтвердите пароль', validators=[DataRequired(), EqualTo('password')])
    full_name = StringField('ФИО', validators=[Optional()])
    group = StringField('Группа', validators=[Optional()])


class OlympiadForm(FlaskForm):
    title = StringField('Название олимпиады', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Описание', validators=[Optional()])
    welcome_pdf = FileField('Приветственное PDF', validators=[
        Optional(),
        FileAllowed(['pdf'], 'Только PDF файлы!')
    ])
    start_time = DateTimeField('Время начала', validators=[DataRequired()], format='%Y-%m-%d %H:%M')
    end_time = DateTimeField('Время окончания', validators=[DataRequired()], format='%Y-%m-%d %H:%M')


class BlockForm(FlaskForm):
    title = StringField('Название блока', validators=[DataRequired(), Length(max=100)])
    description = TextAreaField('Описание', validators=[Optional()])
    total_points = IntegerField('Общее количество баллов', validators=[DataRequired(), NumberRange(min=1)])
    threshold_percentage = IntegerField('Пороговый процент для перехода к следующему блоку',
                                        validators=[DataRequired(), NumberRange(min=0, max=100)])


class QuestionForm(FlaskForm):
    question_text = TextAreaField('Текст вопроса', validators=[DataRequired()])
    question_type = SelectField('Тип вопроса', choices=[
        ('test', 'Тестовый вопрос'),
        ('matching', 'Задание на соответствие')
    ], validators=[DataRequired()])
    points = IntegerField('Баллов за вопрос', validators=[DataRequired(), NumberRange(min=1)])

    # Для JS взаимодействия - будут заполняться динамически при отправке формы
    options = HiddenField('Варианты ответов')  # JSON с опциями для тестов
    matching_pairs = HiddenField('Пары для соответствия')  # JSON с парами для заданий на соответствие