# Market Dashboard — Setup Guide

Follow these steps in order. Each step only needs to be done once.

---

## Step 1 — Install Python

1. Go to https://www.python.org/downloads/ and download the latest Python 3.x installer.
2. Run the installer. **Important:** tick the box "Add Python to PATH" before clicking Install.
3. Open **Command Prompt** (search "cmd" in Start menu) and type:
   ```
   python --version
   ```
   You should see something like `Python 3.12.x`. If you do, Python is ready.

---

## Step 2 — Install required packages

1. Open **Command Prompt**.
2. Navigate to the dashboard folder:
   ```
   cd "C:\Users\USER\OneDrive\Claude work\market-dashboard"
   ```
3. Install packages:
   ```
   pip install -r requirements.txt
   ```
   This takes 1-2 minutes. You only need to do this once.

---

## Step 3 — Set up Google Cloud credentials

This allows the app to read your private Relative Strength Google Sheet.

### 3a. Create a Google Cloud project

1. Go to https://console.cloud.google.com/
2. Click the project dropdown at the top → **New Project**.
3. Name it `market-dashboard` and click **Create**.

### 3b. Enable the Google Sheets API

1. In the left menu go to **APIs & Services → Library**.
2. Search for **Google Sheets API** and click it.
3. Click **Enable**.

### 3c. Create a Service Account

1. Go to **APIs & Services → Credentials**.
2. Click **+ Create Credentials → Service Account**.
3. Name it `market-dashboard-reader` and click **Create and Continue**.
4. Skip the optional role step — click **Continue**, then **Done**.

### 3d. Download the JSON key file

1. On the Credentials page, click your new service account.
2. Go to the **Keys** tab.
3. Click **Add Key → Create new key → JSON → Create**.
4. A file downloads automatically (e.g. `market-dashboard-reader-xxxx.json`).
5. Rename it to `service_account.json`.
6. Move it into the `credentials` folder:
   ```
   C:\Users\USER\OneDrive\Claude work\market-dashboard\credentials\service_account.json
   ```

### 3e. Share your Relative Strength sheet with the service account

1. Open the downloaded `service_account.json` in Notepad.
2. Find the line `"client_email"` — copy that email address (it looks like `market-dashboard-reader@...iam.gserviceaccount.com`).
3. Open your Relative Strength Google Sheet.
4. Click **Share** (top right).
5. Paste the service account email and set permission to **Viewer**.
6. Click **Share**.

---

## Step 4 — Fetch data for the first time

In **Command Prompt**, run:
```
cd "C:\Users\USER\OneDrive\Claude work\market-dashboard"
python fetch_data.py
```

You should see:
```
=== Market Dashboard Data Fetch — 2026-04-25 16:30 ===

Fetching Stockbee Market Monitor...
  Stockbee: 500 rows saved.
Fetching Relative Strength sheet...
  Relative Strength: 200 rows saved.

All data fetched successfully.
```

If you see errors, re-check Step 3 (credentials and sharing).

---

## Step 5 — Launch the dashboard

```
cd "C:\Users\USER\OneDrive\Claude work\market-dashboard"
streamlit run dashboard.py
```

Your browser will open automatically at `http://localhost:8501`.

---

## Step 6 — Automate daily data fetch (Windows Task Scheduler)

Set this up once so data is refreshed automatically every weekday at 4:30 PM.

1. Open **Task Scheduler** (search in Start menu).
2. Click **Create Basic Task** (right panel).
3. Name: `Market Dashboard Fetch` → Next.
4. Trigger: **Daily** → Next.
5. Start time: `4:30 PM` → Next.
6. Action: **Start a program** → Next.
7. Fill in:
   - **Program/script:** `python`
   - **Add arguments:** `fetch_data.py`
   - **Start in:** `C:\Users\USER\OneDrive\Claude work\market-dashboard`
8. Click **Finish**.
9. Right-click the new task → **Properties → Conditions** tab → untick "Start only if computer is on AC power" (optional but useful for laptops).

To run only on weekdays:
- Right-click the task → **Properties → Triggers** tab → Edit trigger.
- Under **Advanced settings**, tick **Repeat task every** and adjust if needed.
- Alternatively: right-click → Properties → Triggers → set "On these days: Mon, Tue, Wed, Thu, Fri".

---

## Daily usage

1. Data fetches automatically at 4:30 PM on weekdays.
2. To view the dashboard, open **Command Prompt** and run:
   ```
   cd "C:\Users\USER\OneDrive\Claude work\market-dashboard"
   streamlit run dashboard.py
   ```
3. You can also click **Refresh Now** inside the dashboard to re-fetch on demand.

---

## Folder structure

```
market-dashboard/
├── dashboard.py              Main dashboard app
├── fetch_data.py             Data fetcher script
├── config.py                 Sheet IDs and thresholds
├── requirements.txt          Python packages
├── credentials/
│   └── service_account.json  Your Google API key (keep private)
└── data/
    ├── stockbee.json          Cached Stockbee data
    ├── relative_strength.json Cached RS data
    └── last_updated.json      Last fetch timestamp
```
