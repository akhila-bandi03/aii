# 🛍️ DukaanSaathi AI
### Smart Voice-Based Kirana & Shop Management for Bharat 🇮🇳

> Built for **The Great Indian AI Internship Challenge** by [Gnani.ai](https://gnani.ai)  
> Tags: `#GnaniAI` `#GreatIndianAIInternshipChallenge`

---

## 🌟 Overview
In India, millions of local **kirana (grocery) store owners** in Tier 2 and Tier 3 cities manage fast-paced daily transactions manually in paper notebooks or struggle with slow, complicated typing interfaces on mobile apps.

**DukaanSaathi AI** bridges this digital divide with a **Voice-First** shop management assistant. A shopkeeper simply speaks their sale in their regional language (e.g. Telugu), and the application:
1. Captures and converts speech to text using **Gnani Prisma STT** with dynamic inventory keyword boosting.
2. Intelligently identifies the customer, product name, quantity, and units.
3. Automatically computes totals, validates live inventory stock, and holds the sale for one-click verification.
4. Responds back aloud in natural regional speech using **Gnani Timbre TTS** to confirm the transaction.

---

## 🚀 Key Features
- **🎙️ Regional Speech-to-Text (Gnani Prisma STT):** Powered by `gnani-vachana` with `te-IN` (Telugu) & Indian English recognition, custom inventory keyword boosting, and domain topic modeling.
- **🗣️ Natural Voice Feedback (Gnani Timbre TTS):** Speaks back confirmation messages aloud in Telugu (Shivani voice model), closing the voice loop without demanding continuous screen gaze.
- **⚡ Dynamic Inventory Matching:** Automatically translates common Telugu colloquial names (బియ్యం, పప్పు, షుగర్, రవ్వ, etc.) and dynamically matches against live inventory items in SQLite.
- **📦 Real-time Inventory & Low-Stock Alerts:** Automatically decrements stock quantities on confirmed sales and flags low-stock items (<= 5 units).
- **📊 Sales Tracking & Recent Transactions:** Full log of transactions with timestamp, customer name, unit pricing, and totals.
- **🛡️ Two-Step Safe Voice Checkout:** Displays recognized voice transcripts with a confirmation preview so shopkeepers retain 100% control before committing to inventory.

---

## 🏗️ Architecture & Workflow

```text
[Shopkeeper Speaks in Telugu]
             │
             ▼
   [In-Browser WAV Audio]
             │
             ▼
   [Gnani Prisma STT] ──► (te-IN + Dynamic Inventory Keywords)
             │
             ▼
  [Voice Extraction Engine] ──► (Maps Telugu/English words to Products & Quantities)
             │
             ▼
 [Pending Sale Review] ──► (User verifies & confirms)
             │
   ┌─────────┴─────────┐
   ▼                   ▼
[Update SQLite DB]   [Gnani Timbre TTS] ──► Speaks aloud:
(Stock & Sales Log)                        "రామ కి 2 కేజీ బియ్యం అమ్మారు. Total ₹200"
```

---

## 💻 Tech Stack
- **Backend:** Python 3.11+, Flask
- **Speech AI APIs:** Gnani AI Platform (`gnani-vachana` SDK)
  - **STT Model:** Prisma (`te-IN`, `prisma-v3.0`)
  - **TTS Model:** Timbre (`te-IN`, voice: `Shivani`)
- **Database:** SQLite
- **Frontend:** Responsive HTML5, Modern CSS Glassmorphism, Web Audio API

---

## 🛠️ Getting Started

### 1. Clone & Set Up Virtual Environment
```powershell
git clone https://github.com/your-username/DukaanSaathiAI.git
cd DukaanSaathiAI

# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 3. Configure API Credentials
Create a `.env` file in the project root:
```env
GNANI_API_KEY="your_gnani_api_key_here"
```

### 4. Run the Application
```powershell
python app.py
```
Open your browser and navigate to:  
👉 **`http://127.0.0.1:5000`**

---

## 🎯 Target Award Categories
- 🏆 **Regional Languages:** Deep support for Telugu voice shopping transactions.
- 🏆 **Real-World Impact:** Directly addresses digital adoption challenges for millions of micro-entrepreneurs and kirana stores.
- 🏆 **Tier 2 / Tier 3 Towns:** Designed specifically for regional merchants where typing in English apps is a major barrier.
- 🏆 **Best 60-Second Demo:** Intuitive end-to-end voice loop recorded under 1 minute.

---

## 📄 License
This project is open-source and created for educational & submission purposes under the MIT License.

