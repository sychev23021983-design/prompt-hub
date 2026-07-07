"""
Генерация промпта для LLM: единый строгий каркас (Yoast-чеклист, запрет на
выдумывание фактов, структура вывода, Schema, внутренние ссылки, ALT/OG,
самопроверка) + специфика голоса/аудитории под каждый из трёх сайтов.

Внутренние ссылки строятся из РЕАЛЬНЫХ строк базы (related_rows), а не
придумываются моделью — это главное отличие от версии 1.
"""
import json


def _extra(row):
    try:
        return json.loads(row["extra_json"] or "{}")
    except Exception:
        return {}


SITE_CONFIGS = {
    "commerce_en": {
        "language": "English",
        "brand": "the shop",
        "persona": "You are a senior SEO copywriter and 3D/CNC file specialist writing product "
                   "pages for an e-commerce store (shustrik-maps.com) selling 3D terrain models "
                   "and maps: STL for 3D printing/CNC, OBJ/FBX/C4D for visualization, "
                   "GeoTIFF/PSD/SVG for GIS and design.",
        "audience": "Hobbyist 3D printers, CNC hobbyists, game/archviz artists, GIS professionals.",
        "tone_bullets": [
            "concrete and specific, no generic marketing adjectives",
            "short, clear sentences, varied sentence length",
            "active voice, minimal passive voice",
            "each paragraph makes one point",
        ],
        "banned_words": ["best", "unique", "unrivaled", "number one", "amazing", "stunning",
                          "world-class", "cutting-edge"],
        "no_invent": ["exact file size in MB", "polygon count", "exact elevation range in meters",
                      "specific software version numbers"],
        "no_invent_fallback": 'use neutral phrasing like "high-resolution elevation data" or '
                              '"ready for standard 3D printers" instead of inventing numbers',
        "schema_type": "Product",
        "why_us_label": "Why buy from us",
        "why_us_hint": "delivery format, instant download, compatible software/printers, support",
        "link_none_note": "No other real pages were found in the same cluster yet — suggest the "
                          "kind of pages that SHOULD exist (e.g. \"link to the parent category "
                          "page\") without inventing specific fake URLs.",
    },
    "b2b_ru": {
        "language": "русский",
        "brand": "ИТЦ-М",
        "persona": "Ты — Senior SEO-копирайтер и технический специалист по корпоративной "
                   "ИТ-инфраструктуре. Пишешь страницы для сайта системного интегратора ИТЦ-М "
                   "(Беларусь): серверы, СХД, сетевое оборудование, HCI, резервное копирование, "
                   "виртуализация, комплектующие для дата-центров.",
        "audience": "ИТ-директора, системные архитекторы, инженеры, специалисты по закупкам.",
        "tone_bullets": [
            "деловой, экспертный тон, без рекламных штампов",
            "короткие понятные предложения, разнообразная длина",
            "активный залог, минимум пассивного",
            "каждый абзац раскрывает одну мысль",
            "переходные слова между абзацами",
        ],
        "banned_words": ["лучший", "уникальный", "номер один", "revolutionary", "передовой",
                          "непревзойдённый"],
        "no_invent": ["количество процессоров", "объём памяти", "скорость интерфейсов",
                      "поддерживаемые технологии", "конкретные модели без указания во входных данных"],
        "no_invent_fallback": 'используй нейтральные формулировки: "широкий модельный ряд", '
                              '"различные варианты конфигурации", "подбирается под требования проекта"',
        "schema_type": "Product / Service / CollectionPage (выбери подходящий по типу страницы)",
        "why_us_label": "Почему ИТЦ-М",
        "why_us_hint": "поставка, гарантия производителя, техподдержка, сертифицированные инженеры",
        "link_none_note": "Реальных связанных страниц в базе не нашлось — предложи, на какую "
                          "страницу СЛЕДОВАЛО бы сослаться по смыслу (например, на общую страницу "
                          "категории), но не выдумывай конкретные несуществующие URL.",
    },
    "personal_ru": {
        "language": "русский",
        "brand": "Мария Сычева",
        "persona": "Ты — SEO-копирайтер, пишешь от лица личного фитнес-тренера Марии Сычевой "
                   "(Минск) для её сайта fit.shustrik-maps.com.",
        "audience": "Люди, ищущие персонального тренера или информацию о тренировках в Минске: "
                    "разного возраста, разного уровня подготовки, часто новички.",
        "tone_bullets": [
            "тёплый, живой тон от первого лица — как будто тренер говорит с клиентом лично",
            "без канцелярита и без сухих медицинских формулировок",
            "короткие предложения, разговорная интонация, но без панибратства",
            "каждый абзац — одна мысль",
        ],
        "banned_words": ["лучший", "уникальный", "номер один", "чудо-методика", "гарантированный результат"],
        "no_invent": ["медицинские диагнозы", "категоричные обещания результата (\"похудеете на X кг\")",
                      "конкретные цифры без указания во входных данных"],
        "no_invent_fallback": 'используй нейтральные, но живые формулировки: "многие клиенты '
                              'отмечают...", "это помогает большинству, но всё индивидуально"',
        "schema_type": "Service (для страниц услуг) или FAQPage/Article (для страниц с FAQ или для статей блога)",
        "why_us_label": "Почему заниматься со мной",
        "why_us_hint": "личный подход, опыт, сертификаты, гибкий формат (очно/онлайн)",
        "link_none_note": "Связанных страниц в базе не нашлось — сайт ещё в разработке. Предложи, "
                          "на какую страницу из уже описанной структуры сайта логично было бы "
                          "сослаться, не придумывая несуществующих разделов.",
    },
}


def get_related_rows(conn, row, limit=6):
    """Ищет реальные связанные строки того же сайта — сначала по vendor/geo/section из
    extra_json (высокая релевантность), затем добивает по типу страницы — чтобы модель
    предлагала внутренние ссылки на существующие страницы, а не выдумывала их."""
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
        return cfg["link_none_note"]
    lines = []
    for r in related:
        url = r["url"] or "(URL ещё не опубликован)"
        lines.append(f"- {r['name']} — {url}")
    return "\n".join(lines)


def build_prompt(row, prompt_style, related_rows=None):
    cfg = SITE_CONFIGS.get(prompt_style, SITE_CONFIGS["b2b_ru"])
    extra = _extra(row)
    related = related_rows or []

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
    if row["faq_questions"]:
        input_lines.append(f"Готовые вопросы для FAQ (используй как есть): {row['faq_questions']}")

    banned = ", ".join(f'"{w}"' for w in cfg["banned_words"])
    no_invent = "; ".join(cfg["no_invent"])
    tone = "\n".join(f"- {t}" for t in cfg["tone_bullets"])

    prompt = f"""{cfg['persona']}

Целевая аудитория: {cfg['audience']}

Стиль:
{tone}

Никогда не используй слова: {banned}.

Не выдумывай факты. Никогда не придумывай: {no_invent}.
Если конкретной информации нет во входных данных — {cfg['no_invent_fallback']}.

Главный запрос должен встречаться: в SEO Title, в H1, в первых 100 словах текста, и ещё
1-2 раза далее по тексту — без переспама. Дополнительные запросы используй естественно.
LSI-слова вплетай в предложения, не перечисляй списком.

Пиши так, чтобы текст хорошо проходил проверку Yoast SEO: уникальность, читаемость,
разнообразная длина предложений, отсутствие переспама ключевым словом, активный залог,
переходные слова между абзацами, логичная структура с подзаголовками.

=== ВХОДНЫЕ ДАННЫЕ О СТРАНИЦЕ ===
{chr(10).join(input_lines)}

=== РЕАЛЬНЫЕ СВЯЗАННЫЕ СТРАНИЦЫ САЙТА (используй ТОЛЬКО эти ссылки для внутренней перелинковки, не выдумывай другие) ===
{_format_related(related, cfg)}

=== ФОРМАТ ОТВЕТА (строго Markdown, именно эти разделы) ===

# SEO Title
(финальный вариант, ≤60 символов)

# H1

# Meta Description
(140-160 символов)

# Основной текст
(150-250 слов. Структура: краткое описание → для каких задач/кому подходит → преимущества →
{"поставка, настройка и гарантия от " + cfg['brand'] if prompt_style != "personal_ru" else "как начать заниматься со мной"})

# {cfg['why_us_label']}
(2-4 пункта: {cfg['why_us_hint']})

# Рекомендуемые внутренние ссылки
(выбери 3-5 самых уместных из списка "РЕАЛЬНЫЕ СВЯЗАННЫЕ СТРАНИЦЫ" выше, для каждой — одна
строка с кратким обоснованием почему уместна; если список пуст — следуй инструкции в нём)

# Schema
Тип: {cfg['schema_type']}
Заполни поля: name, description{", brand, offers" if prompt_style == "commerce_en" else ", provider"}
{"Если на странице есть FAQ-вопросы — добавь отдельно FAQPage schema с этими вопросами." if row["faq_questions"] else ""}

# Изображения
Для 2-3 предполагаемых изображений на странице дай: ALT, Title, подпись (caption) —
опирайся на тему страницы, не выдумывай, что именно на фото, если это не очевидно из темы.

# Open Graph
OG Title:
OG Description:

# Самопроверка по Yoast
Заполни таблицу (✔ или ✘ + короткий комментарий), и если что-то не соответствует —
исправь сам текст выше, прежде чем выдать финальный ответ:

| Критерий | Статус |
|---|---|
| SEO Title содержит основной запрос | |
| Meta Description 140-160 символов | |
| H1 содержит основной запрос | |
| Плотность ключевых слов не избыточна | |
| Есть переходные слова | |
| Минимум пассивного залога | |
| Есть подзаголовки | |
| Есть внутренние ссылки | |
| Есть ALT для изображений | |
| Читаемость (короткие абзацы, разная длина предложений) | |
"""
    return prompt


def generate_prompt(row, prompt_style, related_rows=None):
    return build_prompt(row, prompt_style, related_rows)
