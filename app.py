import requests 
from bs4 import BeautifulSoup
import re
from html import escape
from datetime import datetime
import random
import sqlite3
import os
import threading
from concurrent.futures import ThreadPoolExecutor

# ============================
# File settings
# ============================
DB_FILE = "beatport_links.db"
OUTPUT_FILE = "index.html"

# ============================
# Date parsing function
# ============================
def parse_date_safe(text):
    if not text: return None
    for fmt in ("%Y-%m-%d", "%d.%m.%y", "%d/%m/%Y"):
        try: return datetime.strptime(text, fmt)
        except: continue
    return None

# ============================
# Create DB
# ============================
conn = sqlite3.connect(DB_FILE)
c = conn.cursor()
c.execute("""
CREATE TABLE IF NOT EXISTS weekly_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chart_name TEXT,
    chart_date_created TEXT,
    chart_image TEXT,
    artist TEXT,
    title TEXT,
    url TEXT,
    genre TEXT,
    label TEXT,
    label_img TEXT,
    artwork TEXT,
    release_dt TEXT,
    release_str TEXT,
    is_duplicate INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()
conn.close()

# ============================
# Function to check if chart already exists in DB
# ============================
def chart_already_exists(chart_name):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT 1 FROM weekly_links WHERE chart_name=? LIMIT 1", (chart_name,))
    exists = c.fetchone() is not None
    conn.close()
    return exists

# ============================
# Function to fetch creation date and chart image
# ============================
def get_chart_metadata(url):
    try:
        r = requests.get(url, headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        date_created = None
        info_divs = soup.find_all("div", class_=re.compile(r"ChartDetailCard-style__Info"))
        for div in info_divs:
            p_tag = div.find("p")
            if p_tag and "Date Created" in p_tag.text:
                span = div.find("span")
                if span:
                    date_created = span.text.strip()
                    break
        chart_image = ""
        image_wrapper = soup.find("div", class_=re.compile(r"ChartDetailCard-style__ImageWrapper"))
        if image_wrapper:
            img = image_wrapper.find("img")
            if img and img.get("src"):
                chart_image = img["src"]
        return date_created, chart_image
    except Exception as e:
        print(f"  ⚠️  Error fetching chart metadata: {e}")
        return None, ""

# ============================
# Label image cache + threading
# ============================
label_img_cache = {}
cache_lock = threading.Lock()

def get_label_img(label, label_href):
    with cache_lock:
        if label in label_img_cache:
            return label, label_img_cache[label]
    try:
        label_page = requests.get(
            "https://www.beatport.com" + label_href,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        label_soup = BeautifulSoup(label_page.text, "html.parser")
        img_tag = label_soup.find("img", alt=label)
        result = img_tag["src"].replace("87x87", "500x500") if img_tag else ""
    except:
        result = ""
    with cache_lock:
        label_img_cache[label] = result
    return label, result

# ============================
# Function to add to DB with duplicate marking
# ============================
def add_track_to_db(chart_name, chart_date_created, chart_image, artist, title, url, genre, label, label_img, artwork, release_dt, release_str):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("""
        SELECT 1 FROM weekly_links 
        WHERE chart_name=? AND artist=? AND title=?
    """, (chart_name, artist, title))
    if c.fetchone():
        conn.close()
        return 0
    c.execute("""
        SELECT chart_name FROM weekly_links 
        WHERE artist=? AND title=?
    """, (artist, title))
    existing = c.fetchall()
    is_dup = 1 if existing else 0
    c.execute("""
        INSERT INTO weekly_links 
        (chart_name, chart_date_created, chart_image, artist, title, url, genre, label, label_img, artwork, release_dt, release_str, is_duplicate)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        chart_name, chart_date_created, chart_image, artist, title, url, genre, label, label_img, artwork,
        release_dt.isoformat() if release_dt else "",
        release_str, is_dup
    ))
    conn.commit()
    conn.close()
    return 1

# ============================
# Fetch all tracks
# ============================
def get_all_links():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT chart_name, chart_date_created, chart_image, artist, title, url, genre, label, label_img, artwork, release_dt, release_str, is_duplicate FROM weekly_links")
    rows = c.fetchall()
    conn.close()
    return rows

# ============================
# Initial links
# ============================
chart_url = os.getenv('CHART_URL', 'https://www.beatport.com/chart/weekend-picks-2026-week-2/876342').strip()
input_links = [chart_url]

print(f"📋 Processing chart: {chart_url}")

# ============================
# Process links
# ============================
total_added = 0
total_skipped = 0

for url in input_links:
    match = re.search(r"/chart/(.+)/\d+$", url)
    chart_name = match.group(1).replace("-", " ").title() if match else url

    if chart_already_exists(chart_name):
        print(f"⏭️  Chart '{chart_name}' already exists in DB - skipping...")
        continue

    print(f"📀 Fetching chart metadata for '{chart_name}'...")
    chart_date_created, chart_image = get_chart_metadata(url)
    print(f"   Date: {chart_date_created}, Image: {'✓' if chart_image else '✗'}")

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    soup = BeautifulSoup(r.text, "html.parser")
    rows = soup.select("div[class*=TableRow]")
    total = len(rows)
    print(f"📀 Loading {total} tracks from {chart_name} ...")

    # שלב 1: איסוף כל הטראקים ללא תמונות לייבל
    tracks_data = []
    unique_labels = {}

    for idx, row in enumerate(rows, 1):
        row_title = row.select_one("div[class*=title] span")
        row_title = row_title.text.strip() if row_title else None

        artist_tags = row.select("div[class*=ArtistNames] a")
        row_artist = ", ".join(a.text.strip() for a in artist_tags) if artist_tags else None

        if not row_title or not row_artist: continue

        genre_div = row.select_one("div[class*=bpm] div")
        genre = genre_div.text.strip() if genre_div else "Unknown"

        label_div = row.find("div", class_=re.compile(r"Table-style__TableCell.*label"))
        label = label_div.find("a").text.strip() if label_div and label_div.find("a") else "Unknown"

        label_href = None
        if label != "Unknown" and label_div and label_div.find("a"):
            label_href = label_div.find("a")["href"]
            if label not in unique_labels:
                unique_labels[label] = label_href

        artwork_div = row.select_one("a.artwork img")
        artwork = artwork_div["src"].replace("95x95", "500x500") if artwork_div else ""

        date_div = row.select_one("div[class*=cell][class*=date]")
        release_dt = parse_date_safe(date_div.text.strip()) if date_div else None
        release_str = date_div.text.strip() if date_div else "NONE"

        tracks_data.append({
            "artist": row_artist,
            "title": row_title,
            "genre": genre,
            "label": label,
            "artwork": artwork,
            "release_dt": release_dt,
            "release_str": release_str,
        })

        progress = int(idx / total * 30)
        bar = "█" * progress + "-" * (30 - progress)
        print(f"\r[{bar}] {idx}/{total} tracks parsed", end="", flush=True)
    print()

    # שלב 2: שליפת תמונות לייבל במקביל
    print(f"🎨 Fetching {len(unique_labels)} unique label images in parallel...")
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = executor.map(lambda item: get_label_img(item[0], item[1]), unique_labels.items())
        for label_name, label_img_url in futures:
            label_img_cache[label_name] = label_img_url
    print(f"   ✓ Label images done")

    # שלב 3: הוספה ל-DB
    for t in tracks_data:
        label_img = label_img_cache.get(t["label"], "")
        added = add_track_to_db(
            chart_name, chart_date_created, chart_image,
            t["artist"], t["title"], url,
            t["genre"], t["label"], label_img,
            t["artwork"], t["release_dt"], t["release_str"]
        )
        if added:
            total_added += 1
        else:
            total_skipped += 1

print(f"✅ DB updated. Added: {total_added}, Skipped: {total_skipped}")

# ============================
# Prepare HTML data by chart
# ============================
charts = {}
genres = set()
labels = set()
label_images = {}
track_duplicates = {}

for row in get_all_links():
    chart_name, chart_date_created, chart_image, artist, title, url, genre, label, label_img, artwork, release_dt_str, release_str, is_dup = row
    release_dt = datetime.fromisoformat(release_dt_str) if release_dt_str else None
    track = {
        "artist": artist,
        "title": title,
        "genre": genre,
        "label": label,
        "label_img": label_img,
        "artwork": artwork,
        "release_dt": release_dt,
        "release_str": release_str,
        "is_duplicate": is_dup,
        "chart": chart_name
    }
    key = f"{artist}|{title}"
    if key not in track_duplicates: track_duplicates[key] = []
    track_duplicates[key].append(chart_name)

    if chart_name not in charts:
        charts[chart_name] = {"date": chart_date_created, "image": chart_image, "tracks": []}
    charts[chart_name]["tracks"].append(track)
    genres.add(genre)
    labels.add(label)
    if label not in label_images: label_images[label] = label_img

genre_colors = {g: f"rgb({random.randint(140,255)},{random.randint(140,255)},{random.randint(140,255)})" for g in genres}
label_colors = {l: f"rgb({random.randint(140,255)},{random.randint(140,255)},{random.randint(140,255)})" for l in labels}

# ============================
# Sort charts by date: newest on top
# ============================
def get_chart_sort_date(chart_data):
    date_str = chart_data[1]["date"]
    if date_str:
        try: return datetime.strptime(date_str, "%Y-%m-%d")
        except: pass
    return datetime.min

sorted_charts = sorted(charts.items(), key=get_chart_sort_date, reverse=True)

# ============================
# HTML
# ============================
html = []
html.append(f"""
<!DOCTYPE html>
<html lang="en">
<meta charset="UTF-8">
<title>Beatport Tracks</title>
<style>
body {{margin:0;background:#000;color:#ccc;font-family:Consolas;}}
#layout {{display:flex;}}
#genre-sidebar {{ width:180px; background:#050505; border-right:1px solid #222; padding:10px; box-sizing:border-box; }}
#genre-sidebar h3 {{margin-top:0;color:#ffd;font-size:14px;}}
.genre-filter {{ display:block; margin-bottom:6px; padding:4px 6px; border-radius:6px; cursor:pointer; font-weight:bold; color:#000; }}
.genre-filter.active {{outline:2px solid #fff;}}
#content {{padding:10px; flex:1;}}
#expand-collapse-btn {{ margin-bottom:10px; padding:6px 12px; background:#222; color:#ff0; border:none; cursor:pointer; font-weight:bold; }}
.track {{padding:4px;}}
.track:hover {{background:#111;}}
.hidden {{display:none;}}
.duplicate {{background:yellow;color:#000; padding:0 3px; border-radius:3px; margin-left:5px; cursor:pointer;}}
.song-line {{display:flex; width:100%; justify-content:flex-start; align-items:center;}}
.track-left {{display:flex; align-items:center; gap:5px; flex-wrap: wrap;}}
.date-tag {{padding:2px 6px; border-radius:5px; background:#666; font-weight:bold; color:#d0d0d0; margin-right:5px; cursor:pointer; flex-shrink:0;}}
.genre-tag {{padding:2px 6px; border-radius:5px; color:#000; font-weight:bold; cursor:pointer; flex-shrink:0;}}
.label-tag {{padding:2px 6px; border-radius:5px; color:#000; font-weight:bold; margin-left:5px; flex-shrink:0; cursor:pointer;}}
.label-tag:hover {{outline:2px solid #fff;}}
.track-title {{cursor:pointer; flex: none; overflow: hidden; text-overflow: ellipsis;}}
.artwork-box {{max-height:0; overflow:hidden; transition:max-height .3s ease; margin-left:0; display:flex; gap:10px;}}
.track.expanded .artwork-box {{max-height:420px;}}
.artwork-box img {{width:400px;height:400px; object-fit:cover;}}
.artwork-box img.label-img {{width:400px;height:400px; object-fit:cover;}}
.hover-preview {{position:fixed; z-index:10000; pointer-events:none; border:3px solid #ff0; box-shadow:0 0 20px rgba(255,255,0,0.5);}}
.hover-preview img {{display:block; max-width:none; max-height:none;}}
#search-bar input {{width:50%; padding:6px; font-size:16px; background:#000; color:#fff; border:1px solid #555;}}
.chart-header {{ background:#111; color:#ff0; font-weight:bold; padding:6px; cursor:pointer; margin-bottom:2px; border-radius:4px; display:flex; align-items:center; gap:8px; }}
.chart-header img {{ width:40px; height:40px; border-radius:4px; object-fit:cover; }}
.chart-header-text {{ flex:1; }}
.chart-date {{ color:#999; font-size:12px; font-weight:normal; margin-left:10px; }}
.chart-content {{ max-height:0; overflow:hidden; transition:max-height .3s ease; }}
.chart-block.expanded .chart-content {{ max-height:5000px; }}
.dup-tooltip {{position:fixed; background:#ff0; color:#000; padding:2px 6px; border-radius:4px; font-weight:bold; pointer-events:none; z-index:9999;}}
</style>
<body>

<div id="search-bar">
  <input type="text" id="search-input" placeholder="Search artist, track or label...">
</div>

<button id="expand-collapse-btn">Expand All / Collapse All</button>
<div id="track-count">Tracks: {sum(len(v['tracks']) for v in charts.values())}</div>

<div id="layout">
  <div id="genre-sidebar">
    <h3>Genres</h3>
""")

for g in sorted(genres):
    html.append(f'<span class="genre-filter" style="background:{genre_colors[g]}" data-genre="{escape(g)}">[{escape(g)}]</span>')

html.append("</div>")
html.append("<div id='content'>")

for chart_name, chart_data in sorted_charts:
    chart_image = chart_data["image"]
    chart_date = chart_data["date"] if chart_data["date"] else ""

    if chart_date:
        try:
            dt = datetime.strptime(chart_date, "%Y-%m-%d")
            chart_date_formatted = dt.strftime("[%d|%m|%y]")
        except:
            chart_date_formatted = f"({chart_date})"
    else:
        chart_date_formatted = ""

    chart_tracks = chart_data["tracks"]
    img_html = f'<img src="{escape(chart_image)}" alt="{escape(chart_name)}">' if chart_image else ''
    date_html = f'<span class="chart-date">{chart_date_formatted}</span>' if chart_date_formatted else ''

    html.append('<div class="chart-block">')
    html.append(f'<div class="chart-header">{img_html}<div class="chart-header-text">📀 {escape(chart_name)} {date_html}</div></div>')
    html.append('<div class="chart-content">')

    for t in chart_tracks:
        release_str = t['release_str'] if t['release_str'] else "NONE"
        release_data_attr = t['release_dt'].strftime('%Y-%m-%d') if t['release_dt'] else ""
        dup_html = '<span class="duplicate">⚠️</span>' if t['is_duplicate'] else ''
        all_charts_str = '|'.join(track_duplicates[f"{t['artist']}|{t['title']}"])
        html.append(f"""
<div class="track"
 data-chart="{escape(t['chart'])}"
 data-all-charts="{escape(all_charts_str)}"
 data-genre="{escape(t['genre'])}"
 data-label="{escape(t['label'])}"
 data-artist="{escape(t['artist'])}"
 data-title="{escape(t['title'])}"
 data-date="{release_data_attr}"
 data-artwork="{escape(t['artwork'])}"
 data-label-artwork="{escape(t.get('label_img',''))}">
 <div class="song-line">
  <div class="track-left">
    <span class="date-tag">{release_str}</span>
    <span class="genre-tag" style="background:{genre_colors[t['genre']]}">[{escape(t['genre'])}]</span>
    <span class="track-title">{escape(t['artist'])} – {escape(t['title'])}</span>
    <span class="label-tag" style="background:{label_colors[t['label']]}">[{escape(t['label'])}]</span>
    {dup_html}
  </div>
 </div>
 <div class="artwork-box"></div>
</div>
""")

    html.append('</div></div>')

html.append("</div></div>")

html.append("""
<script>
let activeGenre=null;
let activeLabel=null;
let activeDate=null;

function updateTrackCount(){
  const visible=document.querySelectorAll('.track:not(.hidden)').length;
  document.getElementById('track-count').textContent="Tracks: "+visible;
}

function applyFilters(){
  document.querySelectorAll('.track').forEach(t=>{
    let hide=false;
    if(activeGenre && t.dataset.genre!==activeGenre) hide=true;
    if(activeLabel && t.dataset.label!==activeLabel) hide=true;
    if(activeDate && t.dataset.date!==activeDate) hide=true;
    t.classList.toggle('hidden',hide);
  });
  updateTrackCount();
}

document.querySelectorAll('.genre-filter').forEach(tag=>{
  tag.addEventListener('click', ()=>{
    const g = tag.dataset.genre;
    document.querySelectorAll('.genre-filter').forEach(t=>t.classList.remove('active'));
    if(activeGenre===g){ activeGenre=null; } else { activeGenre=g; tag.classList.add('active'); }
    applyFilters();
  });
});

document.querySelectorAll('.genre-tag').forEach(tag=>{
  tag.addEventListener('click',e=>{
    e.stopPropagation();
    const g = tag.textContent.replace(/[\[\]]/g,'');
    activeGenre = (activeGenre===g)?null:g;
    applyFilters();
  });
});

document.querySelectorAll('.label-tag').forEach(tag=>{
  tag.addEventListener('click',e=>{
    e.stopPropagation();
    const l = tag.textContent.replace(/[\[\]]/g,'');
    document.querySelectorAll('.label-tag').forEach(t=>t.classList.remove('active-label'));
    if(activeLabel===l){ activeLabel=null; }
    else { activeLabel=l; tag.classList.add('active-label'); }
    applyFilters();
  });
});

document.querySelectorAll('.date-tag').forEach(tag=>{
  tag.addEventListener('click',e=>{
    e.stopPropagation();
    const parent=tag.closest('.track');
    const dateStr=parent.dataset.date;
    activeDate = (activeDate===dateStr)?null:dateStr;
    applyFilters();
  });
});

document.querySelectorAll('.track-title').forEach(title=>{
  title.addEventListener('click',()=>{
    const track = title.closest('.track');
    const box = track.querySelector('.artwork-box');
    document.querySelectorAll('.track.expanded').forEach(t=>{
        if(t !== track){ t.classList.remove('expanded'); t.querySelector('.artwork-box').innerHTML=''; }
    });
    if(track.classList.contains('expanded')){ track.classList.remove('expanded'); box.innerHTML=''; return; }
    const artHTML = track.dataset.artwork ? `<img src="${track.dataset.artwork}">` : '';
    const labelHTML = track.dataset.labelArtwork ? `<img class="label-img" src="${track.dataset.labelArtwork}">` : '';
    if(artHTML || labelHTML) box.innerHTML = artHTML + labelHTML;
    track.classList.add('expanded');
  });
});

const searchInput = document.getElementById('search-input');
searchInput.addEventListener('input', ()=>{
    const term = searchInput.value.toLowerCase();
    document.querySelectorAll('.track').forEach(t=>{
        let hide=false;
        const text = (t.dataset.artist+" "+t.dataset.title+" "+t.dataset.label).toLowerCase();
        if(term && !text.includes(term)) hide=true;
        if(activeGenre && t.dataset.genre!==activeGenre) hide=true;
        if(activeLabel && t.dataset.label!==activeLabel) hide=true;
        if(activeDate && t.dataset.date!==activeDate) hide=true;
        t.classList.toggle('hidden',hide);
    });
    updateTrackCount();
});

document.querySelectorAll('.chart-header').forEach(h=>{
    h.addEventListener('click', ()=>{ h.parentElement.classList.toggle('expanded'); });
});

document.getElementById('expand-collapse-btn').addEventListener('click', ()=>{
    document.querySelectorAll('.chart-block').forEach(c=>{ c.classList.toggle('expanded'); });
});

document.querySelectorAll('.duplicate').forEach(icon=>{
    let tooltip;
    icon.addEventListener('mouseenter', e=>{
        const track = icon.closest('.track');
        const allCharts = track.dataset.allCharts.split('|');
        const currentChart = track.dataset.chart;
        const otherCharts = allCharts.filter(c => c !== currentChart);
        if(otherCharts.length===0) return;
        tooltip = document.createElement('div');
        tooltip.className = 'dup-tooltip';
        tooltip.textContent = otherCharts.join(', ');
        document.body.appendChild(tooltip);
        tooltip.style.left = e.clientX + 10 + 'px';
        tooltip.style.top = e.clientY + 10 + 'px';
    });
    icon.addEventListener('mousemove', e=>{
        if(tooltip){ tooltip.style.left = e.clientX + 10 + 'px'; tooltip.style.top = e.clientY + 10 + 'px'; }
    });
    icon.addEventListener('mouseleave', ()=>{ if(tooltip) tooltip.remove(); });
});

document.querySelectorAll('.chart-header img').forEach(img=>{
    let preview;
    img.addEventListener('mouseenter', e=>{
        if(!img.src) return;
        preview = document.createElement('div');
        preview.className = 'hover-preview';
        const previewImg = document.createElement('img');
        previewImg.src = img.src;
        preview.appendChild(previewImg);
        document.body.appendChild(preview);
        preview.style.left = e.clientX + 20 + 'px';
        preview.style.top = e.clientY + 20 + 'px';
    });
    img.addEventListener('mousemove', e=>{
        if(preview){ preview.style.left = e.clientX + 20 + 'px'; preview.style.top = e.clientY + 20 + 'px'; }
    });
    img.addEventListener('mouseleave', ()=>{ if(preview) preview.remove(); });
});
</script>
</body>
</html>
""")

# ============================
# Save HTML
# ============================
with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write("".join(html))

print(f"✅ HTML file saved to {OUTPUT_FILE}")
