import os
import sys
import pandas as pd
from pyvis.network import Network

sys.stdout.reconfigure(encoding="utf-8")


def find_parent_code(code):
    """Kod sistemine göre bir kişinin ebeveyn kodunu bulur.

    Örnek: '2FDCB' -> '2FDC', '2A' -> '2', '2' -> '0'
    """
    if pd.isna(code) or str(code).strip() == "" or code == "0" or code == "0.0":
        return None

    # float dönüşümünden kaynaklı .0 varsa veya boşluk varsa temizle
    code = str(code).strip().split(".")[0]

    # Eğer kod 1 karakterliyse (örn: '2'), kök çift olan '0'a bağlanır
    if len(code) == 1:
        return "0"

    # Geçici kodlar için düzeltme (örn: '2FE-1')
    if "-" in code:
        return code.split("-")[0][:-1]

    # Standart hiyerarşi: Son karakteri düşürerek ebeveyni bul
    return code[:-1]


def generate_family_tree(excel_path, output_html="sulale_agaci.html"):
    # 1. Tek bir Excel dosyasından ilgili sayfaları (sekmeleri) oku
    try:
        df = pd.read_excel(excel_path, sheet_name="Sülale Listesi")
        df_cross = pd.read_excel(excel_path, sheet_name="Çapraz Akrabalıklar")
    except Exception as e:
        print(
            f"Hata: Excel dosyası veya sayfa isimleri ('Sülale Listesi', 'Çapraz Akrabalıklar') bulunamadı!\nDetay: {e}"
        )
        return

    # Kolon isimlerindeki olası gizli boşlukları temizle
    df.columns = df.columns.str.strip()
    df_cross.columns = df_cross.columns.str.strip()

    # Kod kolonunu metne çevir ve temizle
    df["Kod"] = df["Kod"].astype(str).str.strip()
    df["Ad"] = df["Ad"].fillna("Bilinmiyor")

    # 2. Pyvis Ağ Yapısını Oluştur
    net = Network(height="900px", width="100%", bgcolor="#f8f9fa", font_color="#343a40")

    # Pyvis'in yeni sürümleriyle tam uyumlu Yukarıdan Aşağıya (Hierarchical) Düzen Ayarları
    options = """
    {
      "layout": {
        "hierarchical": {
          "enabled": true,
          "direction": "UD",
          "sortMethod": "directed",
          "nodeSpacing": 180,
          "levelSeparation": 220
        }
      },
      "physics": {
        "enabled": true,
        "hierarchicalRepulsion": {
          "nodeDistance": 200
        }
      }
    }
    """
    net.set_options(options)

    # 3. Nesillere Göre Renk Paleti (Açıklama sayfandaki mantığa göre)
    color_map = {
        "Kök": "#2B2D42",  # Kök Çift (Eyyüp - Cihan)
        "Nesil 1": "#8D99AE",  # Çocuklar
        "Nesil 2": "#EF233C",  # Torunlar
        "Nesil 3": "#D90429",
        "Nesil 4": "#4EA8DE",
        "Nesil 5": "#48CAE4",
        "Nesil 6": "#90E0EF",
    }

    # 4a. Hangi kodların alt dalı (çocuğu) var — önceden hesapla
    ebeveyn_kodlari = set()
    for _, row in df.iterrows():
        code_tmp = str(row["Kod"]).strip().split(".")[0]
        if code_tmp == "nan" or not code_tmp:
            continue
        parent_tmp = find_parent_code(code_tmp)
        if parent_tmp:
            ebeveyn_kodlari.add(parent_tmp)

    # 4b. Düğümleri (Kişileri) Ekle
    for _, row in df.iterrows():
        code = str(row["Kod"]).strip().split(".")[0]
        if code == "nan" or not code:
            continue

        name = row["Ad"]
        spouse = (
            f" (Eşi: {row['Eş Adı']})"
            if "Eş Adı" in row and pd.notna(row["Eş Adı"]) and str(row["Eş Adı"]).strip() != ""
            else ""
        )
        gen = row["Nesil"] if "Nesil" in row and pd.notna(row["Nesil"]) else "Nesil Belirsiz"

        # Detaylar (Üzerine mouse ile gelince gözükecek kutu / Tooltip)
        # \\D kullanarak syntax uyarısını düzelttik
        dt = (
            f"\\nD.Tarihi: {row['Doğum Tarihi']}"
            if "Doğum Tarihi" in row and pd.notna(row["Doğum Tarihi"])
            else ""
        )
        notlar = (
            f"\\nNot: {row['Notlar / Çapraz Ref']}"
            if "Notlar / Çapraz Ref" in row and pd.notna(row["Notlar / Çapraz Ref"])
            else ""
        )

        has_children = code in ebeveyn_kodlari
        base_color   = color_map.get(str(gen).strip(), "#6c757d")

        # Nodes with children get a "▼" label suffix + bright white border.
        # Leaf nodes get a dimmed border so branch-points stand out at a glance.
        if has_children:
            label      = f"{name}{spouse} ▼"
            node_color = {
                "background": base_color,
                "border":     "#FFFFFF",
                "highlight":  {"background": base_color, "border": "#FFD700"},
            }
            border_w = 3
        else:
            label      = f"{name}{spouse}"
            node_color = {
                "background": base_color,
                "border":     base_color,   # blends in — leaf has no distinct border
                "highlight":  {"background": base_color, "border": "#FFD700"},
            }
            border_w = 1

        title = f"Kod: {code}\\nNesil: {gen}{dt}{notlar}"

        net.add_node(
            code, label=label, title=title,
            color=node_color, shape="box", borderWidth=border_w,
        )

    # 5. Ebeveyn-Çocuk Bağlantılarını Ekle
    for _, row in df.iterrows():
        code = str(row["Kod"]).strip().split(".")[0]
        if code == "nan" or not code:
            continue

        parent_code = find_parent_code(code)
        if parent_code and parent_code in net.get_nodes():
            net.add_edge(parent_code, code, arrows="to", color="#adb5bd")

    # 6. Çapraz Akrabalıkları (İç Evlilikleri) Kesikli Sarı Çizgiyle Ekle
    for _, row in df_cross.iterrows():
        p1 = str(row["Kişi 1 Kodu"]).strip().split(".")[0]
        p2 = str(row["Kişi 2 Kodu"]).strip().split(".")[0]

        if p1 in net.get_nodes() and p2 in net.get_nodes():
            desc = row["Açıklama"] if "Açıklama" in row else "Çapraz Akrabalık"
            net.add_edge(
                p1,
                p2,
                color="#ffb703",
                weight=2,
                style="dashed",
                title=f"Çapraz Evlilik: {desc}",
            )

    # 7. HTML Dosyası Olarak Kaydet
    net.write_html(output_html)
    print(f"\\n[BAŞARILI] Sülale ağacı oluşturuldu: '{output_html}'")
    print("Bu dosyayı çift tıklayarak tarayıcında interaktif olarak inceleyebilirsin.")


# Bilgisayarındaki Excel dosyasının tam adı
excel_file = "Demiralay_Sulalesi.xlsx"

if os.path.exists(excel_file):
    generate_family_tree(excel_file)
else:
    print(
        f"Hata: '{excel_file}' dosyası bulunamadı! Lütfen script ile aynı klasörde olduğundan emin olun."
    )