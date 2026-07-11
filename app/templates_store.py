"""
Кастомные промпт-шаблоны по типу страницы (вкладка "Промпт-шаблоны").

Идея: у разных типов страниц (лендинг, о нас, страница доверия, FAQ, услуга,
блог) нужна разная структура промпта — не только разные данные, но и разный
набор блоков/логику. Обычный движок (prompt_config/*.yaml + master_prompt.md.j2)
покрывает общий случай хорошо, но для конкретного типа страницы можно сохранить
полностью кастомный Jinja2-шаблон текстом прямо в БД (редактируется через UI,
без git) — и он будет использован вместо дефолтного, если для (сайт, тип
страницы) он сохранён.

Приоритет при генерации промпта (см. server.py /prompt/<id>):
1. Если у строки указан page_type И для (site_id, page_type) есть кастомный
   шаблон — рендерится он (prompts.render_custom_template).
2. Иначе — обычный дефолтный движок (prompts.generate_prompt).
"""

PAGE_TYPES = [
    ("landing", "Лендинг"),
    ("about", "О нас / О компании"),
    ("trust", "Страница доверия (гарантии, сертификаты, отзывы)"),
    ("faq", "FAQ-страница"),
    ("service", "Услуга / товар (коммерческая страница)"),
    ("blog", "Статья блога"),
]
PAGE_TYPE_LABELS = dict(PAGE_TYPES)


def list_templates(conn, site_id=None):
    q = "SELECT * FROM prompt_templates"
    params = []
    if site_id:
        q += " WHERE site_id=?"
        params.append(site_id)
    q += " ORDER BY site_id, page_type"
    return conn.execute(q, params).fetchall()


def get_template(conn, site_id, page_type):
    return conn.execute(
        "SELECT * FROM prompt_templates WHERE site_id=? AND page_type=?",
        (site_id, page_type)
    ).fetchone()


def save_template(conn, site_id, page_type, template_text):
    from datetime import datetime
    now = datetime.utcnow().isoformat(timespec="seconds")
    existing = get_template(conn, site_id, page_type)
    if existing:
        conn.execute(
            "UPDATE prompt_templates SET template_text=?, updated_at=? WHERE id=?",
            (template_text, now, existing["id"])
        )
    else:
        conn.execute(
            "INSERT INTO prompt_templates (site_id, page_type, template_text, updated_at) VALUES (?,?,?,?)",
            (site_id, page_type, template_text, now)
        )
    conn.commit()


def delete_template(conn, template_id):
    conn.execute("DELETE FROM prompt_templates WHERE id=?", (template_id,))
    conn.commit()
