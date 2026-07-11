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


def get_related_rows(conn, row, limit=6):
    """Ищет реальные связанные строки того же сайта — сначала по vendor/geo/section из
    extra_json (высокая релевантность), затем добивает по типу страницы."""
    extra = _extra(row)
    site_id = row["site_id"]
    candidates = {}

    for key in ("vendor", "geo", "section"):
        val = extra.get(key)
        if val:
            more = conn.execute(
                """SELECT id, name, url FROM rows_
                   WHERE site_id=? AND extra_json LIKE ? AND id!=? LIMIT ?""",
                (site_id, f'%"{key}": "{val}"%', row["id"], limit)
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


def build_prompt(row, prompt_style, related_rows=None):
    cfg = _get_site_config(prompt_style)
    extra = _extra(row)
    related = related_rows or []
    kind_label, kind_goal, kind_avoid = _page_kind(row, prompt_style)

    input_lines = [
        f"Название: {row['name']}",
        f"Раздел/тип: {row['row_type']}",
        f"URL: {row['url'] or '(ещё не опубликован)'}",
    ]
    if extra.get("vendor"):
        input_lines.append(f"Вендор: {extra['vendor']}")
    if extra.get("geo"):
        input_lines.append(f"Гео/объект: {extra['geo']}")
    if extra.get("section"):
        input_lines.append(f"Раздел сайта: {extra['section']}")
    input_lines += [
        f"SEO Title (черновой): {row['seo_title']}",
        f"H1 (черновой): {row['h1']}",
        f"Meta Description (черновой): {row['meta_description']}",
        f"Основной запрос: {row['primary_keyword']}",
        f"Дополнительные запросы: {row['secondary_keywords']}",
    ]
    if row["lsi_keywords"]:
        input_lines.append(f"LSI-слова (вплетай в текст, не перечисляй списком): {row['lsi_keywords']}")

    has_faq = bool(row["faq_questions"])
    if has_faq:
        input_lines.append(
            f"Возможные вопросы для FAQ (выбери самые релевантные, не обязательно все): {row['faq_questions']}"
        )

    related_block = _format_related(related, cfg)

    template = _env.get_template("master_prompt.md.j2")
    return template.render(
        cfg=cfg,
        limits=cfg["_limits"],
        ai_openers=cfg["ai_openers"],
        kind_label=kind_label,
        kind_goal=kind_goal,
        kind_avoid=kind_avoid,
        input_lines=input_lines,
        related_block=related_block,
        has_faq=has_faq,
    )


def generate_prompt(row, prompt_style, related_rows=None):
    return build_prompt(row, prompt_style, related_rows)
