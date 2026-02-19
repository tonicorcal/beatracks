# Beatport Charts Viewer 🎵

Automated script for fetching and displaying Beatport charts with daily updates via GitHub Actions.

## 🎯 Live Demo

**https://tonicorcal.github.io/beatracks/**

> ⚠️ **DISCLAIMER**: This is a display-only demo for educational purposes. All data belongs to Beatport. Please support the artists by purchasing music through official channels.

## 🎮 How to Add Charts

Simply go to Actions and run the workflow with your desired chart URL:

```
┌─────────────────────────────────────────┐
│ Run workflow                            │
├─────────────────────────────────────────┤
│ Use workflow from: Branch: main         │
│                                         │
│ Beatport Chart URL                      │
│ ┌─────────────────────────────────────┐ │
│ │ https://www.beatport.com/chart/... │ │
│ └─────────────────────────────────────┘ │
│                                         │
│          [Run workflow]                 │
└─────────────────────────────────────────┘
```

## 📁 Project Structure

```
beatracks/
├── .github/
│   └── workflows/
│       └── update.yml          # GitHub Actions workflow
├── app.py                      # Main script
├── requirements.txt            # Python dependencies
├── beatport_links.db          # Database (auto-generated)
├── index.html                 # Output file (auto-generated)
└── README.md                   # This file
```

## 🚀 Installation & Usage

### Local Execution

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Run the script:
```bash
python app.py
```

3. Open the `index.html` file in your browser

### GitHub Actions Setup (Automatic Updates)

1. Upload all files to your GitHub repository

2. Ensure you have these files:
   - `.github/workflows/update.yml`
   - `app.py`
   - `requirements.txt`

3. Enable GitHub Actions:
   - Go to Settings → Actions → General
   - Select "Allow all actions and reusable workflows"

4. Grant write permissions to GitHub Actions:
   - Settings → Actions → General
   - Scroll to "Workflow permissions"
   - Select "Read and write permissions"
   - Save

5. Configure GitHub Pages:
   - Settings → Pages
   - Source: **GitHub Actions** (not "Deploy from a branch")
   - Save

6. The script will run automatically:
   - Daily at midnight (UTC)
   - Can be triggered manually via Actions → Update Beatport Tracks → Run workflow

## 📝 Adding New Charts

### Manual Execution (Recommended)

1. Go to **Actions** → **Update Beatport Tracks**
2. Click **Run workflow**
3. Enter your desired Beatport chart URL in the input field
4. Click **Run workflow** button

### Changing Default Chart

Edit the default URL in `.github/workflows/update.yml`:

```yaml
inputs:
  chart_url:
    description: 'Beatport Chart URL'
    default: 'https://www.beatport.com/chart/YOUR-CHART/123456'
```

## 🎨 Features

- ✅ Automatic fetching of Beatport charts
- ✅ Duplicate detection across charts
- ✅ Filters by genre, label, and date
- ✅ Track search functionality
- ✅ Album and label artwork display
- ✅ Automatic updates via GitHub Actions
- ✅ Automatic GitHub Pages deployment
- ✅ Manual chart URL input via workflow
- ✅ SQLite history storage

## 🔧 Key Changes from Local Version

1. **Relative Paths**: Using relative paths instead of absolute paths
2. **Timeout**: Added HTTP request timeout to prevent hanging
3. **GitHub Actions**: Full automation with automatic commit and push
4. **Auto-Deploy**: Automatic GitHub Pages deployment after each update
5. **Manual Input**: Add charts via workflow input without editing code

## 📊 How It Works

1. **Workflow runs** (scheduled or manual)
2. **Script fetches** chart data from Beatport
3. **Database updated** with new tracks (duplicates are marked)
4. **HTML generated** with all charts and tracks
5. **Changes committed** to repository
6. **GitHub Pages deployed** automatically
7. **Live site updated** at https://tonicorcal.github.io/beatracks/

## 🎯 Quick Start

1. Fork this repository
2. Enable GitHub Actions (Settings → Actions)
3. Enable GitHub Pages with "GitHub Actions" as source
4. Go to Actions → Run workflow → Enter chart URL
5. Wait 2-3 minutes
6. Visit your live site!

## 💡 Tips

- Chart URLs must be from beatport.com/chart/...
- Each run checks for duplicates automatically
- The database persists across runs
- You can run multiple charts by triggering the workflow multiple times
- Old charts remain in the database and HTML

## 🤖 Credits

This entire project was built by **Claude (Anthropic)** - from the Python script to the GitHub Actions workflow, HTML/CSS/JavaScript interface, and documentation. The repository owner doesn't know how to write a single line of code. All development, debugging, and optimization was done through conversational AI assistance.

**Powered by:** Claude Sonnet 4.5
