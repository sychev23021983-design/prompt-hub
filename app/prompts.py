"""
Генерация промпта для LLM: единый строгий каркас (тип страницы и цель, локальное SEO,
EEAT-тон, запрет на AI-штампы, разнообразие между страницами, Yoast-чеклист, запрет на
выдумывание фактов, расширенная Schema, явный блок FAQ, продающие блоки) + специфика
голоса/аудитории под каждый из трёх сайтов.

Внутренние ссылки строятся из РЕАЛЬНЫХ строк базы (related_rows), а не придумываются моделью.
"""
import json


def _extra(row):
    try:
        return json.loads(row["extra_json"] or "{}")
    except Exception:
        return {}


AI_OPENERS_RU = [
    "Если вы", "Сегодня", "В современном мире", "Все больше людей", "Каждый человек",
    "Это отличный способ",
]
AI_OPENERS_EN = [
    "In today's world", "If you're looking for", "Are you looking to", "Nowadays",
    "Everyone wants", "This is a great way to",
]

SITE_CONFIGS = {
    "commerce_en": {
        "language": "English",
        "brand": "the shop",
        "persona": "You are a senior SEO copywriter and 3D/CNC file specialist writing product "
                   "pages for an e-commerce store (shustrik-maps.com) selling 3D terrain models "
                   "and maps: STL for 3D printing/CNC, OBJ/FBX/C4D for visualization, "
                   "GeoTIFF/PSD/SVG for GIS and design.",
        "audience": "Hobbyist 3D printers, CNC hobbyists, game/archviz artists, GIS professionals.",
        "eeat_frame": "Write as someone who has actually printed and used files like this — "
                      "specific and hands-on, not like a generic marketing page.",
        "reader_feelings": ["this seller actually understands 3D printing and CNC files",
                             "I know exactly what file I'm getting and what it works with",
                             "there's nothing hidden or exaggerated here"],
        "tone_bullets": [
            "concrete and specific, no generic marketing adjectives",
            "short, clear sentences, varied sentence length",
            "active voice, minimal passive voice",
            "each paragraph makes one point",
        ],
        "banned_words": ["best", "unique", "unrivaled", "number one", "amazing", "stunning",
                          "world-class", "cutting-edge"],
        "ai_openers": AI_OPENERS_EN,
        "no_invent": ["exact file size in MB", "polygon count", "exact elevation range in meters",
                      "specific software version numbers"],
        "no_invent_fallback": 'use neutral phrasing like "high-resolution elevation data" or '
                              '"ready for standard 3D printers" instead of inventing numbers',
        "local_seo": None,
        "schema_type": "Product",
        "schema_extra": ["brand", "offers (priceCurrency, availability)", "sku (if a slug/id exists)"],
        "why_us_label": "Why buy from us",
        "why_us_hint": "delivery format, instant download, compatible software/printers, support",
        "process_block": None,
        "who_for_block": None,
        "expect_block": None,
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
        "eeat_frame": "Пиши так, будто ты инженер-интегратор, который уже внедрял такие решения "
                      "у корпоративных заказчиков — конкретно, по делу, без нравоучений и без давления.",
        "reader_feelings": ["этот интегратор реально разбирается в теме, а не пересказывает пресс-релиз",
                             "мне понятно, для каких задач это решение и как получить расчёт",
                             "здесь не пытаются продать любой ценой"],
        "tone_bullets": [
            "деловой, экспертный тон, без рекламных штампов",
            "короткие понятные предложения, разнообразная длина",
            "активный залог, минимум пассивного",
            "каждый абзац раскрывает одну мысль",
            "переходные слова между абзацами",
        ],
        "banned_words": ["лучший", "уникальный", "номер один", "revolutionary", "передовой",
                          "непревзойдённый"],
        "ai_openers": AI_OPENERS_RU,
        "no_invent": ["количество процессоров", "объём памяти", "скорость интерфейсов",
                      "поддерживаемые технологии", "конкретные модели без указания во входных данных"],
        "no_invent_fallback": 'используй нейтральные формулировки: "широкий модельный ряд", '
                              '"различные варианты конфигурации", "подбирается под требования проекта"',
        "local_seo": ["Минск", "Беларусь"],
        "schema_type": "Product / Service / CollectionPage (выбери подходящий по типу страницы)",
        "schema_extra": ["provider: ИТЦ-М", "serviceType (если применимо)", "areaServed: Беларусь",
                         "availableChannel", "telephone (если известен)", "sameAs (если известен)"],
        "why_us_label": "Почему ИТЦ-М",
        "why_us_hint": "поставка, гарантия производителя, техподдержка, сертифицированные инженеры",
        "process_block": {
            "title": "Как проходит работа с нами",
            "hint": "запрос → консультация и подбор конфигурации → коммерческое предложение → "
                    "поставка и настройка → гарантийное сопровождение",
        },
        "who_for_block": {
            "title": "Кому подходит",
            "hint": "опиши 3-5 характерных сценариев/типов заказчика для этой категории оборудования",
        },
        "expect_block": None,
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
        "eeat_frame": "Пиши так, будто тренер объясняет человеку после бесплатной первой "
                      "консультации — спокойно, без нравоучений, без запугивания и без давления.",
        "reader_feelings": ["со мной спокойно", "меня не будут заставлять и сравнивать с другими",
                             "мне помогут и всё объяснят", "я смогу начать даже без подготовки"],
        "tone_bullets": [
            "тёплый, живой тон от первого лица — как будто тренер говорит с клиентом лично",
            "без канцелярита и без сухих медицинских формулировок",
            "короткие предложения, разговорная интонация, но без панибратства",
            "каждый абзац — одна мысль",
        ],
        "banned_words": ["лучший", "уникальный", "номер один", "чудо-методика", "гарантированный результат"],
        "ai_openers": AI_OPENERS_RU,
        "no_invent": ["медицинские диагнозы", "категоричные обещания результата (\"похудеете на X кг\")",
                      "конкретные цифры без указания во входных данных"],
        "no_invent_fallback": 'используй нейтральные, но живые формулировки: "многие клиенты '
                              'отмечают...", "это помогает большинству, но всё индивидуально"',
        "local_seo": ["Минск"],
        "schema_type": "Service (для страниц услуг) или FAQPage/Article (для страниц с FAQ или для статей блога)",
        "schema_extra": ["provider: Мария Сычева", "serviceType", "areaServed: Минск",
                         "availableChannel (очно / онлайн)"],
        "why_us_label": "Почему заниматься со мной",
        "why_us_hint": "личный подход, опыт, сертификаты, гибкий формат (очно/онлайн)",
        "process_block": {
            "title": "Что будет на первом занятии",
            "hint": "знакомство → обсуждение целей → оценка уровня подготовки → первое безопасное "
                    "занятие → рекомендации домой",
        },
        "who_for_block": {
            "title": "Кому подходит",
            "hint": "новичкам, после длительного перерыва, после 40 лет, при сидячей работе, при "
                    "проблемах с осанкой, для укрепления мышц корпуса — выбери уместное для темы страницы",
        },
        "expect_block": {
            "title": "Чего ожидать",
            "hint": "не обещай результат, опиши ощущения: тело чувствуется лучше, улучшается "
                    "подвижность, укрепляются глубокие мышцы, движения увереннее, осанка меняется "
                    "постепенно",
        },
        "link_none_note": "Связанных страниц в базе не нашлось — сайт ещё в разработке. Предложи, "
                          "на какую страницу из уже описанной структуры сайта логично было бы "
                          "сослаться, не придумывая несуществующих разделов.",
    },
}


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
        return cfg["link_none_note"]
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
    cfg = SITE_CONFIGS.get(prompt_style, SITE_CONFIGS["b2b_ru"])
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
        input_lines.append(f"Возможные вопросы для FAQ (выбери самые релевантные, не обязательно все): {row['faq_questions']}")

    banned = ", ".join(f'"{w}"' for w in cfg["banned_words"])
    no_invent = "; ".join(cfg["no_invent"])
    tone = "\n".join(f"- {t}" for t in cfg["tone_bullets"])
    ai_openers = ", ".join(f'"{p}..."' for p in cfg["ai_openers"])
    feelings = "; ".join(f'"{f}"' for f in cfg["reader_feelings"])
    local_seo_block = ""
    if cfg["local_seo"]:
        terms = ", ".join(cfg["local_seo"])
        local_seo_block = (f"\nЛокальное SEO: естественно упоминай {terms} и релевантные "
                           f"местные формулировки — не вставляй город в каждое предложение, "
                           f"достаточно 2-3 упоминаний по тексту.\n")

    extra_blocks = ""
    if cfg["who_for_block"]:
        extra_blocks += f"\n# {cfg['who_for_block']['title']}\n({cfg['who_for_block']['hint']} — 3-5 пунктов)\n"
    if cfg["process_block"]:
        extra_blocks += f"\n# {cfg['process_block']['title']}\n({cfg['process_block']['hint']})\n"
    if cfg["expect_block"]:
        extra_blocks += f"\n# {cfg['expect_block']['title']}\n({cfg['expect_block']['hint']})\n"

    faq_section = ""
    if has_faq:
        faq_section = ("\n# FAQ\nВыбери 6-10 самых релевантных вопросов из входных данных (не "
                       "обязательно все) и дай на каждый краткий, живой ответ (2-4 предложения), "
                       "без выдуманных цифр.\n")

    schema_extra_str = ", ".join(cfg["schema_extra"])
    delivery_line = ("поставка, настройка и гарантия от " + cfg['brand']) if prompt_style != "personal_ru" else "как начать заниматься со мной"

    prompt = f"""{cfg['persona']}

Целевая аудитория: {cfg['audience']}

ВАЖНО — тип и цель этой страницы:
Это {kind_label}. Цель страницы — {kind_goal}. {kind_avoid}.

{cfg['eeat_frame']}

После прочтения читатель должен почувствовать: {feelings}.

Стиль:
{tone}

Никогда не используй слова: {banned}.
Никогда не начинай текст (и абзацы) с фраз вроде: {ai_openers} — это типичные признаки
текста, написанного ИИ.
{local_seo_block}
Если эта страница — не единственная, которую ты пишешь: каждая страница должна заметно
отличаться от других по структуре, формулировкам, примеру начала и логике изложения —
не используй одинаковые шаблонные первые абзацы от страницы к странице.

Не выдумывай факты. Никогда не придумывай: {no_invent}.
Если конкретной информации нет во входных данных — {cfg['no_invent_fallback']}.

Главный запрос должен встречаться: в SEO Title, в H1, в первых 100 словах текста, и ещё
1-2 раза далее по тексту — без переспама. Дополнительные запросы используй естественно.
LSI-слова вплетай в предложения, не перечисляй списком.
Там, где уместно по смыслу, естественно упомяни в самом тексте (не только в отдельном
списке ниже) 1-2 связанные страницы из списка "РЕАЛЬНЫЕ СВЯЗАННЫЕ СТРАНИЦЫ" — это сильнее
для SEO, чем просто список ссылок в конце.

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
{delivery_line})

# {cfg['why_us_label']}
(2-4 пункта: {cfg['why_us_hint']})
{extra_blocks}
# Рекомендуемые внутренние ссылки
(выбери 3-5 самых уместных из списка "РЕАЛЬНЫЕ СВЯЗАННЫЕ СТРАНИЦЫ" выше, для каждой — одна
строка с кратким обоснованием почему уместна; если список пуст — следуй инструкции в нём)
{faq_section}
# CTA (призыв к действию в конце страницы)
Спокойное, без давления приглашение — записаться / оставить заявку / запросить КП
(в зависимости от типа сайта), 1-2 предложения.

# Schema
Тип: {cfg['schema_type']}
Заполни поля: name, description, {schema_extra_str}
{"Если выбраны FAQ-вопросы выше — добавь отдельно FAQPage schema с этими вопросами и ответами." if has_faq else ""}

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
| Есть внутренние ссылки (включая упоминание в тексте) | |
| Нет типичных AI-штампов в начале абзацев | |
| Есть ALT для изображений | |
| Читаемость (короткие абзацы, разная длина предложений) | |
"""
    return prompt


def generate_prompt(row, prompt_style, related_rows=None):
    return build_prompt(row, prompt_style, related_rows)
