import random
from app import app, db, User

# Liste : (pseudo, mot de passe, téléphone)
utilisateurs = [
    ("Rakoto", "rakoto", "0340000002"),
    ("Rabe", "rabe", "0340000003"),
    ("Rasoa", "rasoa", "0340000004"),
    ("Randria", "randria", "0340000005"),
    ("Ravao", "ravao", "0340000006"),
    ("Ramena", "ramena", "0340000007"),
    ("Rakala", "rakala", "0340000008"),
    ("Rindra", "rindra", "0340000009"),
    ("Rabozy", "rabozy", "0340000010"),
    ("Raly", "raly", "0340000011"),
    ("Rado", "rado", "0340000012"),
    ("Rina", "rina", "0340000013"),
]

with app.app_context():
    created = 0
    skipped = 0
    total_points = 0

    for pseudo, mdp, tel in utilisateurs:
        if User.query.filter_by(username=pseudo).first():
            print(f"⏭️  {pseudo} existe déjà — ignoré")
            skipped += 1
            continue

        # 🆕 Solde aléatoire entre 1000 et 10000, multiple de 1000
        points = random.randint(1, 10) * 1000

        u = User(username=pseudo, phone=tel, points=points)
        u.set_password(mdp)
        db.session.add(u)
        created += 1
        total_points += points
        print(f"✅ {pseudo} créé (mdp : {mdp}, tel : {tel}, {points} pts)")

    db.session.commit()
    print()
    print(f"📊 Total : {created} créé(s), {skipped} ignoré(s)")
    print(f"💰 Points distribués : {total_points} pts")