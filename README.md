<div align="center">

# 🛒 OLX Scraper

**A high-performance, concurrent web scraper for OLX.com.pk — collects product listings at scale and stores them in a local SQLite database.**

[![CI](https://github.com/Adan-Bhatti/olx-scraper/actions/workflows/ci.yml/badge.svg)](https://github.com/Adan-Bhatti/olx-scraper/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.8%2B-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code Style: PEP8](https://img.shields.io/badge/code%20style-PEP8-blue)](https://peps.python.org/pep-0008/)

</div>

---

## ✨ Features

- ⚡ **Concurrent scraping** — parallel `ThreadPoolExecutor` workers for fast detail-page fetching
- 🔁 **Idempotent** — skips already-visited URLs via thread-safe tracking
- 🛡️ **Rate-limited** — randomized delays prevent bans and respect the server
- 🗄️ **SQLite storage** — structured schema for products and product images
- 🖥️ **CLI interface** — configure keyword, target count, and worker threads

---

## 📋 Requirements

- Python 3.8+
- pip

---

## 🚀 Installation

```bash
git clone https://github.com/Adan-Bhatti/olx-scraper.git
cd olx-scraper

python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 💻 Usage

```bash
cd src
python main.py
```

### CLI Options

| Option | Default | Description |
|--------|---------|-------------|
| `--keyword` | `smartphones` | Search keyword (slugified for OLX URLs) |
| `--target` | `1000` | Minimum number of products to collect |
| `--workers` | `8` | `ThreadPoolExecutor` worker count |

**Examples:**

```bash
python main.py --keyword laptops --target 500 --workers 4
python main.py --keyword "mobile phones" --target 1000
```

On completion, the scraper prints final row counts and writes a full log to `Execution_Log.txt` in the project root.

---

## 🗄️ Database Schema

```sql
CREATE TABLE products (
    id           TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    price        REAL,
    description  TEXT,
    seller_name  TEXT,
    rating       REAL,
    source_url   TEXT UNIQUE,
    harvested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE product_images (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id TEXT,
    image_url  TEXT NOT NULL,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE,
    UNIQUE(product_id, image_url)
);
```

**Inspect the database:**

```bash
sqlite3 ../ecommerce_harvest.db "SELECT COUNT(*) FROM products;"
sqlite3 ../ecommerce_harvest.db "SELECT id, name, price FROM products LIMIT 5;"
```

---

## 🏗️ Architecture and Design Notes

| Concern | Approach |
|---------|----------|
| **Concurrency** | Index pages crawled sequentially; detail pages fetched in parallel workers |
| **Idempotency** | `visited_urls` guarded by a `threading.Lock`; duplicates skipped at scheduling time |
| **Throttling** | `random.uniform(0, 5)` delay applied before each HTTP request |
| **SQLite Safety** | All writes use `INSERT OR IGNORE` inside a `threading.Lock` |

---

## ⚠️ Ethical Use and Disclaimer

This tool is for **educational purposes only**. When scraping any website:

- Respect the site's `robots.txt` and Terms of Service
- Use reasonable rate limits (built-in throttling is already configured)
- Do not scrape personal data beyond publicly listed information
- Do not use scraped data for commercial purposes without permission

The author is not responsible for any misuse of this software.

---

## 🤝 Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

---

## 👤 Author

**Adan Bhatti** · [GitHub](https://github.com/Adan-Bhatti)
