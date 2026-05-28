import os
import sys
import math
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import networkx as nx
import pandas as pd


def find_parent_code(code):
    if pd.isna(code) or str(code).strip() == "" or code in ("0", "0.0"):
        return None
    code = str(code).strip().split(".")[0]
    if len(code) == 1:
        return "0"
    if "-" in code:
        return code.split("-")[0][:-1]
    return code[:-1]


GEN_STYLE = {
    "Kök":     {"face": "#2B2D42", "text": "#FFFFFF"},
    "Nesil 1": {"face": "#4A5568", "text": "#FFFFFF"},
    "Nesil 2": {"face": "#C53030", "text": "#FFFFFF"},
    "Nesil 3": {"face": "#9C4221", "text": "#FFFFFF"},
    "Nesil 4": {"face": "#2B6CB0", "text": "#FFFFFF"},
    "Nesil 5": {"face": "#276749", "text": "#FFFFFF"},
    "Nesil 6": {"face": "#234E52", "text": "#E6FFFA"},
}
_DEFAULT_STYLE = {"face": "#718096", "text": "#FFFFFF"}

# Each depth band uses two lanes (inner / outer) so nodes alternate radially
# instead of sitting on a single ring. This doubles angular capacity and
# fills the space between bands with content instead of blank arcs.
LANE_DELTA = 4.0  # radial offset  ±  from the band centre-line
FIG_SIZE   = 70   # must match figsize(= used below for node-size estimates
NUDGE_GAP  = 0.6  # minimum empty space between node boxes after nudging


def _font_size(depth):
    return 20.0 if depth == 0 else max(12.5, 18.0 - depth * 0.8)


def _node_size_du(label, depth, data_range):
    """Estimate node bounding-box (width, height) in data units."""
    fs = _font_size(depth)
    lines = label.split("\n")
    max_chars = max(len(l) for l in lines)
    n_lines   = len(lines)
    du_per_in = data_range / FIG_SIZE        # data-units per inch
    char_w    = fs / 72.0 * 0.60 * du_per_in
    line_h    = fs / 72.0 * 1.50 * du_per_in
    pad       = 0.65 * fs / 72.0 * du_per_in  # matches boxstyle pad=0.65
    return (max_chars * char_w + 2 * pad,
            n_lines   * line_h * 1.3 + 2 * pad)


def _nudge(pos, sizes, gap=NUDGE_GAP, n_iter=60):
    """
    Minimum-translation-vector collision pass.
    Each iteration finds every overlapping pair and pushes them apart
    along whichever axis requires the smaller displacement.
    Runs until no overlaps remain or n_iter is exhausted.
    """
    nodes = list(pos.keys())
    for _ in range(n_iter):
        moved = False
        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                a, b = nodes[i], nodes[j]
                ax_, ay_ = pos[a]
                bx,  by  = pos[b]
                wa, ha   = sizes[a]
                wb, hb   = sizes[b]

                ov_x = (wa + wb) / 2 + gap - abs(ax_ - bx)
                ov_y = (ha + hb) / 2 + gap - abs(ay_ - by)

                if ov_x <= 0 or ov_y <= 0:
                    continue            # no overlap on this pair

                moved = True
                if ov_x <= ov_y:       # cheaper to separate along x
                    shift = ov_x / 2 + 0.05
                    sign  = 1 if ax_ >= bx else -1
                    pos[a] = (ax_ + sign * shift, ay_)
                    pos[b] = (bx  - sign * shift, by)
                else:                   # cheaper to separate along y
                    shift = ov_y / 2 + 0.05
                    sign  = 1 if ay_ >= by else -1
                    pos[a] = (ax_, ay_ + sign * shift)
                    pos[b] = (bx,  by  - sign * shift)
        if not moved:
            break
    return pos


def _leaf_count(G, node):
    children = list(G.successors(node))
    return 1 if not children else sum(_leaf_count(G, c) for c in children)


def generate_family_tree_v3(
    excel_path,
    out_png="sulale_agaci_v3.png",
    out_pdf="sulale_agaci_v3.pdf",
):
    # ── 1. Load data ──────────────────────────────────────────────────────
    try:
        df = pd.read_excel(excel_path, sheet_name="Sülale Listesi")
        df_cross = pd.read_excel(excel_path, sheet_name="Çapraz Akrabalıklar")
    except Exception as e:
        print(f"Hata: {e}")
        return

    df.columns = df.columns.str.strip()
    df_cross.columns = df_cross.columns.str.strip()
    df["Kod"] = df["Kod"].astype(str).str.strip()
    df["Ad"] = df["Ad"].fillna("Bilinmiyor")

    # ── 2. Build graph ────────────────────────────────────────────────────
    G = nx.DiGraph()
    node_info = {}

    for _, row in df.iterrows():
        code = str(row["Kod"]).strip().split(".")[0]
        if code == "nan" or not code:
            continue
        name = str(row["Ad"])
        spouse = (
            f"\n({row['Eş Adı']})"
            if "Eş Adı" in row
            and pd.notna(row["Eş Adı"])
            and str(row["Eş Adı"]).strip()
            else ""
        )
        gen = (
            str(row["Nesil"]).strip()
            if "Nesil" in row and pd.notna(row["Nesil"])
            else ""
        )
        G.add_node(code)
        node_info[code] = {
            "label": f"{name}{spouse}",
            "style": GEN_STYLE.get(gen, _DEFAULT_STYLE),
        }

    for _, row in df.iterrows():
        code = str(row["Kod"]).strip().split(".")[0]
        if code == "nan" or not code:
            continue
        parent = find_parent_code(code)
        if parent and parent in G and code in G:
            G.add_edge(parent, code)

    cross_edges = []
    for _, row in df_cross.iterrows():
        p1 = str(row["Kişi 1 Kodu"]).strip().split(".")[0]
        p2 = str(row["Kişi 2 Kodu"]).strip().split(".")[0]
        if p1 in G and p2 in G:
            cross_edges.append((p1, p2))

    # ── 3. BFS depths ─────────────────────────────────────────────────────
    root = "0"
    depth_of = {root: 0}
    queue = [root]
    level_n = {0: 1}
    max_d = 0
    while queue:
        node = queue.pop(0)
        for child in G.successors(node):
            if child not in depth_of:
                d = depth_of[node] + 1
                depth_of[child] = d
                level_n[d] = level_n.get(d, 0) + 1
                max_d = max(max_d, d)
                queue.append(child)

    # ── 4. Band-centre radii ──────────────────────────────────────────────
    # With dual-lane staggering each band holds ~2x nodes, so the
    # arc-length criterion uses half the nodes per effective lane.
    # min_gap must clear both lanes of the inner band (2*LANE_DELTA) plus
    # breathing room between bands.
    depth_radii = {0: 0.0}
    MIN_ARC = 6.0   # arc-length reserved per node per lane
    MIN_GAP = 14.0  # centre-to-centre distance between adjacent bands
    for d in range(1, max_d + 1):
        n = level_n.get(d, 1)
        # outer lane (larger circumference) is the bottleneck
        n_per_lane = math.ceil(n / 2)
        r_outer_lane = (n_per_lane * MIN_ARC) / (2 * math.pi)
        r_by_count = max(0.0, r_outer_lane - LANE_DELTA)   # band centre
        r_by_gap = depth_radii[d - 1] + MIN_GAP
        depth_radii[d] = max(r_by_count, r_by_gap)

    # ── 5. Two-step layout: angles → staggered radii ──────────────────────
    angle_of = {}  # node → centre angle

    def _assign_angles(node, a0, a1, depth):
        angle_of[node] = ((a0 + a1) / 2.0, depth)
        children = list(G.successors(node))
        if not children:
            return
        total = sum(_leaf_count(G, c) for c in children)
        cur = a0
        for child in children:
            span = (_leaf_count(G, child) / total) * (a1 - a0)
            _assign_angles(child, cur, cur + span, depth + 1)
            cur += span

    if root in G:
        _assign_angles(root, 0.0, 2 * math.pi, 0)

    # Group and sort by angle within each depth
    depth_buckets = defaultdict(list)
    for node, (angle, depth) in angle_of.items():
        depth_buckets[depth].append((node, angle))
    for depth in depth_buckets:
        depth_buckets[depth].sort(key=lambda x: x[1])

    # Place nodes: even-index → inner lane, odd-index → outer lane
    pos = {}
    for depth, node_angles in depth_buckets.items():
        if depth == 0:
            pos[node_angles[0][0]] = (0.0, 0.0)
            continue
        r_base = depth_radii[depth]
        for i, (node, angle) in enumerate(node_angles):
            r = (r_base - LANE_DELTA) if i % 2 == 0 else (r_base + LANE_DELTA)
            pos[node] = (r * math.cos(angle), r * math.sin(angle))

    for node in G:
        if node not in pos:
            pos[node] = (0.0, 0.0)

    # ── 6. Collision-nudge pass ───────────────────────────────────────────
    # Estimate data range before nudging to get node sizes in data units.
    pre_outer_r  = depth_radii[max_d] + LANE_DELTA
    est_range    = 2 * (pre_outer_r * 1.10 + 8)
    node_sizes   = {
        node: _node_size_du(node_info[node]["label"], depth_of.get(node, 0), est_range)
        for node in pos
        if node in node_info
    }
    for node in pos:                   # fallback for label-less nodes
        if node not in node_sizes:
            node_sizes[node] = (1.0, 0.5)

    print("  Çakışma giderme hesaplanıyor…")
    pos = _nudge(pos, node_sizes)
    print("  Tamamlandı.")

    # ── 7. Render ─────────────────────────────────────────────────────────
    BG = "#FAFAF8"
    fig, ax = plt.subplots(figsize=(70, 70), facecolor=BG)
    ax.set_facecolor(BG)
    ax.set_aspect("equal")
    ax.axis("off")

    # Use actual max radius after nudging (nudge may push nodes outward)
    outer_r = max(math.sqrt(x**2 + y**2) for x, y in pos.values()) + 3.0
    pad = outer_r * 0.08 + 7

    # Faint guide arcs — one pair per band (inner + outer lane edge)
    for d in range(1, max_d + 1):
        for dr in (-LANE_DELTA, LANE_DELTA):
            ax.add_patch(plt.Circle(
                (0, 0), depth_radii[d] + dr,
                fill=False, color="#DCDCDC", lw=0.3,
                linestyle=":", alpha=0.5, zorder=0,
            ))

    # Tree edges — tapered by depth
    for src, dst in G.edges():
        if src not in pos or dst not in pos:
            continue
        d_src = depth_of.get(src, 0)
        lw = max(0.6, 2.4 - d_src * 0.30)
        ax.plot(
            [pos[src][0], pos[dst][0]],
            [pos[src][1], pos[dst][1]],
            color="#C4C4C4", lw=lw, alpha=0.75, zorder=1,
        )

    # Cross-marriage edges — curved amber dashes
    for p1, p2 in cross_edges:
        if p1 not in pos or p2 not in pos:
            continue
        ax.annotate(
            "", xy=pos[p2], xytext=pos[p1],
            arrowprops=dict(
                arrowstyle="-",
                color="#F6AE2D",
                lw=3.0,
                linestyle="dashed",
                connectionstyle="arc3,rad=0.3",
            ),
            zorder=2,
        )

    # Nodes — font size is large and barely decreases with depth
    for node, (x, y) in pos.items():
        if node not in node_info:
            continue
        d = depth_of.get(node, 0)
        style = node_info[node]["style"]

        fs = _font_size(d)
        fw = "bold" if d <= 1 else "normal"

        ax.text(
            x, y,
            node_info[node]["label"],
            ha="center", va="center",
            fontsize=fs, fontweight=fw,
            color=style["text"],
            multialignment="center",
            linespacing=1.3,
            zorder=3,
            bbox=dict(
                boxstyle="round,pad=0.65",
                facecolor=style["face"],
                edgecolor="#F6AE2D" if d == 0 else "#FFFFFF",
                linewidth=4.0 if d == 0 else 1.0,
                alpha=0.95,
            ),
        )

    # Legend
    legend_items = [
        mpatches.Patch(facecolor=v["face"], edgecolor="#BBBBBB", lw=0.5, label=k)
        for k, v in GEN_STYLE.items()
    ]
    legend_items.append(
        mlines.Line2D([], [], color="#F6AE2D", lw=2.5,
                      linestyle="dashed", label="Çapraz Evlilik")
    )
    ax.legend(
        handles=legend_items,
        title="Açıklama",
        title_fontsize=15,
        fontsize=14,
        framealpha=0.97,
        facecolor="white",
        edgecolor="#BBBBBB",
        loc="lower right",
        borderpad=1.4,
    )

    # Title
    ax.text(
        0, outer_r + 5,
        "Demiralay Sülalesi — Şecere Haritası",
        ha="center", va="bottom",
        fontsize=28, fontweight="bold",
        color="#2B2D42",
    )

    ax.set_xlim(-(outer_r + pad), outer_r + pad)
    ax.set_ylim(-(outer_r + pad), outer_r + pad + 10)

    # ── 7. Save ───────────────────────────────────────────────────────────
    plt.savefig(out_png, dpi=150, bbox_inches="tight", facecolor=BG)
    print(f"  PNG: {out_png}")
    plt.savefig(out_pdf, bbox_inches="tight", facecolor=BG)
    print(f"  PDF: {out_pdf}")
    plt.close()

    print("\n[BAŞARILI] Şecere haritası oluşturuldu.")
    print("  PNG — ekran / web için")
    print("  PDF — baskı için (vektörel, herhangi bir boyutta kesiksiz yazdırabilirsiniz)")


excel_file = "Demiralay_Sulalesi.xlsx"

if os.path.exists(excel_file):
    generate_family_tree_v3(excel_file)
else:
    print(f"Hata: '{excel_file}' dosyası bulunamadı!")
