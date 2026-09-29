"""Render docs/architecture.svg + .png — the as-built architecture mapped onto Figure 1."""
from pathlib import Path
from xml.sax.saxutils import escape

W, H = 1480, 1030
LAYERS = [
    ("1. DATA SOURCES", "#1F5AA6", [
        ("Electricity smart meters", "15-min kWh · synthetic UK profile", "or SGCC adapter (data/sgcc.py)"),
        ("Gas smart meters", "hourly m3 · heating pattern", "data/generator.py"),
        ("Water meters", "irregular 5-30 min L/min", "UK local time (DST test)")]),
    ("2. INGESTION", "#1B3F73", [
        ("Apache Kafka 3.9 (KRaft)", "topic meter-readings-raw", "ingestion/producer.py"),
        ("Validate + clean", "schema, range, duplicates, sentinels", "validation.py · cleaning.py"),
        ("Normalise timestamps", "UTC + canonical grid, gap fill", "normalise.py"),
        ("Feature extraction", "11 causal features, per-meter buffer", "features.py · stream_processor.py")]),
    ("3. STORAGE", "#23807A", [
        ("raw_readings", "hypertable, compression, retention", "storage/schema.sql"),
        ("processed_readings", "features, scores, latency_ms", "hypertable"),
        ("hourly_consumption", "continuous aggregate (history)", "cross-utility axis"),
        ("anomalies + audit_log", "alerts, status, threshold changes", "study_responses")]),
    ("4. DETECTION", "#4E8A2E", [
        ("Statistical", "Z-score (hourly profile)", "24-hour moving average"),
        ("Machine learning", "Isolation Forest", "One-Class SVM"),
        ("Deep learning", "LSTM autoencoder (PyTorch)", "16-step windows"),
        ("Ensemble", "F1-weighted percentile fusion", "detection/engine.py")]),
    ("5. VISUALISATION", "#5B3F99", [
        ("Real-time", "monitoring", "replay / live DB"), ("Historical", "analysis", "60-day record"),
        ("Cross-utility", "comparison", "hourly common axis"), ("Alerts &", "notifications", "ack · dismiss · escalate"),
        ("Model", "performance", "KPIs, H1 / H2"), ("Explainable AI", "insights", "SHAP · LIME · narrative"),
        ("User study", "RQ3 / H3", "SUS · TAM · trust")]),
    ("6. USERS", "#2C3E57", [("Utility network operators", "monitoring only — every action audited; thresholds operator-mediated", "")]),
]
CROSS = [
    ("Monitoring & logging", ["JSON logs (logging_setup.py)", "latency CSV + reports/"]),
    ("Alert management", ["severity, debounce, escalation", "cross-utility co-occurrence", "alerts/rules.py"]),
    ("Security & privacy", ["no PII, env secrets", "least-privilege DB roles", "API key on writes"]),
    ("API layer", ["FastAPI REST (api/main.py)", "/readings /anomalies /metrics", "/thresholds /alerts/{id}/ack"]),
    ("Backup & recovery", ["pg_dump rotation", "ops/backup/backup.sh"]),
]


def t(x, y, s, size=13, weight=400, fill="#1D2327", anchor="start"):
    return (f'<text x="{x}" y="{y}" font-family="Inter, Helvetica, Arial, sans-serif" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}">{escape(s)}</text>')


out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">',
       f'<rect width="{W}" height="{H}" fill="#FFFFFF"/>',
       '<defs><marker id="a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
       '<path d="M1 1L9 5L1 9z" fill="#5A6B78"/></marker></defs>',
       t(40, 44, "Confluence — as-built architecture (mapped to Figure 1 of the proposal)", 22, 700),
       t(40, 68, "Kappa architecture: one streaming path for live detection and historical replay. Module paths are relative to src/confluence/.", 13, 400, "#5A6B78")]
x0, lw, cw = 40, 170, 1010
y, rh, gap = 90, 128, 24
for i, (name, color, boxes) in enumerate(LAYERS):
    h = {3: rh + 34, 5: 78}.get(i, rh)
    out.append(f'<rect x="{x0}" y="{y}" width="{lw + cw}" height="{h}" rx="8" fill="{color}" fill-opacity="0.06" stroke="{color}" stroke-width="1.2"/>')
    out.append(f'<rect x="{x0}" y="{y}" width="{lw}" height="{h}" rx="8" fill="{color}"/>')
    words = name.split(" ", 1)
    out.append(t(x0 + 16, y + h / 2 - 2, words[0], 15, 700, "#FFFFFF"))
    out.append(t(x0 + 16, y + h / 2 + 17, words[1] if len(words) > 1 else "", 15, 700, "#FFFFFF"))
    n = len(boxes)
    bx, bw_total = x0 + lw + 16, cw - 32
    bw = (bw_total - (n - 1) * 12) / n
    for j, (title, l1, l2) in enumerate(boxes):
        xx = bx + j * (bw + 12)
        bh = (rh - 24) if i == 3 else h - 24
        out.append(f'<rect x="{xx:.1f}" y="{y + 12}" width="{bw:.1f}" height="{bh}" rx="6" fill="#FFFFFF" stroke="{color}" stroke-opacity="0.55"/>')
        cx = xx + bw / 2
        if n >= 7:   # two-line titles in the visualisation layer
            out.append(t(cx, y + 38, title, 13, 650, color, "middle"))
            out.append(t(cx, y + 56, l1, 13, 650, color, "middle"))
            out.append(t(cx, y + 80, l2, 11, 400, "#3A4449", "middle"))
        else:
            out.append(t(cx, y + 38, title, 14, 650, color, "middle"))
            out.append(t(cx, y + 60, l1, 12, 400, "#3A4449", "middle"))
            if l2:
                out.append(t(cx, y + 78, l2, 12, 400, "#6B7378", "middle"))
    if i == 3:
        out.append(f'<rect x="{bx}" y="{y + h - 4}" width="{bw_total}" height="0" />')
    if i < 5:
        ax = x0 + lw + cw / 2
        out.append(f'<line x1="{ax}" y1="{y + h + 2}" x2="{ax}" y2="{y + h + gap - 4}" stroke="#5A6B78" stroke-width="2" marker-end="url(#a)"/>')
    if i == 3:  # explainability band
        pass
    y += h + gap
# explainability strip overlay under detection layer
dy = 90 + 3 * (rh + gap)
out.append(f'<rect x="{x0 + lw + 16}" y="{dy + rh - 4}" width="{cw - 32}" height="28" rx="5" fill="#F3E3B5" stroke="#C99A2E"/>')
out.append(t(x0 + lw + cw / 2, dy + rh + 15, "Explainability: TreeSHAP on every alert (Isolation Forest) · LIME + KernelSHAP on the tabular ensemble · plain-language narrative  —  explain/xai.py, narrative.py", 12, 600, "#6B4E00", "middle"))
# cross-cutting column
cx0, cwid = x0 + lw + cw + 40, 220
out.append(f'<rect x="{cx0}" y="90" width="{cwid}" height="{y - 90 - gap}" rx="8" fill="#F4F6F8" stroke="#2C3E57"/>')
out.append(f'<rect x="{cx0}" y="90" width="{cwid}" height="46" rx="8" fill="#2C3E57"/>')
out.append(t(cx0 + cwid / 2, 119, "CROSS-CUTTING SERVICES", 14, 700, "#FFFFFF", "middle"))
yy = 152
for title, lines in CROSS:
    bh = 34 + 18 * len(lines)
    out.append(f'<rect x="{cx0 + 12}" y="{yy}" width="{cwid - 24}" height="{bh}" rx="6" fill="#FFFFFF" stroke="#9AA7B4"/>')
    out.append(t(cx0 + 24, yy + 22, title, 13, 650))
    for k, l in enumerate(lines):
        out.append(t(cx0 + 24, yy + 42 + 18 * k, "· " + l, 11.5, 400, "#3A4449"))
    yy += bh + 12
out.append(f'<line x1="{cx0}" y1="400" x2="{x0 + lw + cw + 4}" y2="400" stroke="#5A6B78" stroke-dasharray="5 4" stroke-width="1.4" marker-end="url(#a)"/>')
# deployment footer
fy = y - gap + 18
out.append(t(40, fy + 6, "Deployment: docker compose (TimescaleDB, Kafka, trainer, producer, consumer, API, dashboard, backup)  ·  "
             "dashboard demo mode on Streamlit Community Cloud  ·  design prototype on GitHub Pages", 12.5, 500, "#3A4449"))
out.append(t(40, fy + 26, "Solid arrows: data flow.  Dashed arrow: control / monitoring flow.  Detection layer boxes are the implemented models; "
             "Figure 1 components are all present.", 12, 400, "#6B7378"))
out.append("</svg>")
svg = "\n".join(out)
root = Path(__file__).resolve().parents[1] / "docs"
(root / "architecture.svg").write_text(svg)
import cairosvg  # noqa: E402
cairosvg.svg2png(bytestring=svg.encode(), write_to=str(root / "architecture.png"), output_width=W * 1.5)
print("written", root / "architecture.png", "height", H, "content ends", fy + 26)
