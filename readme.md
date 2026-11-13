# PLAYBACK.MG

Plateforme de vente de playbacks avec système de points et cascade de récompenses.

## 🎯 Concept

- Chaque client peut commander un playback personnalisé à l'administrateur.
- Le playback est mis en vente sur la plateforme à un prix dégressif.
- À chaque nouvel acheteur, le prix baisse de 1 000 Ar.
- Quand le prix atteint 0 Ar, le playback devient gratuit pour tous.
- Chaque acheteur gagne 1 000 points à chaque nouvel achat en aval.
- 1 point = 1 Ariary. Les points ne sont PAS convertibles en argent réel.

## 🛠️ Technologies

- **Flask** (framework web Python)
- **SQLite** (base de données)
- **Flask-Login** (authentification)
- **Flask-SQLAlchemy** (ORM)

## 📦 Installation

### 1. Cloner le projet

```bash
git clone <url-du-repo>
cd vente_de_pbk