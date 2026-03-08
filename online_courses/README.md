# Online Courses Platform (Flask)

Веб-платформа онлайн-курсів, розроблена на основі **Flask**.
Система дозволяє викладачам створювати курси, модулі та уроки, а студентам — записуватись на курси та відстежувати прогрес навчання.

Проєкт створений як **курсова робота** з дисципліни об’єктно-орієнтованого програмування.

---

# Основні можливості

## Для студентів

* реєстрація та авторизація
* перегляд доступних курсів
* запис на курс
* перегляд структури курсу (модулі → уроки)
* позначення уроків як завершених
* відображення прогресу проходження курсу
* отримання сертифіката після завершення курсу

## Для викладачів

* створення нових курсів
* редагування курсу
* видалення курсу
* додавання модулів
* додавання уроків
* перегляд студентів, записаних на курс
* перегляд прогресу студентів

---

# Архітектура проєкту

Система побудована на основі **Flask + SQLAlchemy + Flask-Login**.

Основні компоненти:

* **Flask** — веб-фреймворк
* **SQLAlchemy** — ORM для роботи з базою даних
* **Flask-Login** — система авторизації користувачів
* **Jinja2 templates** — генерація HTML

---

# Структура проєкту

```
online_courses/
│
├── run.py                # головний файл Flask застосунку
│
├── templates/            # HTML шаблони (View)
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── course.html
│   ├── instructor_new_course.html
│   ├── instructor_new_module.html
│   ├── instructor_new_lesson.html
│   └── instructor_students.html
│
├── static/
│   ├── css/
│   │   ├── base.css
│   │   ├── index.css
│   │   ├── login.css
│   │   ├── course.css
│   │   ├── instructor.css
│   │   └── students.css
│   │
│   └── img/
│       └── hero.svg
│
└── courses.db            # SQLite база даних (створюється автоматично)
```

---

# Моделі бази даних

У системі використовуються такі основні моделі:

* **User** — користувач системи (student / teacher)
* **Course** — курс
* **Module** — модуль курсу
* **Lesson** — урок
* **Enrollment** — запис студента на курс
* **LessonProgress** — прогрес проходження уроків

Зв’язки між моделями:

```
User
 ├── teaches → Course
 └── enrolls → Enrollment

Course
 └── contains → Module

Module
 └── contains → Lesson

Enrollment
 └── tracks → LessonProgress
```

---

# Використані архітектурні патерни

## Active Record

Active Record — це патерн доступу до даних, у якому модель представляє таблицю бази даних і містить методи для роботи з нею.

У проєкті він реалізований через **SQLAlchemy ORM**.

Використовується у моделях:

* User
* Course
* Module
* Lesson
* Enrollment
* LessonProgress

Операції з базою даних виконуються через:

```
db.session.add()
db.session.commit()
Model.query.filter_by()
Model.query.get()
```

---

## MVC (Model-View-Controller)

У системі використовується архітектурний підхід **MVC**.

### Model

Класи SQLAlchemy:

* User
* Course
* Module
* Lesson
* Enrollment
* LessonProgress

### View

HTML-шаблони, що рендеряться через `render_template()`:

* index.html
* login.html
* course.html
* instructor_*.html
* dashboard_*.html
* certificate.html

### Controller

Функції маршрутів Flask:

* `index()`
* `login()`
* `register()`
* `dashboard()`
* `course_view()`
* `enroll()`
* `complete_lesson()`
* `instructor_new_course()`
* `instructor_edit_course()`
* `instructor_delete_course()`

Контролери обробляють HTTP-запити та взаємодіють із моделями.

---

## Authorization Guard

Для контролю доступу використовується підхід **Guard**.

Функції перевірки доступу:

```
require_teacher()
require_student()
must_own_course()
```

Вони перевіряють:

* чи авторизований користувач
* роль користувача
* право редагування курсу

Якщо перевірка не проходить — повертається помилка **403 Forbidden**.

---

## Helper / Domain Logic

Частина бізнес-логіки винесена у допоміжні функції:

```
seed_once()
get_course_tree()
ensure_progress_rows()
course_progress()
is_course_completed()
```

Їх призначення:

* ініціалізація бази даних
* формування структури курсу
* створення записів прогресу
* обчислення відсотка проходження курсу
* перевірка завершення курсу

Це дозволяє уникнути дублювання коду в контролерах.

---

## Singleton-like shared objects

У застосунку використовуються спільні об’єкти:

```
app
db
login_manager
```

Вони створюються один раз при запуску програми та використовуються у всій системі.

Формально це не класичний **Singleton**, але вони виконують аналогічну роль.

---

# Встановлення та запуск

## 1. Активувати віртуальне середовище

```
venv\Scripts\activate
```

## 2. Перейти у директорію проєкту

```
cd "B:\Games\OOP\Volchkov\OnlineCoursesPlatform+\online_courses"
```

## 3. Запустити сервер

```
python run.py
```

Після запуску сервер буде доступний за адресою:

```
http://127.0.0.1:5000
```

---

# Тестові користувачі

Після першого запуску створюються демо-акаунти:

### Викладач

```
email: teacher@mail.com
password: 1234
```

### Студент

```
email: student@mail.com
password: 1234
```

---

# Технології

* Python
* Flask
* SQLAlchemy
* Flask-Login
* SQLite
* HTML / CSS
* Jinja2

---

# Автор

Юрій Волчков
Курсова робота з дисципліни **Об’єктно-орієнтоване програмування**
