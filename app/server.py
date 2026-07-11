import os
import subprocess
from datetime import date

from flask import Flask, render_template, request, jsonify, redirect, url_for

from db import get_conn, init_db
from prompts import generate_prompt, get_related_rows
import structure

app = Flask(__name__)

REPO_DIR = os.environ.get("PROMPT_HUB_REPO_DIR", "/app/data/seo-repos")

# Инициализация БД и первый импорт при старте (нужно и под gunicorn, где __main__ не
# выполняется). Импорт запускается только если таблица sites ещё пуста — повторные
# рестарты контейнера не будут затирать прогресс (Applied?/Notes), для обновления
# данных используйте кнопку "Обновить данные из xlsx" (/reimport).
init_db()
_conn = get_conn()
_sites_count = _conn.execute("SELECT COUNT(*) c FROM sites").fetchone()["c"]
_conn.close()
if _sites_count == 0:
    subprocess.run(["python", "import.py"], cwd=os.path.dirname(__file__))


@app.route("/")
def index():
    conn = get_conn()
    sites = conn.execute("SELECT * FROM sites ORDER BY id").fetchall()

    site_slug = request.args.get("site", "")
    applied_filter = request.args.get("applied", "")
    search = request.args.get("q", "").strip()

    query = """SELECT r.*, s.name as site_name, s.slug as site_slug, s.prompt_style,
                      sn.path_order as node_path_order
               FROM rows_ r JOIN sites s ON s.id = r.site_id
               LEFT JOIN structure_nodes sn ON sn.id = r.structure_node_id
               WHERE 1=1"""
    params = []
    if site_slug:
        query += " AND s.slug = ?"
        params.append(site_slug)
    if applied_filter:
        query += " AND r.applied = ?"
        params.append(applied_filter)
    if search:
        query += " AND (r.name LIKE ? OR r.primary_keyword LIKE ? OR r.seo_title LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    # Сортировка: сначала по сайту, внутри сайта — привязанные к структуре страницы
    # идут в порядке дерева (sn.path_order), непривязанные — общим хвостом в конце.
    query += " ORDER BY s.id, (r.structure_node_id IS NULL), sn.path_order, r.sheet, r.id LIMIT 500"

    rows = conn.execute(query, params).fetchall()

    counts = conn.execute("""
        SELECT s.slug, r.applied, COUNT(*) c FROM rows_ r
        JOIN sites s ON s.id = r.site_id GROUP BY s.slug, r.applied
    """).fetchall()
    stats = {}
    for c in counts:
        stats.setdefault(c["slug"], {"Yes": 0, "No": 0, "Skipped": 0, "total": 0})
        stats[c["slug"]][c["applied"] or "No"] = c["c"]
        stats[c["slug"]]["total"] += c["c"]

    # Опции для привязки к разделу структуры (по сайту) + хлебные крошки для колонки "Раздел"
    site_options = {}
    breadcrumbs = {}
    for s in sites:
        site_options[s["id"]] = structure.get_flat_options(conn, s["id"])
        breadcrumbs.update(structure.get_breadcrumbs(conn, s["id"]))

    conn.close()
    return render_template("index.html", sites=sites, rows=rows, stats=stats,
                            current_site=site_slug, current_applied=applied_filter, q=search,
                            site_options=site_options, breadcrumbs=breadcrumbs)


@app.route("/prompt/<int:row_id>")
def get_prompt(row_id):
    conn = get_conn()
    row = conn.execute("""SELECT r.*, s.prompt_style FROM rows_ r
                           JOIN sites s ON s.id = r.site_id WHERE r.id=?""", (row_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "not found"}), 404
    related = get_related_rows(conn, row)
    conn.close()
    text = generate_prompt(row, row["prompt_style"], related)
    return jsonify({"prompt": text})


EDITABLE_FIELDS = {
    "name", "url", "seo_title", "h1", "meta_description", "primary_keyword",
    "secondary_keywords", "lsi_keywords", "faq_questions", "notes",
}


@app.route("/update/<int:row_id>", methods=["POST"])
def update_field(row_id):
    data = request.get_json(silent=True) or {}
    field = data.get("field", "")
    value = data.get("value", "")
    if field not in EDITABLE_FIELDS:
        return jsonify({"error": f"field '{field}' is not editable"}), 400
    conn = get_conn()
    conn.execute(f"UPDATE rows_ SET {field}=? WHERE id=?", (value, row_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "field": field})


@app.route("/mark/<int:row_id>", methods=["POST"])
def mark_row(row_id):
    status = request.form.get("applied", "Yes")
    notes = request.form.get("notes", "")
    conn = get_conn()
    conn.execute("UPDATE rows_ SET applied=?, date_applied=?, notes=? WHERE id=?",
                 (status, date.today().isoformat() if status == "Yes" else None, notes, row_id))
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("index"))


@app.route("/export/<slug>")
def export_site(slug):
    """Экспортирует текущее состояние сайта обратно в xlsx (для ручной заливки в GitHub)."""
    import openpyxl
    conn = get_conn()
    site = conn.execute("SELECT * FROM sites WHERE slug=?", (slug,)).fetchone()
    if not site:
        return "site not found", 404
    rows = conn.execute("SELECT * FROM rows_ WHERE site_id=? ORDER BY sheet, id", (site["id"],)).fetchall()
    breadcrumbs = structure.get_breadcrumbs(conn, site["id"])
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Export"
    headers = ["sheet", "name", "url", "row_type", "раздел", "seo_title", "h1", "meta_description",
               "primary_keyword", "secondary_keywords", "lsi_keywords", "faq_questions",
               "applied", "date_applied", "notes"]
    ws.append(headers)
    for r in rows:
        values = []
        for h in headers:
            if h == "раздел":
                values.append(breadcrumbs.get(r["structure_node_id"], ""))
            else:
                values.append(r[h] if h in r.keys() else "")
        ws.append(values)

    out_path = f"/tmp/{slug}_export.xlsx"
    wb.save(out_path)
    from flask import send_file
    return send_file(out_path, as_attachment=True, download_name=f"{slug}_export.xlsx")


@app.route("/reimport", methods=["POST"])
def reimport():
    """Перезапускает импортёр (после того как вы обновили xlsx в import_data/)."""
    result = subprocess.run(["python", "import.py"], cwd=os.path.dirname(__file__),
                             capture_output=True, text=True)
    return jsonify({"stdout": result.stdout, "stderr": result.stderr, "returncode": result.returncode})


# ---------------------------------------------------------------------------
# Структура сайта: дерево разделов (заполняется вручную/вставкой из KeyCollector)
# + привязка страниц из общей таблицы + подсказка URL по пути в дереве.
# ---------------------------------------------------------------------------

@app.route("/structure/<slug>")
def structure_view(slug):
    conn = get_conn()
    site = conn.execute("SELECT * FROM sites WHERE slug=?", (slug,)).fetchone()
    if not site:
        conn.close()
        return "site not found", 404
    tree = structure.get_tree(conn, site["id"])
    flat_options = structure.get_flat_options(conn, site["id"])
    unattached = conn.execute(
        "SELECT id, name, sheet FROM rows_ WHERE site_id=? AND structure_node_id IS NULL ORDER BY sheet, id",
        (site["id"],)
    ).fetchall()
    conn.close()
    return render_template("structure.html", site=site, tree=tree, unattached=unattached,
                            flat_options=flat_options)


@app.route("/structure/<slug>/import", methods=["POST"])
def structure_import(slug):
    """Принимает вставленный текст дерева (из KeyCollector) и находит-или-создаёт
    узлы по пути — существующие привязки страниц никогда не удаляются."""
    conn = get_conn()
    site = conn.execute("SELECT * FROM sites WHERE slug=?", (slug,)).fetchone()
    if not site:
        conn.close()
        return jsonify({"error": "site not found"}), 404
    text = (request.get_json(silent=True) or {}).get("text", "")
    if not text.strip():
        conn.close()
        return jsonify({"error": "empty text"}), 400
    stats = structure.import_tree_text(conn, site["id"], text)
    conn.close()
    return jsonify({"ok": True, **stats})


@app.route("/structure/node", methods=["POST"])
def structure_add_node():
    """Ручное добавление одного узла (корневого или дочернего)."""
    data = request.get_json(silent=True) or {}
    slug = data.get("site_slug", "")
    parent_id = data.get("parent_id") or None
    title = (data.get("title") or "").strip()
    if not title:
        return jsonify({"error": "title required"}), 400
    conn = get_conn()
    site = conn.execute("SELECT * FROM sites WHERE slug=?", (slug,)).fetchone()
    if not site:
        conn.close()
        return jsonify({"error": "site not found"}), 404
    next_order = conn.execute(
        """SELECT COALESCE(MAX(sort_order), -1) + 1 AS n FROM structure_nodes
           WHERE site_id=? AND ((parent_id IS NULL AND ? IS NULL) OR parent_id=?)""",
        (site["id"], parent_id, parent_id)
    ).fetchone()["n"]
    cur = conn.execute(
        "INSERT INTO structure_nodes (site_id, parent_id, title, slug, sort_order) VALUES (?,?,?,?,?)",
        (site["id"], parent_id, title, structure.slugify(title), next_order)
    )
    node_id = cur.lastrowid
    conn.commit()
    structure.recompute_path_order(conn, site["id"])
    conn.close()
    return jsonify({"ok": True, "id": node_id})


@app.route("/structure/node/<int:node_id>", methods=["POST"])
def structure_update_node(node_id):
    """Переименование узла и/или изменение его slug (сегмента URL)."""
    data = request.get_json(silent=True) or {}
    conn = get_conn()
    node = conn.execute("SELECT * FROM structure_nodes WHERE id=?", (node_id,)).fetchone()
    if not node:
        conn.close()
        return jsonify({"error": "not found"}), 404
    title = data.get("title")
    node_slug = data.get("slug")
    if title is not None:
        conn.execute("UPDATE structure_nodes SET title=? WHERE id=?", (title.strip(), node_id))
    if node_slug is not None:
        conn.execute("UPDATE structure_nodes SET slug=? WHERE id=?", (structure.slugify(node_slug), node_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/structure/node/<int:node_id>/delete", methods=["POST"])
def structure_delete_node(node_id):
    """Удаляет узел, только если у него нет ни дочерних разделов, ни привязанных
    страниц — чтобы случайно не потерять данные."""
    conn = get_conn()
    node = conn.execute("SELECT * FROM structure_nodes WHERE id=?", (node_id,)).fetchone()
    if not node:
        conn.close()
        return jsonify({"error": "not found"}), 404
    children = conn.execute("SELECT COUNT(*) c FROM structure_nodes WHERE parent_id=?", (node_id,)).fetchone()["c"]
    attached = conn.execute("SELECT COUNT(*) c FROM rows_ WHERE structure_node_id=?", (node_id,)).fetchone()["c"]
    if children or attached:
        conn.close()
        return jsonify({"error": f"нельзя удалить: {children} подразделов, {attached} привязанных страниц"}), 400
    conn.execute("DELETE FROM structure_nodes WHERE id=?", (node_id,))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/attach/<int:row_id>", methods=["POST"])
def attach_row(row_id):
    """Привязывает (или отвязывает, если node_id пуст) страницу к разделу структуры."""
    data = request.get_json(silent=True) or {}
    node_id = data.get("node_id") or None
    conn = get_conn()
    conn.execute("UPDATE rows_ SET structure_node_id=? WHERE id=?", (node_id, row_id))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/suggest_url/<int:row_id>")
def suggest_url_route(row_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM rows_ WHERE id=?", (row_id,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"error": "not found"}), 404
    suggestion = structure.suggest_url(conn, row)
    conn.close()
    return jsonify({"url": suggestion})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8040)), debug=False)
