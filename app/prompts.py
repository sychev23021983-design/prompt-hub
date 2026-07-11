"""
Генерация промпта для LLM: единый строгий каркас (тип страницы и цель, локальное SEO,
EEAT-тон, запрет на AI-штампы, разнообразие между страницами, Yoast-чеклист, запрет на
выдумывание фактов, расширенная Schema, явный блок FAQ, продающие блоки) + специфика
голоса/аудитории под каждый из трёх сайтов.

Контент этих правил (стиль, лимиты символов/слов, формат ответа, чек-лист) вынесен из
кода в файлы:
  - prompt_config/*.yaml     — конфиг под каждый сайт + общие значения по умолчанию
  - prompt_templates/*.md.j2 — шаблон итогового промпта (общий для всех сайтов) и
                                общий инклюд с чек-листом Yoast

Правки стиля/лимитов/чек-листа делаются в этих файлах через git, без изменения этого
модуля. Здесь остаётся только логика данных: чтение строки БД, поиск связанных страниц,
определение типа страницы, сборка контекста для шаблона.

Внутренние ссылки строятся из РЕАЛЬНЫХ строк базы (related_rows), а не придумываются моделью.
"""
import json
import os

import yaml
from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "prompt_config")
TEMPLATE_DIR = os.path.join(BASE_DIR, "prompt_templates")

_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    trim_blocks=True,
    lstrip_blocks=True,
    keep_trailing_newline=True,
)
_env.filters["quote"] = lambda s: f'"{s}"'
_env.filters["ellipsis_quote"] = lambda s: f'"{s}..."'


def _load_yaml(filename):
    with open(os.path.join(CONFIG_DIR, filename), "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


_AI_OPENERS = _load_yaml("_shared_ai_openers.yaml")
_DEFAULT_LIMITS = _load_yaml("_shared_defaults.yaml")

_SITE_CONFIG_CACHE = {}


def _get_site_config(prompt_style):
    """Загружает и кэширует конфиг сайта из prompt_config/<prompt_style>.yaml,
    подмешивая общие ai_openers и лимиты (с учётом overrides конкретного сайта)."""
    if prompt_style in _SITE_CONFIG_CACHE:
        return _SITE_CONFIG_CACHE[prompt_style]

    fname = f"{prompt_style}.yaml"
    effective_style = prompt_style if os.path.exists(os.path.join(CONFIG_DIR, fname)) else "b2b_ru"

    cfg = _load_yaml(f"{effective_style}.yaml")
    cfg["ai_openers"] = _AI_OPENERS.get(cfg.get("ai_openers_ref", "ru"), _AI_OPENERS["ru"])

    limits = dict(_DEFAULT_LIMITS)
    limits.update(cfg.get("overrides") or {})
    cfg["_limits"] = limits

    _SITE_CONFIG_CACHE[prompt_style] = cfg
    return cfg


def _extra(row):
    try:
        return json.loads(row["extra_json"] or "{}")
    except Exception:
        return {}


def _field(label, value):
    """Формирует строку 'Label: значение' с явной пометкой «нет данных», если
    поле пустое — вместо того чтобы молча пропускать поле (модель начинала
    додумывать за него) или печатать буквальное 'None' из пустого значения БД."""
    val = (value or "").strip() if isinstance(value, str) else value
    if not val:
        return f"{label}: нет данных"
    return f"{label}: {val}"


def get_related_rows(conn, row, limit=6):
    """Ищет реальные связанные строки того же сайта. Приоритет источников:
    1) структура сайта, если страница к ней привязана — другие страницы того же
       раздела, страница родительского раздела (категории), страницы соседних
       разделов; это самый точный источник, т.к. отражает реальную архитектуру сайта
    2) старая эвристика по vendor/geo/section из extra_json
    3) страницы того же типа (row_type)
    Добивает лимит по порядку, не дублируя уже найденное."""
    candidates = {}
    node_id = row["structure_node_id"]

    if node_id:
        same_node = conn.execute(
            "SELECT id, name, url FROM rows_ WHERE structure_node_id=? AND id!=? LIMIT ?",
            (node_id, row["id"], limit)
        ).fetchall()
        for r in same_node:
            candidates[r["id"]] = r

        if len(candidates) < limit:
            node = conn.execute("SELECT parent_id FROM structure_nodes WHERE id=?", (node_id,)).fetchone()
            parent_id = node["parent_id"] if node else None
            if parent_id:
                parent_page = conn.execute(
                    "SELECT id, name, url FROM rows_ WHERE structure_node_id=? AND id!=? LIMIT 1",
                    (parent_id, row["id"])
                ).fetchall()
                for r in parent_page:
                    candidates[r["id"]] = r

                if len(candidates) < limit:
                    sibling_nodes = conn.execute(
                        "SELECT id FROM structure_nodes WHERE parent_id=? AND id!=?",
                        (parent_id, node_id)
                    ).fetchall()
                    sibling_ids = [s["id"] for s in sibling_nodes]
                    if sibling_ids:
                        placeholders = ",".join("?" * len(sibling_ids))
                        more = conn.execute(
                            f"""SELECT id, name, url FROM rows_
                                WHERE structure_node_id IN ({placeholders}) AND id!=? LIMIT ?""",
                            (*sibling_ids, row["id"], limit - len(candidates))
                        ).fetchall()
                        for r in more:
                            candidates[r["id"]] = r

    if len(candidates) < limit:
        extra = _extra(row)
        site_id = row["site_id"]
        for key in ("vendor", "geo", "section"):
            val = extra.get(key)
            if val:
                more = conn.execute(
                    """SELECT id, name, url FROM rows_
                       WHERE site_id=? AND extra_json LIKE ? AND id!=? LIMIT ?""",
                    (site_id, f'%"{key}": "{val}"%', row["id"], limit - len(candidates))
                ).fetchall()
                for r in more:
                    candidates[r["id"]] = r
            if len(candidates) >= limit:
                break

        if len(candidates) < limit:
            rows_same_type = conn.execute(
                """SELECT id, name, url FROM rows_
                   WHERE site_id=? AND row_type=? AND id!=? LIMIT ?""",
                (site_id, row["row_type"], row["id"], limit - len(candidates))
            ).fetchall()
            for r in rows_same_type:
                candidates[r["id"]] = r

    return list(candidates.values())[:limit]


def _format_related(related, cfg):
    if not related:
        return cfg["link_none_note"].strip()
    lines = []
    for r in related:
        url = r["url"] or "(URL ещё не опубликован)"
        lines.append(f"- {r['name']} — {url}")
    return "\n".join(lines)


def _page_kind(row, prompt_style):
    sheet = row["sheet"] or ""
    row_type = (row["row_type"] or "").lower()

    if prompt_style == "personal_ru":
        if sheet == "Blog_Clusters":
            return ("статья блога",
                    "дать полезную, конкретную информацию по теме и мягко подвести читателя к "
                    "мысли о персональной тренировке",
                    "не превращай статью в рекламный лендинг с давлением купить")
        return ("коммерческая страница услуги",
                "помочь посетителю понять, подходит ли ему эта услуга, ответить на частые "
                "вопросы и мотивировать записаться на консультацию",
                "не превращай страницу в информационную статью \"обо всём\" — весь текст должен "
                "работать на решение записаться")

    if prompt_style == "b2b_ru":
        if "статья" in row_type or "блог" in row_type:
            return ("статья блога", "дать полезную техническую информацию и подвести к продукту",
                    "не превращай статью в рекламный текст")
        return ("коммерческая страница (категория оборудования/вендора)",
                "помочь ИТ-специалисту понять, подходит ли решение под его задачу, и подвести "
                "к запросу коммерческого предложения",
                "не растекайся в общие рассуждения об отрасли — держи фокус на решении и задаче заказчика")

    return ("страница товара (продукт для скачивания)",
            "чётко объяснить, что это за файл, для чего он подходит и как его использовать",
            "не пиши общих рассуждений о теме — сразу к делу")


def build_context(row, prompt_style, related_rows=None, breadcrumb=None):
    """Собирает весь контекст для рендера промпта — общий как для дефолтного
    файлового шаблона (master_prompt.md.j2), так и для кастомных шаблонов типов
    страниц, сохранённых на вкладке "Промпт-шаблоны" (см. templates_store.py).
    Кастомные шаблоны получают доступ и к этим готовым полям (input_lines,
    related_block, cfg, limits...), и к «сырым» полям строки через `row`."""
    cfg = _get_site_config(prompt_style)
    extra = _extra(row)
    related = related_rows or []
    has_related = bool(related)
    kind_label, kind_goal, kind_avoid = _page_kind(row, prompt_style)

    input_lines = [
        _field("Название", row["name"]),
        _field("Раздел/тип", row["row_type"]),
        f"URL: {row['url'] or '(ещё не опубликован)'}",
    ]
    if breadcrumb:
        input_lines.append(f"Раздел структуры сайта (хлебные крошки): {breadcrumb}")
    if extra.get("vendor"):
        input_lines.append(f"Вендор: {extra['vendor']}")
    if extra.get("geo"):
        input_lines.append(f"Гео/объект: {extra['geo']}")
    if extra.get("section"):
        input_lines.append(f"Раздел сайта: {extra['section']}")
    input_lines += [
        _field("SEO Title (черновой)", row["seo_title"]),
        _field("H1 (черновой)", row["h1"]),
        _field("Meta Description (черновой)", row["meta_description"]),
        _field("Основной запрос", row["primary_keyword"]),
        _field("Дополнительные запросы", row["secondary_keywords"]),
        _field("LSI-слова (вплетай в текст, не перечисляй списком)", row["lsi_keywords"]),
    ]

    has_faq = bool(row["faq_questions"])
    input_lines.append(_field(
        "Возможные вопросы для FAQ (выбери самые релевантные, не обязательно все)",
        row["faq_questions"]
    ))
    if row["notes"]:
        input_lines.append(_field("Дополнительные пожелания (заметки)", row["notes"]))

    # Короткий список соседних страниц (не всё дерево структуры сайта — это
    # раздувало бы промпт почти без пользы) с ДРУГОЙ рамкой, чем related_block:
    # там те же страницы даны "для перелинковки", здесь — "чтобы не повторяться".
    # Переиспользуем уже полученный related, отдельного похода в БД не делаем.
    sibling_titles = [r["name"] for r in related[:6] if r["name"]]
    sibling_note = None
    if sibling_titles:
        sibling_note = (
            "Другие страницы рядом по теме (не для перелинковки, а для справки — "
            "если тема пересекается, не повторяй те же формулировки и примеры, "
            "что вероятно уже есть там): " + ", ".join(sibling_titles)
        )
        input_lines.append(sibling_note)

    related_block = _format_related(related, cfg)

    return dict(
        row=dict(row),
        cfg=cfg,
        limits=cfg["_limits"],
        ai_openers=cfg["ai_openers"],
        kind_label=kind_label,
        kind_goal=kind_goal,
        kind_avoid=kind_avoid,
        input_lines=input_lines,
        sibling_titles=sibling_titles,
        sibling_note=sibling_note,
        related=related,
        related_block=related_block,
        has_related=has_related,
        has_faq=has_faq,
        breadcrumb=breadcrumb or "",
    )


def build_prompt(row, prompt_style, related_rows=None, breadcrumb=None):
    context = build_context(row, prompt_style, related_rows, breadcrumb)
    template = _env.get_template("master_prompt.md.j2")
    return template.render(**context)


def generate_prompt(row, prompt_style, related_rows=None, breadcrumb=None):
    return build_prompt(row, prompt_style, related_rows, breadcrumb)


def render_custom_template(template_text, row, prompt_style, related_rows=None, breadcrumb=None):
    """Рендерит кастомный шаблон типа страницы (текст из prompt_templates в БД,
    вкладка "Промпт-шаблоны") с тем же контекстом, что и дефолтный шаблон —
    можно использовать и готовые {{ input_lines }}/{{ related_block }}, и
    напрямую поля строки: {{ row.name }}, {{ row.primary_keyword }} и т.д."""
    context = build_context(row, prompt_style, related_rows, breadcrumb)
    template = _env.from_string(template_text)
    return template.render(**context)


def build_lsi_prompt(row, prompt_style, breadcrumb=None):
    """Небольшой самостоятельный промпт «дай мне LSI-слова для этой страницы» —
    для копирования в ChatGPT/Claude и вставки результата обратно в поле LSI
    keywords вручную (кнопка "🔤 LSI" в основной таблице)."""
    context = build_context(row, prompt_style, related_rows=None, breadcrumb=breadcrumb)
    template = _env.get_template("lsi_prompt.md.j2")
    return template.render(**context)


def build_planning_prompt(row, prompt_style, related_rows=None, breadcrumb=None):
    """Этап 1 (необязательный) двухэтапной генерации: промпт для проектирования
    страницы — интент, тип, подход, структура, выбор FAQ/ссылок, тон — без
    написания финального текста. Результат вставляется вручную в поле "План
    страницы" (page_plan), после чего основной промпт (кнопка "Промпт")
    автоматически следует этому плану вместо того, чтобы решать всё сам."""
    context = build_context(row, prompt_style, related_rows, breadcrumb)
    template = _env.get_template("planning_prompt.md.j2")
    return template.render(**context)


def build_image_prompt(row, prompt_style, breadcrumb=None):
    """Этап 3 (необязательный): отдельный промпт только для рекомендаций по
    изображениям — использует "План страницы", если он уже заполнен."""
    context = build_context(row, prompt_style, related_rows=None, breadcrumb=breadcrumb)
    template = _env.get_template("image_prompt.md.j2")
    return template.render(**context)
