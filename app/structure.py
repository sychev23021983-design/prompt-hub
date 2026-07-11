"""
Структура сайта (вкладка "Структура"): раскрывающееся дерево разделов, которое
пользователь заполняет вручную (обычно вставкой из KeyCollector), и привязка
страниц из общей таблицы (rows_) к узлам этого дерева.

Хранение: structure_nodes(site_id, parent_id, title, slug, sort_order, path_order).
rows_.structure_node_id — необязательная ссылка на узел, к которому привязана страница.

path_order — материализованный путь вида "0001.0007.0002": склейка zero-padded
sort_order узла и всех его предков. Сортировка по этому текстовому полю целиком
даёт правильный pre-order обход дерева одним ORDER BY, без рекурсивных запросов
на чтение (SQLite recursive CTE работают, но так проще и быстрее для сотен узлов).
"""
import re

CYRILLIC_TO_LATIN = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}


def slugify(text):
    """Транслитерация + приведение к безопасному сегменту URL. Работает и для
    русского, и для английского текста (для EN просто нижний регистр + дефисы)."""
    if not text:
        return ""
    text = text.strip().lower()
    text = "".join(CYRILLIC_TO_LATIN.get(ch, ch) for ch in text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def _looks_2space(text):
    indents = set()
    for raw_line in text.splitlines():
        if not raw_line.strip() or "\t" in raw_line:
            continue
        stripped = raw_line.lstrip(" ")
        n = len(raw_line) - len(stripped)
        if n:
            indents.add(n)
    return bool(indents) and min(indents) == 2


def _renormalize_depths(text):
    items = []
    stack_widths = []  # индент-ширины текущего пути, по возрастанию
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        line = raw_line.rstrip("\n")
        stripped = line.lstrip(" \t")
        indent = line[: len(line) - len(stripped)]
        width = len(indent.replace("\t", "    "))
        title = re.sub(r"^[-*•]\s*", "", stripped).strip()
        if not title:
            continue
        while stack_widths and stack_widths[-1] >= width:
            stack_widths.pop()
        depth = len(stack_widths)
        stack_widths.append(width)
        items.append({"depth": depth, "title": title})
    return items


def parse_indented_tree(text):
    """Парсит вставленный текст с древовидной структурой в плоский список
    {depth, title} в порядке появления. Поддерживает отступы табами или
    пробелами (2 или 4 пробела = один уровень), а также маркеры "- "/"* " перед
    названием. Пустые строки игнорируются.

    Пример входа:
        Оборудование
            Серверы
                Dell
                HPE
            СХД

    -> [(0,"Оборудование"), (1,"Серверы"), (2,"Dell"), (2,"HPE"), (1,"СХД")]
    """
    if _looks_2space(text):
        return _renormalize_depths(text)

    items = []
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        line = raw_line.rstrip("\n")
        stripped = line.lstrip(" \t")
        indent = line[: len(line) - len(stripped)]
        indent_width = indent.replace("\t", "    ")
        depth = len(indent_width) // 4 if indent_width else 0
        title = re.sub(r"^[-*•]\s*", "", stripped).strip()
        if title:
            items.append({"depth": depth, "title": title})
    return items


def import_tree_text(conn, site_id, text):
    """Добавляет/обновляет узлы дерева из вставленного текста. Никогда не
    удаляет существующие узлы (в т.ч. с привязанными страницами) — только
    находит-или-создаёт по пути (родитель + title), чтобы повторная вставка
    обновлённого списка из KeyCollector не рвала уже сделанные привязки."""
    items = parse_indented_tree(text)
    created, matched = 0, 0
    parent_stack = [None]  # parent_stack[d] = id родителя для глубины d

    for item in items:
        depth, title = item["depth"], item["title"]
        parent_id = parent_stack[depth] if depth < len(parent_stack) else parent_stack[-1]

        existing = conn.execute(
            """SELECT id FROM structure_nodes
               WHERE site_id=? AND title=? AND
                     ((parent_id IS NULL AND ? IS NULL) OR parent_id=?)""",
            (site_id, title, parent_id, parent_id)
        ).fetchone()

        if existing:
            node_id = existing["id"]
            matched += 1
        else:
            next_order = conn.execute(
                """SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM structure_nodes
                   WHERE site_id=? AND ((parent_id IS NULL AND ? IS NULL) OR parent_id=?)""",
                (site_id, parent_id, parent_id)
            ).fetchone()["n"]
            cur = conn.execute(
                """INSERT INTO structure_nodes (site_id, parent_id, title, slug, sort_order)
                   VALUES (?,?,?,?,?)""",
                (site_id, parent_id, title, slugify(title), next_order)
            )
            node_id = cur.lastrowid
            created += 1

        parent_stack = parent_stack[: depth + 1]
        if len(parent_stack) <= depth + 1:
            parent_stack.append(node_id)
        else:
            parent_stack[depth + 1] = node_id
        parent_stack = parent_stack[: depth + 2]

    conn.commit()
    recompute_path_order(conn, site_id)
    return {"created": created, "matched": matched, "total": len(items)}


def recompute_path_order(conn, site_id):
    """Пересчитывает path_order для всех узлов сайта: zero-padded sort_order
    self + всех предков, склеенные через точку — для сортировки всего дерева
    одним ORDER BY path_order (pre-order обход)."""
    nodes = conn.execute(
        "SELECT id, parent_id, sort_order FROM structure_nodes WHERE site_id=?",
        (site_id,)
    ).fetchall()
    by_id = {n["id"]: n for n in nodes}
    cache = {}

    def path_for(node_id):
        if node_id in cache:
            return cache[node_id]
        n = by_id[node_id]
        segment = f"{n['sort_order']:05d}"
        prefix = path_for(n["parent_id"]) + "." if n["parent_id"] and n["parent_id"] in by_id else ""
        result = prefix + segment
        cache[node_id] = result
        return result

    for n in nodes:
        conn.execute("UPDATE structure_nodes SET path_order=? WHERE id=?", (path_for(n["id"]), n["id"]))
    conn.commit()


def get_tree(conn, site_id):
    """Дерево узлов для рендера: список корней, у каждого узла — .children,
    .attached_count (сколько страниц привязано)."""
    nodes = conn.execute(
        """SELECT sn.*, (SELECT COUNT(*) FROM rows_ r WHERE r.structure_node_id = sn.id) AS attached_count
           FROM structure_nodes sn WHERE sn.site_id=? ORDER BY sn.path_order""",
        (site_id,)
    ).fetchall()

    by_id = {}
    roots = []
    for n in nodes:
        d = dict(n)
        d["children"] = []
        by_id[d["id"]] = d
    for n in nodes:
        d = by_id[n["id"]]
        if n["parent_id"] and n["parent_id"] in by_id:
            by_id[n["parent_id"]]["children"].append(d)
        else:
            roots.append(d)
    return roots


def get_flat_options(conn, site_id):
    """Плоский список узлов с отступом в названии — для <select> привязки
    страницы к разделу (сортировка совпадает с деревом)."""
    nodes = conn.execute(
        "SELECT * FROM structure_nodes WHERE site_id=? ORDER BY path_order",
        (site_id,)
    ).fetchall()
    options = []
    for n in nodes:
        depth = (n["path_order"] or "").count(".")
        options.append({"id": n["id"], "label": ("— " * depth) + n["title"]})
    return options


def get_breadcrumbs(conn, site_id):
    """{node_id: 'Раздел / Подраздел / Узел'} для всех узлов сайта — для колонки
    "Раздел" в основной таблице."""
    nodes = conn.execute(
        "SELECT id, parent_id, title FROM structure_nodes WHERE site_id=?",
        (site_id,)
    ).fetchall()
    by_id = {n["id"]: n for n in nodes}
    cache = {}

    def crumb(node_id):
        if node_id in cache:
            return cache[node_id]
        n = by_id[node_id]
        prefix = crumb(n["parent_id"]) + " / " if n["parent_id"] and n["parent_id"] in by_id else ""
        result = prefix + n["title"]
        cache[node_id] = result
        return result

    return {n["id"]: crumb(n["id"]) for n in nodes}


def node_path(conn, node_id):
    """Список узлов от корня до node_id включительно."""
    path = []
    current_id = node_id
    guard = 0
    while current_id and guard < 50:
        guard += 1
        n = conn.execute("SELECT * FROM structure_nodes WHERE id=?", (current_id,)).fetchone()
        if not n:
            break
        path.append(n)
        current_id = n["parent_id"]
    return list(reversed(path))


def suggest_url(conn, row):
    """Предлагает относительный URL для страницы на основе пути её узла в
    структуре (слаги разделов) + слага собственного названия страницы."""
    segments = []
    if row["structure_node_id"]:
        for n in node_path(conn, row["structure_node_id"]):
            if n["slug"]:
                segments.append(n["slug"])
    own_slug = slugify(row["name"] or "")
    if own_slug:
        segments.append(own_slug)
    if not segments:
        return ""
    return "/" + "/".join(segments) + "/"
