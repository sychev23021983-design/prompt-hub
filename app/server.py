import os
import subprocess
from datetime import date

from flask import Flask, render_template, request, jsonify, redirect, url_for

from db import get_conn, init_db
from prompts import generate_prompt, get_related_rows

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

    query = """SELECT r.*, s.name as site_name, s.slug as site_slug, s.prompt_style
               FROM rows_ r JOIN sites s ON s.id = r.site_id WHERE 1=1"""
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
    query += " ORDER BY s.id, r.sheet, r.id LIMIT 500"

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

    conn.close()
    return render_template("index.html", sites=sites, rows=rows, stats=stats,
                            current_site=site_slug, current_applied=applied_filter, q=search)


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
    conn.close()

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Export"
    headers = ["sheet", "name", "url", "row_type", "seo_title", "h1", "meta_description",
               "primary_keyword", "secondary_keywords", "lsi_keywords", "faq_questions",
               "applied", "date_applied", "notes"]
    ws.append(headers)
    for r in rows:
        ws.append([r[h] if h in r.keys() else "" for h in headers])

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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8040)), debug=False)
