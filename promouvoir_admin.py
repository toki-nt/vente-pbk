from app import app, db, User

with app.app_context():
    u = User.query.filter_by(username='admin').first()
    if u:
        u.is_admin = True
        db.session.commit()
        print(f"OK, {u.username} est maintenant admin")
    else:
        print("Utilisateur introuvable")