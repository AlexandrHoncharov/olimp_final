#!/usr/bin/env python3
"""
Скрипт для тестирования генерации сертификатов
Создает тестовые сертификаты для проверки дизайна и расположения элементов
"""

import os
import sys
from PIL import Image, ImageDraw, ImageFont
import textwrap
from datetime import datetime


# Импортируем функции из основного файла (если запускается отдельно)
# В реальном приложении эти функции уже будут в app.py

def create_certificate_background(width=3508, height=2480):
    """Создает фон сертификата (A4 в альбомной ориентации, 300 DPI)"""
    # Создаем изображение с белым фоном
    img = Image.new('RGB', (width, height), 'white')
    draw = ImageDraw.Draw(img)

    # Рамка сертификата
    border_width = 40
    border_color = '#820000'

    # Внешняя рамка
    draw.rectangle([0, 0, width - 1, height - 1], outline=border_color, width=border_width)

    # Внутренняя декоративная рамка
    inner_margin = 80
    draw.rectangle([inner_margin, inner_margin, width - inner_margin, height - inner_margin],
                   outline='#B8860B', width=8)

    # Декоративные углы
    corner_size = 150
    corner_color = '#FFD700'

    # Верхние углы
    draw.polygon([(inner_margin, inner_margin),
                  (inner_margin + corner_size, inner_margin),
                  (inner_margin, inner_margin + corner_size)],
                 fill=corner_color)
    draw.polygon([(width - inner_margin, inner_margin),
                  (width - inner_margin - corner_size, inner_margin),
                  (width - inner_margin, inner_margin + corner_size)],
                 fill=corner_color)

    # Нижние углы
    draw.polygon([(inner_margin, height - inner_margin),
                  (inner_margin + corner_size, height - inner_margin),
                  (inner_margin, height - inner_margin - corner_size)],
                 fill=corner_color)
    draw.polygon([(width - inner_margin, height - inner_margin),
                  (width - inner_margin - corner_size, height - inner_margin),
                  (width - inner_margin, height - inner_margin - corner_size)],
                 fill=corner_color)

    return img


def get_font(size, bold=False):
    """Получает шрифт нужного размера"""
    try:
        if bold:
            return ImageFont.truetype("arial.ttf", size)
        else:
            return ImageFont.truetype("arial.ttf", size)
    except:
        try:
            if bold:
                return ImageFont.truetype("/System/Library/Fonts/Arial Bold.ttf", size)
            else:
                return ImageFont.truetype("/System/Library/Fonts/Arial.ttf", size)
        except:
            return ImageFont.load_default()


def add_signatures_to_certificate(img, signatures_folder='static/signatures'):
    """Добавляет подписи членов жюри на сертификат (обновленная версия)"""
    draw = ImageDraw.Draw(img)
    width, height = img.size

    # Позиции для подписей (внизу сертификата)
    signature_y = height - 400
    signature_width = 350  # Увеличено с 300 до 350
    signature_height = 150

    # Данные членов жюри
    jury_members = [
        {"name": "Мохнатко Ирина Николаевна", "position": "к.т.н., доцент, зав. кафедрой «Гражданская безопасность»",
         "file": "1.jpg"},
        {"name": "Малюта Сергей Иванович", "position": "к.т.н., доцент кафедры «Гражданская безопасность»",
         "file": "2.jpg"},
        {"name": "Мазилин Сергей Дмитриевич", "position": "к.т.н., доцент кафедры «Гражданская безопасность»",
         "file": "3.jpg"}
    ]

    # Расчет позиций для размещения подписей (увеличенное расстояние)
    spacing_between_signatures = 200  # Увеличено с 100 до 200 пикселей
    total_width = len(jury_members) * signature_width + (len(jury_members) - 1) * spacing_between_signatures
    start_x = (width - total_width) // 2

    font_name = get_font(32, bold=True)
    font_position = get_font(24)

    for i, member in enumerate(jury_members):
        x = start_x + i * (signature_width + spacing_between_signatures)

        # Пытаемся загрузить изображение подписи
        try:
            signature_path = os.path.join(signatures_folder, member["file"])
            if os.path.exists(signature_path):
                signature_img = Image.open(signature_path)
                # Изменяем размер подписи (увеличенная область)
                signature_img = signature_img.resize((signature_width - 50, signature_height - 80),
                                                     Image.Resampling.LANCZOS)
                # Вставляем подпись
                img.paste(signature_img, (x + 25, signature_y - 100),
                          signature_img if signature_img.mode == 'RGBA' else None)
        except Exception as e:
            print(f"Не удалось загрузить подпись {member['file']}: {e}")
            # Рисуем прямоугольник для подписи (обновленные координаты)
            draw.rectangle([x + 25, signature_y - 100, x + signature_width - 25, signature_y - 20],
                           outline='#CCCCCC', width=2)
            draw.text((x + signature_width // 2, signature_y - 60), "(подпись)",
                      font=font_position, fill='#666666', anchor="mm")

        # Добавляем линию для подписи
        draw.line([x, signature_y, x + signature_width, signature_y], fill='#000000', width=3)

        # Добавляем имя и должность (увеличенные лимиты строк)
        name_lines = textwrap.wrap(member["name"], width=30)  # Увеличено с 25 до 30
        position_lines = textwrap.wrap(member["position"], width=35)  # Увеличено с 30 до 35

        current_y = signature_y + 20
        for line in name_lines:
            bbox = draw.textbbox((0, 0), line, font=font_name)
            text_width = bbox[2] - bbox[0]
            draw.text((x + signature_width // 2 - text_width // 2, current_y), line,
                      font=font_name, fill='#000000')
            current_y += 45  # Увеличен интервал с 40 до 45

        current_y += 15  # Увеличен отступ с 10 до 15
        for line in position_lines:
            bbox = draw.textbbox((0, 0), line, font=font_position)
            text_width = bbox[2] - bbox[0]
            draw.text((x + signature_width // 2 - text_width // 2, current_y), line,
                      font=font_position, fill='#000000')
            current_y += 35  # Увеличен интервал с 30 до 35

    return img


def generate_test_participation_certificate():
    """Генерирует тестовый сертификат участия"""
    img = create_certificate_background()
    draw = ImageDraw.Draw(img)
    width, height = img.size

    # Заголовок университета
    university_lines = [
        "ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ",
        "ВЫСШЕГО ОБРАЗОВАНИЯ «МЕЛИТОПОЛЬСКИЙ ГОСУДАРСТВЕННЫЙ УНИВЕРСИТЕТ»",
        "Технический факультет",
        "кафедра «Гражданская безопасность»"
    ]

    font_header = get_font(48, bold=True)
    font_subheader = get_font(40, bold=True)
    font_small_header = get_font(36, bold=True)

    y = 200
    for i, line in enumerate(university_lines):
        if i < 2:
            current_font = font_header
        elif i == 2:
            current_font = font_subheader
        else:
            current_font = font_small_header

        bbox = draw.textbbox((0, 0), line, font=current_font)
        text_width = bbox[2] - bbox[0]
        draw.text((width // 2 - text_width // 2, y), line, font=current_font, fill='#000000')
        y += 70

    # Заголовок сертификата
    y += 100
    certificate_title = "СЕРТИФИКАТ УЧАСТНИКА"
    font_title = get_font(80, bold=True)
    bbox = draw.textbbox((0, 0), certificate_title, font=font_title)
    text_width = bbox[2] - bbox[0]
    draw.text((width // 2 - text_width // 2, y), certificate_title, font=font_title, fill='#820000')

    # Основной текст
    y += 200
    font_main = get_font(48)
    font_name = get_font(56, bold=True)

    # "Настоящим подтверждается, что"
    confirm_text = "Настоящим подтверждается, что"
    bbox = draw.textbbox((0, 0), confirm_text, font=font_main)
    text_width = bbox[2] - bbox[0]
    draw.text((width // 2 - text_width // 2, y), confirm_text, font=font_main, fill='#000000')

    # Имя участника
    y += 120
    user_name = "Иванов Иван Иванович"
    bbox = draw.textbbox((0, 0), user_name, font=font_name)
    text_width = bbox[2] - bbox[0]
    draw.text((width // 2 - text_width // 2, y), user_name, font=font_name, fill='#820000')

    # Подчеркивание имени
    line_start = width // 2 - text_width // 2 - 50
    line_end = width // 2 + text_width // 2 + 50
    draw.line([line_start, y + 70, line_end, y + 70], fill='#820000', width=4)

    # Специальность
    y += 120
    speciality_text = "направление подготовки: Техносферная безопасность"
    bbox = draw.textbbox((0, 0), speciality_text, font=font_main)
    text_width = bbox[2] - bbox[0]
    draw.text((width // 2 - text_width // 2, y), speciality_text, font=font_main, fill='#000000')

    # Текст об участии в олимпиаде
    y += 100
    participation_lines = [
        "принял(а) участие в олимпиаде",
        '"Тестовая олимпиада по гражданской безопасности"'
    ]

    for line in participation_lines:
        if line.startswith('"'):
            current_font = font_name
            color = '#820000'
        else:
            current_font = font_main
            color = '#000000'

        bbox = draw.textbbox((0, 0), line, font=current_font)
        text_width = bbox[2] - bbox[0]
        draw.text((width // 2 - text_width // 2, y), line, font=current_font, fill=color)
        y += 80

    # Дата
    y += 100
    date_text = f"«___» _____________ {datetime.now().year} г."
    bbox = draw.textbbox((0, 0), date_text, font=font_main)
    text_width = bbox[2] - bbox[0]
    draw.text((200, y), date_text, font=font_main, fill='#000000')

    # Добавляем подписи с улучшенным расположением
    img = add_signatures_to_certificate(img)

    return img


def generate_test_winner_certificate():
    """Генерирует тестовый диплом победителя"""
    img = create_certificate_background()
    draw = ImageDraw.Draw(img)
    width, height = img.size

    # Заголовок университета
    university_lines = [
        "ФЕДЕРАЛЬНОЕ ГОСУДАРСТВЕННОЕ БЮДЖЕТНОЕ ОБРАЗОВАТЕЛЬНОЕ УЧРЕЖДЕНИЕ",
        "ВЫСШЕГО ОБРАЗОВАНИЯ «МЕЛИТОПОЛЬСКИЙ ГОСУДАРСТВЕННЫЙ УНИВЕРСИТЕТ»",
        "Технический факультет",
        "кафедра «Гражданская безопасность»"
    ]

    font_header = get_font(48, bold=True)
    font_subheader = get_font(40, bold=True)
    font_small_header = get_font(36, bold=True)

    y = 180
    for i, line in enumerate(university_lines):
        if i < 2:
            current_font = font_header
        elif i == 2:
            current_font = font_subheader
        else:
            current_font = font_small_header

        bbox = draw.textbbox((0, 0), line, font=current_font)
        text_width = bbox[2] - bbox[0]
        draw.text((width // 2 - text_width // 2, y), line, font=current_font, fill='#000000')
        y += 60

    # Заголовок сертификата
    y += 80
    certificate_title = "ДИПЛОМ ПОБЕДИТЕЛЯ"
    title_color = '#FFD700'  # Золотой

    font_title = get_font(80, bold=True)
    bbox = draw.textbbox((0, 0), certificate_title, font=font_title)
    text_width = bbox[2] - bbox[0]
    draw.text((width // 2 - text_width // 2, y), certificate_title, font=font_title, fill=title_color)

    # Место
    y += 120
    place_text = "I МЕСТО"

    font_place = get_font(60, bold=True)
    bbox = draw.textbbox((0, 0), place_text, font=font_place)
    text_width = bbox[2] - bbox[0]
    draw.text((width // 2 - text_width // 2, y), place_text, font=font_place, fill=title_color)

    # Основной текст
    y += 150
    font_main = get_font(48)
    font_name = get_font(56, bold=True)

    # "Награждается"
    award_text = "Награждается"
    bbox = draw.textbbox((0, 0), award_text, font=font_main)
    text_width = bbox[2] - bbox[0]
    draw.text((width // 2 - text_width // 2, y), award_text, font=font_main, fill='#000000')

    # Имя участника
    y += 100
    user_name = "Петров Петр Петрович"
    bbox = draw.textbbox((0, 0), user_name, font=font_name)
    text_width = bbox[2] - bbox[0]
    draw.text((width // 2 - text_width // 2, y), user_name, font=font_name, fill='#820000')

    # Подчеркивание имени
    line_start = width // 2 - text_width // 2 - 50
    line_end = width // 2 + text_width // 2 + 50
    draw.line([line_start, y + 70, line_end, y + 70], fill='#820000', width=4)

    # Специальность
    y += 120
    speciality_text = "направление подготовки: Техносферная безопасность"
    bbox = draw.textbbox((0, 0), speciality_text, font=font_main)
    text_width = bbox[2] - bbox[0]
    draw.text((width // 2 - text_width // 2, y), speciality_text, font=font_main, fill='#000000')

    # Текст о победе в олимпиаде
    y += 100
    victory_lines = [
        "занявшему I МЕСТО в олимпиаде",
        '"Тестовая олимпиада по гражданской безопасности"',
        "Результат: 120.0 баллов"
    ]

    for line in victory_lines:
        if line.startswith('"') or line.startswith('Результат:'):
            current_font = font_name if line.startswith('"') else font_main
            color = '#820000'
        else:
            current_font = font_main
            color = '#000000'

        bbox = draw.textbbox((0, 0), line, font=current_font)
        text_width = bbox[2] - bbox[0]
        draw.text((width // 2 - text_width // 2, y), line, font=current_font, fill=color)
        y += 80

    # Дата
    y += 100
    date_text = f"«___» _____________ {datetime.now().year} г."
    bbox = draw.textbbox((0, 0), date_text, font=font_main)
    text_width = bbox[2] - bbox[0]
    draw.text((200, y), date_text, font=font_main, fill='#000000')

    # Добавляем подписи с улучшенным расположением
    img = add_signatures_to_certificate(img)

    return img


def main():
    """Основная функция для создания тестовых сертификатов"""
    print("🧪 Генерация тестовых сертификатов...")

    # Создаем папку для тестовых сертификатов
    test_folder = 'test_certificates'
    if not os.path.exists(test_folder):
        os.makedirs(test_folder)
        print(f"📁 Создана папка: {test_folder}")

    try:
        # Генерируем сертификат участника
        print("\n📜 Создание сертификата участника...")
        participation_cert = generate_test_participation_certificate()
        participation_path = os.path.join(test_folder, 'test_participation_certificate.png')
        participation_cert.save(participation_path, 'PNG', quality=95, dpi=(300, 300))
        print(f"✅ Сохранен: {participation_path}")

        # Генерируем диплом победителя
        print("\n🏆 Создание диплома победителя...")
        winner_cert = generate_test_winner_certificate()
        winner_path = os.path.join(test_folder, 'test_winner_certificate.png')
        winner_cert.save(winner_path, 'PNG', quality=95, dpi=(300, 300))
        print(f"✅ Сохранен: {winner_path}")

        print(f"\n🎉 Тестовые сертификаты созданы в папке '{test_folder}'")
        print("📋 Проверьте расположение подписей и общий дизайн")

    except Exception as e:
        print(f"❌ Ошибка при создании сертификатов: {e}")
        return False

    return True


if __name__ == "__main__":
    main()