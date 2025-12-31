<p align="center">
  <img src="static/logo.svg" width="120" alt="Alexandria Logo">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Flask-000000?style=for-the-badge&logo=flask&logoColor=white" alt="Flask">
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind">
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker">
</p>

# Alexandria &mdash; Your Personal Private Library

Alexandria is a minimalist, vintage-inspired personal book tracker. It allows you to maintain a digital ledger of your reading journey, seamlessly integrating with the Google Books API to fetch rich metadata and covers.

## 📜 Features

- **Vintage Aesthetic**: A classic "Librarian's Ledger" feel using serif typography and paper-like textures.
- **Archive Search**: Direct integration with Google Books API to find and acquire new volumes.
- **Reading States**: Track your current reads and voyages completed.
- **Secure Access**: Configurable librarian credentials to protect your archives.
- **Modern Backend**: Built with Flask, SQLAlchemy, and managed by `uv`.
- **Containerized**: Full Docker and Docker Compose support for easy deployment.

## 🛠️ Configuration

Alexandria uses environment variables for configuration. You can copy the template to get started:

```bash
cp .env.example .env
```

### Environment Variables

| Variable | Description | Default |
| :--- | :--- | :--- |
| `APP_NAME` | The title of your library | `Alexandria` |
| `SECRET_KEY` | Security key for session encryption | `default-key` |
| `LIBRARIAN_USERNAME` | Admin login username | `admin` |
| `LIBRARIAN_PASSWORD` | Admin login password | `alexandria` |
| `DATABASE_URL` | SQLite database URI | `sqlite:///instance/alexandria.db` |

## 🚀 Getting Started

### Using Docker (Recommended)

1. **Build and start the container**:
   ```bash
   docker compose up -d
   ```
2. **Access your library** at `http://localhost:5000`.

### Manual Installation

Ensure you have [uv](https://github.com/astral-sh/uv) installed.

1. **Install dependencies**:
   ```bash
   uv sync
   ```
2. **Run the application**:
   ```bash
   uv run python app.py
   ```

## 📸 Screenshots

<p align="center">
  <img src="https://images.unsplash.com/photo-1507842217343-583bb7270b66?auto=format&fit=crop&q=80&w=1200" width="800" alt="Library Background">
</p>

## 📂 Project Structure

- `app.py`: Main application logic.
- `models.py`: Database models (Books & Users).
- `api.py`: Google Books API integration.
- `static/`: Favicon, logo, and CSS.
- `templates/`: Vintage Jinja2 templates.
- `instance/`: SQLite database storage (mounted as volume in Docker).

---
*Catalogued with care, 2025.*
