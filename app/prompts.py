"""
Генерация промпта для LLM на основе строки таблицы + стиля сайта.
Три стиля: commerce_en (shustrik-maps.com), b2b_ru (itc.by), personal_ru (fit.shustrik-maps.com)
"""
import json


def _extra(row):
    try:
        return json.loads(row["extra_json"] or "{}")
    except Exception:
        return {}


def prompt_commerce_en(row):
    extra = _extra(row)
    geo = extra.get("geo", "")
    return f"""You are writing product copy for an e-commerce site that sells 3D models and maps \
(STL for 3D printing/CNC, OBJ/FBX/C4D for visualization, GeoTIFF/PSD/SVG for GIS/design).

Write the full product page text in English for the following item. Keep it concrete, no fluff, \
no generic marketing adjectives. Follow the structure: short intro (2-3 sentences), a "What's \
included" bullet list, a "Best for" line naming compatible software/printers.

PRODUCT: {row['name']}
URL: {row['url'] or '(not yet published)'}
TYPE: {row['row_type']}
GEO / SUBJECT: {geo}

Use these as guidance, not as text to copy verbatim:
SEO TITLE: {row['seo_title']}
H1: {row['h1']}
META DESCRIPTION: {row['meta_description']}
PRIMARY KEYWORD: {row['primary_keyword']}
SECONDARY KEYWORDS: {row['secondary_keywords']}
LSI KEYWORDS (weave in naturally, don't list them): {row['lsi_keywords']}

Output format:
1. SEO Title (final, <=60 chars)
2. H1
3. Meta Description (140-160 chars)
4. Product description (the actual body copy, 80-150 words)
5. "What's included" bullets
6. "Best for" line
"""


def prompt_b2b_ru(row):
    extra = _extra(row)
    vendor = extra.get("vendor", "")
    section = extra.get("section", "")
    return f"""Ты пишешь текст для B2B-сайта системного интегратора ИТ-решений в Беларуси \
(ИТЦ-М): серверы, СХД, сети, HCI, резервное копирование, виртуализация для дата-центров. \
Аудитория — ИТ-директора и закупщики компаний, тон деловой, без "воды" и маркетинговых \
превосходных степеней, упор на конкретику: характеристики, применение, поставка, гарантия.

СТРАНИЦА: {row['name']}
РАЗДЕЛ: {section}
ВЕНДОР: {vendor or '—'}
ТИП СТРАНИЦЫ: {row['row_type']}
URL: {row['url'] or '(ещё не опубликована)'}

Ориентируйся на эти данные (не копируй дословно, это подсказки):
SEO TITLE: {row['seo_title']}
H1: {row['h1']}
META DESCRIPTION: {row['meta_description']}
ОСНОВНОЙ ЗАПРОС: {row['primary_keyword']}
ДОПОЛНИТЕЛЬНЫЕ ЗАПРОСЫ: {row['secondary_keywords']}
LSI-СЛОВА (вплетай естественно, не перечисляй списком): {row['lsi_keywords']}

Формат ответа:
1. SEO Title (финальный)
2. H1
3. Meta Description (140-160 символов)
4. Основной текст страницы (150-250 слов): что это, для каких задач, почему через ИТЦ-М
   (поставка, гарантия, техподдержка), без выдуманных характеристик — если конкретных цифр
   нет во входных данных, пиши обобщённо (например "широкий модельный ряд", не выдумывай ТТХ)
5. Короткий блок "Почему ИТЦ-М" (2-3 пункта)
"""


def prompt_personal_ru(row):
    extra = _extra(row)
    is_blog = row["sheet"] == "Blog_Clusters"
    faq = row["faq_questions"] or ""
    if is_blog:
        sample_kw = extra.get("sample_keywords", "")
        return f"""Ты пишешь статью для блога личного фитнес-тренера (Мария Сычева, Минск). \
Тон живой, личный, от первого лица, как будто тренер сама объясняет клиенту — без сухого \
канцелярского стиля и без медицинских категоричных заявлений (не диагностируй, не давай
жёстких медицинских рекомендаций, только практические фитнес-советы).

ТЕМА СТАТЬИ: {row['name']}
Примеры реальных запросов, которые должна закрыть статья: {sample_kw}

Ориентируйся на эти данные (не копируй дословно):
SEO TITLE: {row['seo_title']}
H1: {row['h1']}
META DESCRIPTION: {row['meta_description']}
ОСНОВНОЙ ЗАПРОС: {row['primary_keyword']}
ДОПОЛНИТЕЛЬНЫЕ ЗАПРОСЫ: {row['secondary_keywords']}

Формат ответа:
1. SEO Title (финальный)
2. H1
3. Meta Description (140-160 символов)
4. Текст статьи (400-600 слов): практичный, конкретный, с примерами упражнений/шагов
   где уместно, в дружелюбном тоне от первого лица
5. Короткий призыв в конце — записаться на консультацию/тренировку
"""
    else:
        return f"""Ты пишешь текст страницы для сайта личного фитнес-тренера (Мария Сычева, \
Минск). Тон тёплый, личный, от первого лица, вызывающий доверие, без канцелярита.

СТРАНИЦА: {row['name']}
ТИП: {row['row_type']}

Ориентируйся на эти данные (не копируй дословно):
SEO TITLE: {row['seo_title']}
H1: {row['h1']}
META DESCRIPTION: {row['meta_description']}
ОСНОВНОЙ ЗАПРОС: {row['primary_keyword']}
ДОПОЛНИТЕЛЬНЫЕ ЗАПРОСЫ: {row['secondary_keywords']}
{"ГОТОВЫЕ ВОПРОСЫ ДЛЯ FAQ-БЛОКА (используй как есть, ответь на каждый по 2-4 предложения): " + faq if faq else ""}

Формат ответа:
1. SEO Title (финальный)
2. H1
3. Meta Description (140-160 символов)
4. Текст страницы (150-300 слов, от первого лица, тепло и по делу)
{"5. Блок FAQ: вопрос + ответ по каждому из списка выше" if faq else ""}
"""


GENERATORS = {
    "commerce_en": prompt_commerce_en,
    "b2b_ru": prompt_b2b_ru,
    "personal_ru": prompt_personal_ru,
}


def generate_prompt(row, prompt_style):
    fn = GENERATORS.get(prompt_style, prompt_b2b_ru)
    return fn(row)
