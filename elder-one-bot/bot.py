import requests
import config
import json
import pathlib
import telebot
from datetime import datetime
from bs4 import BeautifulSoup


telebot.apihelper.proxy = {"https": "https://51.158.123.35:8811"}
bot = telebot.TeleBot(config.access_token)


def get_page(group, week=0):
    if page_is_actual(group, week):
        web_page = page_load(group, week)
    else:
        if week:
            week1 = str(week) + '/'
        else:
            week1 = ''
        url = '{domain}/{group}/{week}raspisanie_zanyatiy_{group}.htm'.format(
            domain=config.domain,
            week=week1,
            group=group)
        response = requests.get(url)
        web_page = response.text
        if web_page.find("Расписание не найдено") >= 0:
            return
        page_save(group, week, web_page)
    return web_page


def page_save(group, week, page):
    """ Сохранить страницу в файл """
    with open(pathlib.Path("data.json")) as data_file:
        data = json.load(data_file)
    week = str(week)
    data[week].update({
            group: {
                "timestamp": datetime.now().timestamp(),
                "page": page
                }
            })
    with open(pathlib.Path("data.json"), "w") as data_file:
        json.dump(data, data_file)


def page_load(group, week):
    """ Загрузить страницу из файла"""
    with open(pathlib.Path("data.json")) as data_file:
        data = json.load(data_file)
    week = str(week)
    return data[week][group]["page"]


def page_is_actual(group, week):
    """ Проверить страницу из файла на актуальность"""
    with open(pathlib.Path("data.json")) as data_file:
        data = json.load(data_file)
    week = str(week)
    if data[week].get(group):
        t1 = datetime.fromtimestamp(data[week][group]["timestamp"])
        t2 = datetime.now()
        delta = t2 - t1
        if delta.seconds >= 3600:
            return False
        else:
            return True
    else:
        return False


def get_curr_week_day():
    """
    Возвращает кортеж из показалетя чётности недели и
    номера текущего дня недели
    """
    page = get_page("K3140")
    soup = BeautifulSoup(page, "html5lib")
    s = soup.find("h2", attrs={"class": "schedule-week"}).strong.text
    week = 2 if s == "Нечетная" else 1
    day = datetime.today().weekday()+1
    return (week, day)


def parse_schedule_for_a_day(web_page, day):
    soup = BeautifulSoup(web_page, "html5lib")
    day = str(day)+"day"

    # Получаем таблицу с расписанием на понедельник
    schedule_table = soup.find("table", attrs={"id": day})

    # Время проведения занятий
    times_list = schedule_table.find_all("td", attrs={"class": "time"})
    times_list = [time.span.text for time in times_list]

    # Место проведения занятий
    locations_list = schedule_table.find_all("td", attrs={"class": "room"})
    locations_list = [room.span.text for room in locations_list]

    # Название дисциплин и имена преподавателей
    lessons_list = schedule_table.find_all("td", attrs={"class": "lesson"})
    lessons_list = [lesson.text.split("\n") for lesson in lessons_list]
    lessons_list = [''.join(el).split("\t") for el in lessons_list]
    lessons_list = ['\n'.join(['\t'+el for el in lesson if el]) for lesson in lessons_list]

    # Номер аудитории
    rooms_list = schedule_table.find_all("td", attrs={"class": "room"})
    for i in range(len(rooms_list)):
        rooms_list[i] = rooms_list[i].dd.text if rooms_list[i].dd.text else ""

    return times_list, locations_list, lessons_list, rooms_list


@bot.message_handler(commands=['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'])
def get_schedule(message):
    """ Получить расписание на указанный день """
    if len(message.text.split()) != 2:
        resp = f"Используйте <b>{message.text.split()[0]} [group]</b>"
        bot.send_message(message.chat.id, resp, parse_mode='HTML')
        return
        
    week_d = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    day, group = message.text.split()
    day = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].index(day[1:])+1
    web_page = get_page(group)
    if not web_page:
        resp = "<b>Указанной группы не существует</b>"
        bot.send_message(message.chat.id, resp, parse_mode='HTML')
        return
    try:
        times_lst, locations_lst, lessons_lst, rooms_list = \
            parse_schedule_for_a_day(web_page, day)
    except Exception:
        bot.send_message(message.chat.id, '<b>В указанный день занятий нет</b>', parse_mode='HTML')
        return
    resp = f'<b>{week_d[day-1]}</b>\n'
    for time, location, room, lession in zip(times_lst, locations_lst, rooms_list, lessons_lst):
        if room != "":
            resp += '<b>{}</b>, {}, {}, {}\n'.format(time, location, room, lession)
        else:
            resp += '<b>{}</b>, {}, {}\n'.format(time, location, lession)
    bot.send_message(message.chat.id, resp, parse_mode='HTML')


@bot.message_handler(commands=['near'])
def get_near_lesson(message):
    """ Получить ближайшее занятие """
    if len(message.text.split()) != 2:
        resp = f"Используйте <b>{message.text.split()[0]} [group]</b>"
        bot.send_message(message.chat.id, resp, parse_mode='HTML')
        return
    # 1. Проверить текущий день
    # 2. Для каждого следующего дня:
    #       если занятий нет --> дальше
    #       иначе --> вернуть первое занятие
    week_d = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    _, group = message.text.split()
    week, day = get_curr_week_day()
    dt = datetime.now()
    curr_h, curr_m = dt.hour, dt.minute
    web_page = get_page(group, week)
    if not web_page:
        resp = "<b>Указанной группы не существует</b>"
        bot.send_message(message.chat.id, resp, parse_mode='HTML')
        return
    try:
        times_lst, locations_lst, lessons_lst, rooms_list = \
            parse_schedule_for_a_day(web_page, day)

        for time, location, room, lession in zip(times_lst, locations_lst, rooms_list, lessons_lst):
            h, m = map(int, time.split('-')[0].split(':'))
            if h > curr_h or (h == curr_h and m > curr_m):
                resp = f'<b>{week_d[day-1]}</b>\n'
                if room != "":
                    resp += '<b>{}</b>, {}, {}, {}'.format(time, location, room, lession)
                else:
                    resp += '<b>{}</b>, {}, {}'.format(time, location, lession)
                bot.send_message(message.chat.id, resp, parse_mode='HTML')
                return
    except Exception:
        s = ''

    while True:
        if day == 7:
            week = week*2%3
            day = 1
            web_page = get_page(group, week)
        else:
            day += 1

        try:
            times_lst, locations_lst, lessons_lst, rooms_list = \
                parse_schedule_for_a_day(web_page, day)
        except Exception:
            continue

        resp = f'<b>{week_d[day-1]}</b>\n'
        if rooms_list[0] != "":
            resp += '<b>{}</b>, {}, {}, {}\n'.format(times_lst[0], locations_lst[0], rooms_list[0], lessons_lst[0])
        else:
            resp += '<b>{}</b>, {}, {}\n'.format(times_lst[0], locations_lst[0], lessons_lst[0])
        bot.send_message(message.chat.id, resp, parse_mode='HTML')
        return



@bot.message_handler(commands=['tomorrow'])
def get_tommorow(message):
    """ Получить расписание на следующий день """
    if len(message.text.split()) != 2:
        resp = f"Используйте <b>{message.text.split()[0]} [group]</b>"
        bot.send_message(message.chat.id, resp, parse_mode='HTML')
        return
    week_d = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    _, group = message.text.split()
    week, day = get_curr_week_day()
    if day == 7:
        week = week*2%3
        day = 1
    else:
        day += 1
    web_page = get_page(group, week)
    if not web_page:
        resp = "<b>Указанной группы не существует</b>"
        bot.send_message(message.chat.id, resp, parse_mode='HTML')
        return

    try:
        times_lst, locations_lst, lessons_lst, rooms_list = \
            parse_schedule_for_a_day(web_page, day)
    except Exception:
        bot.send_message(message.chat.id, '<b>Завтра занятий нет</b>', parse_mode='HTML')
        return

    resp = f'<b>{week_d[day-1]}</b>\n'
    for time, location, room, lession in zip(times_lst, locations_lst, rooms_list, lessons_lst):
        if room != "":
            resp += '<b>{}</b>, {}, {}, {}\n'.format(time, location, room, lession)
        else:
            resp += '<b>{}</b>, {}, {}\n'.format(time, location, lession)
    bot.send_message(message.chat.id, resp, parse_mode='HTML')



@bot.message_handler(commands=['all'])
def get_all_schedule(message):
    """ Получить расписание на всю неделю для указанной группы """
    if len(message.text.split()) != 2:
        resp = f"Используйте <b>{message.text.split()[0]} [group]</b>"
        bot.send_message(message.chat.id, resp, parse_mode='HTML')
        return
    _, group = message.text.split()
    week = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    web_page = get_page(group)
    if not web_page:
        resp = "<b>Указанной группы не существует</b>"
        bot.send_message(message.chat.id, resp, parse_mode='HTML')
        return
    resp = ''
    for day in range(1, 8):
        resp += f'<b>{week[day-1]}</b>\n'
        try:
            times_lst, locations_lst, lessons_lst, rooms_list = \
                parse_schedule_for_a_day(web_page, day)
        except Exception:
            resp += '<b>Занятий нет</b>\n\n\n'
            continue

        for time, location, room, lession in zip(times_lst, locations_lst, rooms_list, lessons_lst):
            if room != "":
                resp += '<b>{}</b>, {}, {}, {}\n'.format(time, location, room, lession)
            else:
                resp += '<b>{}</b>, {}, {}\n'.format(time, location, lession)
        resp += '\n'

    k = resp.find('<b>Чт</b>')
    bot.send_message(message.chat.id, resp[:k], parse_mode='HTML')
    bot.send_message(message.chat.id, resp[k:], parse_mode='HTML')


@bot.message_handler(commands=['time'])
def get_time(message):
    dt = datetime.now()
    s = dt.strftime('%d-%m-%Y %H:%M:%S')
    bot.send_message(message.chat.id, s)

if __name__ == '__main__':
    bot.polling(none_stop=True)
