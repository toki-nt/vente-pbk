import re
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'changez-cette-cle-secrete'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///playback.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


def detect_source(url):
    if not url:
        return None
    if 'youtube.com' in url or 'youtu.be' in url:
        return 'youtube'
    if 'drive.google.com' in url:
        return 'drive'
    return None


def get_youtube_id(url):
    patterns = [r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([^&?/\s]+)']
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def get_drive_id(url):
    patterns = [r'drive\.google\.com/file/d/([^/]+)', r'drive\.google\.com/open\?id=([^&]+)']
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


# --- Modèles ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False, nullable=False)
    points = db.Column(db.Integer, nullable=False, default=0)

    playbacks = db.relationship('Playback', backref='creator', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Playback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Integer, nullable=False, default=9000)
    owner_count = db.Column(db.Integer, nullable=False, default=1)
    is_free = db.Column(db.Boolean, default=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    demo_url = db.Column(db.String(500), nullable=True)
    demo_source = db.Column(db.String(20), nullable=True)
    full_url = db.Column(db.String(500), nullable=True)
    full_source = db.Column(db.String(20), nullable=True)

    def display_price(self):
        if self.is_free:
            return "0 Ar (0 pts) - Gratuit"
        return f"{self.price:,} Ar ({self.price:,} pts)".replace(",", " ")


class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    playback_id = db.Column(db.Integer, db.ForeignKey('playback.id'), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    price_paid = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    user = db.relationship('User', backref='purchases')
    playback = db.relationship('Playback', backref='purchases')


class PointGain(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    playback_id = db.Column(db.Integer, db.ForeignKey('playback.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False, default=1000)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    user = db.relationship('User', foreign_keys=[user_id], backref='point_gains')
    buyer = db.relationship('User', foreign_keys=[buyer_id])
    playback = db.relationship('Playback', backref='point_gains')


class RechargeRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    phone_used = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    user = db.relationship('User', backref='recharge_requests')


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(30), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    link = db.Column(db.String(200), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    user = db.relationship('User', backref='notifications')


# 🆕 Historique des actions admin
class AdminAction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    target_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    details = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    admin = db.relationship('User', foreign_keys=[admin_id], backref='admin_actions')
    target_user = db.relationship('User', foreign_keys=[target_user_id])


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# --- Contexte global : notifications non lues ---
@app.context_processor
def inject_notifications():
    if current_user.is_authenticated:
        unread = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return {'unread_notifications': unread}
    return {'unread_notifications': 0}


# --- Routes utilisateurs ---
@app.route('/')
def index():
    playbacks = Playback.query.order_by(Playback.id.desc()).all()
    return render_template('catalogue.html', playbacks=playbacks)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        phone = request.form.get('phone')
        password = request.form.get('password')

        if User.query.filter_by(username=username).first():
            flash('Ce pseudo est déjà pris')
            return redirect(url_for('register'))

        new_user = User(username=username, phone=phone)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()

        flash('Inscription réussie, veuillez vous connecter')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if user.is_blocked:
                flash('Votre compte a été bloqué. Contactez l\'administrateur.')
                return redirect(url_for('login'))
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Pseudo ou mot de passe incorrect')

    return render_template('login.html')


@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))


@app.route('/catalogue')
def catalogue():
    playbacks = Playback.query.order_by(Playback.id.desc()).all()
    return render_template('catalogue.html', playbacks=playbacks)


@app.route('/achat/<int:playback_id>')
@login_required
def achat(playback_id):
    pb = db.session.get(Playback, playback_id)
    if not pb:
        return render_template('404.html'), 404
    if pb.is_free:
        flash('Ce playback est déjà gratuit.')
        return redirect(url_for('catalogue'))
    if pb.creator_id == current_user.id:
        flash('Vous ne pouvez pas acheter votre propre playback.')
        return redirect(url_for('catalogue'))
    if Purchase.query.filter_by(user_id=current_user.id, playback_id=pb.id).first():
        flash('Vous possédez déjà ce playback.')
        return redirect(url_for('catalogue'))
    return render_template('achat.html', pb=pb)


@app.route('/achat/<int:playback_id>/confirmer', methods=['POST'])
@login_required
def confirmer_achat(playback_id):
    try:
        pb = db.session.get(Playback, playback_id)

        if not pb:
            return render_template('404.html'), 404
        if pb.is_free:
            flash('Ce playback est déjà gratuit.')
            return redirect(url_for('catalogue'))
        if pb.creator_id == current_user.id:
            flash('Vous ne pouvez pas acheter votre propre playback.')
            return redirect(url_for('catalogue'))
        if Purchase.query.filter_by(user_id=current_user.id, playback_id=pb.id).first():
            flash('Vous possédez déjà ce playback.')
            return redirect(url_for('catalogue'))
        if current_user.points < pb.price:
            manque = pb.price - current_user.points
            flash(f'Solde insuffisant. Il vous manque {manque} pts ({manque} Ar).')
            return redirect(url_for('recharge'))

        previous_purchases = Purchase.query.filter_by(playback_id=pb.id).order_by(Purchase.position).all()

        current_user.points -= pb.price

        purchase = Purchase(
            user_id=current_user.id,
            playback_id=pb.id,
            position=len(previous_purchases) + 1,
            price_paid=pb.price
        )
        db.session.add(purchase)

        for prev in previous_purchases:
            prev_user = db.session.get(User, prev.user_id)
            if prev_user:
                prev_user.points += 1000
                db.session.add(PointGain(
                    user_id=prev_user.id,
                    playback_id=pb.id,
                    buyer_id=current_user.id,
                    amount=1000
                ))
                db.session.add(Notification(
                    type='points_gained',
                    message=f'Vous avez gagné 1 000 pts grâce à l\'achat de "{pb.title}" par {current_user.username}.',
                    user_id=prev_user.id,
                    link='/mes-gains'
                ))

        pb.price -= 1000
        if pb.price <= 0:
            pb.price = 0
            pb.is_free = True

        pb.owner_count += 1

        db.session.add(Notification(
            type='purchase_success',
            message=f'Vous avez acheté "{pb.title}" pour {purchase.price_paid} pts.',
            user_id=current_user.id,
            link=f'/ecoute/{pb.id}'
        ))

        admin_users = User.query.filter_by(is_admin=True).all()
        for admin in admin_users:
            db.session.add(Notification(
                type='new_purchase',
                message=f'{current_user.username} a acheté "{pb.title}" pour {purchase.price_paid} pts.',
                user_id=admin.id,
                link='/admin/playbacks'
            ))

        db.session.commit()

        return render_template('achat_reussi.html', pb=pb, purchase=purchase)

    except Exception as e:
        db.session.rollback()
        return render_template('500.html'), 500


@app.route('/mes-playbacks')
@login_required
def mes_playbacks():
    purchases = Purchase.query.filter_by(user_id=current_user.id).order_by(Purchase.id.desc()).all()
    return render_template('mes_playbacks.html', purchases=purchases)


@app.route('/mes-gains')
@login_required
def mes_gains():
    gains = PointGain.query.filter_by(user_id=current_user.id).order_by(PointGain.id.desc()).all()
    total = sum(g.amount for g in gains)
    return render_template('mes_gains.html', gains=gains, total=total)


@app.route('/ecoute/<int:playback_id>')
@login_required
def ecoute(playback_id):
    pb = db.session.get(Playback, playback_id)
    if not pb:
        return render_template('404.html'), 404

    if pb.is_free:
        return render_template('ecoute.html', pb=pb)

    purchase = Purchase.query.filter_by(user_id=current_user.id, playback_id=pb.id).first()
    if not purchase:
        flash('Vous ne possédez pas ce playback.')
        return redirect(url_for('catalogue'))

    return render_template('ecoute.html', pb=pb)


@app.route('/recharge', methods=['GET', 'POST'])
@login_required
def recharge():
    if request.method == 'POST':
        try:
            amount = int(request.form.get('amount'))
            phone_used = request.form.get('phone_used')
            if amount < 1000:
                flash('Le montant minimum est de 1000 Ar (1000 pts).')
                return redirect(url_for('recharge'))

            existing_pending = RechargeRequest.query.filter_by(
                user_id=current_user.id,
                status='pending'
            ).first()
            if existing_pending:
                flash('Vous avez déjà une demande de recharge en attente. Attendez sa validation avant d\'en créer une nouvelle.')
                return redirect(url_for('recharge'))

            req = RechargeRequest(
                user_id=current_user.id,
                amount=amount,
                phone_used=phone_used,
                status='pending'
            )
            db.session.add(req)

            admin_users = User.query.filter_by(is_admin=True).all()
            for admin in admin_users:
                db.session.add(Notification(
                    type='new_recharge',
                    message=f'{current_user.username} demande une recharge de {amount} pts ({amount} Ar).',
                    user_id=admin.id,
                    link='/admin/recharges'
                ))

            db.session.commit()
            flash('Demande de recharge envoyée.')
            return redirect(url_for('recharge'))
        except Exception as e:
            db.session.rollback()
            return render_template('500.html'), 500

    requests_list = RechargeRequest.query.filter_by(user_id=current_user.id).order_by(RechargeRequest.id.desc()).all()
    has_pending = any(r.status == 'pending' for r in requests_list)
    return render_template('recharge.html', requests=requests_list, has_pending=has_pending)


# --- Notifications (client) ---
@app.route('/mes-notifications')
@login_required
def mes_notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.id.desc()).limit(50).all()

    # 🆕 W : marquer automatiquement comme lues
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()

    return render_template('mes_notifications.html', notifications=notifications)


@app.route('/mes-notifications/<int:notif_id>/lire', methods=['POST'])
@login_required
def lire_notification(notif_id):
    n = db.session.get(Notification, notif_id)
    if not n or n.user_id != current_user.id:
        return render_template('404.html'), 404
    n.is_read = True
    db.session.commit()
    return redirect(n.link if n.link else url_for('mes_notifications'))


@app.route('/mes-notifications/tout-lire', methods=['POST'])
@login_required
def lire_toutes_notifications():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({'is_read': True})
    db.session.commit()
    flash('Toutes vos notifications ont été marquées comme lues.')
    return redirect(url_for('mes_notifications'))


# --- Admin ---
@app.route('/admin')
@login_required
def admin_dashboard():
    if not current_user.is_admin:
        return render_template('403.html'), 403

    nb_users = User.query.count()
    nb_playbacks = Playback.query.count()
    nb_purchases = Purchase.query.count()
    total_points_distributed = db.session.query(db.func.sum(PointGain.amount)).scalar() or 0
    nb_recharges_validated = RechargeRequest.query.filter_by(status='validated').count()
    nb_recharges_pending = RechargeRequest.query.filter_by(status='pending').count()
    recent_purchases = Purchase.query.order_by(Purchase.id.desc()).limit(10).all()
    nb_blocked = User.query.filter_by(is_blocked=True).count()

    top_playbacks = db.session.query(
        Playback.title,
        db.func.count(Purchase.id).label('nb')
    ).join(Purchase).filter(Purchase.position > 1).group_by(Playback.id).order_by(db.func.count(Purchase.id).desc()).limit(5).all()

    top_gainers = db.session.query(
        User.username,
        db.func.sum(PointGain.amount).label('total')
    ).join(PointGain, PointGain.user_id == User.id).group_by(User.id).order_by(db.func.sum(PointGain.amount).desc()).limit(5).all()

    top_creators = db.session.query(
        User.username,
        db.func.count(Playback.id).label('nb')
    ).join(Playback, Playback.creator_id == User.id).group_by(User.id).order_by(db.func.count(Playback.id).desc()).limit(5).all()

    return render_template('admin_dashboard.html',
        nb_users=nb_users,
        nb_playbacks=nb_playbacks,
        nb_purchases=nb_purchases,
        total_points_distributed=total_points_distributed,
        nb_recharges_validated=nb_recharges_validated,
        nb_recharges_pending=nb_recharges_pending,
        recent_purchases=recent_purchases,
        nb_blocked=nb_blocked,
        top_playbacks=top_playbacks,
        top_gainers=top_gainers,
        top_creators=top_creators
    )


@app.route('/admin/utilisateurs')
@login_required
def admin_utilisateurs():
    if not current_user.is_admin:
        return render_template('403.html'), 403
    users = User.query.order_by(User.id).all()
    nb_blocked = User.query.filter_by(is_blocked=True).count()
    return render_template('admin_utilisateurs.html', users=users, nb_blocked=nb_blocked)


# --- Admin : modifier points ---
@app.route('/admin/utilisateurs/<int:user_id>/modifier-points', methods=['GET', 'POST'])
@login_required
def modifier_points(user_id):
    if not current_user.is_admin:
        return render_template('403.html'), 403

    u = db.session.get(User, user_id)
    if not u:
        return render_template('404.html'), 404

    if request.method == 'POST':
        try:
            delta = int(request.form.get('delta'))
            raison = (request.form.get('raison') or '').strip()

            if delta == 0:
                flash('Aucune modification (le montant est 0).')
                return redirect(url_for('admin_utilisateurs'))

            ancien_solde = u.points
            nouveau_solde = u.points + delta
            if nouveau_solde < 0:
                flash(f'Impossible : le solde ne peut pas devenir négatif (solde actuel : {ancien_solde} pts).')
                return redirect(url_for('modifier_points', user_id=u.id))

            u.points = nouveau_solde

            signe = '+' if delta > 0 else ''
            raison_txt = f' Raison : {raison}' if raison else ''
            db.session.add(Notification(
                type='points_manual',
                message=f'L\'administrateur a modifié votre solde : {signe}{delta} pts ({ancien_solde} → {nouveau_solde} pts).{raison_txt}',
                user_id=u.id,
                link='/dashboard'
            ))

            # 🆕 X : enregistrer l'action admin
            db.session.add(AdminAction(
                admin_id=current_user.id,
                action='modifier_points',
                target_user_id=u.id,
                details=f'{ancien_solde} → {nouveau_solde} pts ({signe}{delta}). Raison : {raison or "aucune"}'
            ))

            db.session.commit()
            flash(f'Solde de {u.username} modifié : {ancien_solde} → {nouveau_solde} pts ({signe}{delta}).')
            return redirect(url_for('admin_utilisateurs'))
        except Exception as e:
            db.session.rollback()
            return render_template('500.html'), 500

    return render_template('admin_modifier_points.html', u=u)


# --- Admin : promouvoir / rétrograder / bloquer / débloquer ---
@app.route('/admin/utilisateurs/<int:user_id>/promouvoir', methods=['POST'])
@login_required
def promouvoir_admin(user_id):
    if not current_user.is_admin:
        return render_template('403.html'), 403
    u = db.session.get(User, user_id)
    if not u:
        return render_template('404.html'), 404
    u.is_admin = True
    db.session.add(AdminAction(
        admin_id=current_user.id,
        action='promouvoir',
        target_user_id=u.id,
        details=f'{u.username} promu administrateur'
    ))
    db.session.commit()
    flash(f'{u.username} est maintenant administrateur.')
    return redirect(url_for('admin_utilisateurs'))


@app.route('/admin/utilisateurs/<int:user_id>/retrograder', methods=['POST'])
@login_required
def retrograder_admin(user_id):
    if not current_user.is_admin:
        return render_template('403.html'), 403
    u = db.session.get(User, user_id)
    if not u:
        return render_template('404.html'), 404
    if u.id == current_user.id:
        flash('Vous ne pouvez pas retirer votre propre statut admin.')
        return redirect(url_for('admin_utilisateurs'))
    u.is_admin = False
    db.session.add(AdminAction(
        admin_id=current_user.id,
        action='retrograder',
        target_user_id=u.id,
        details=f'{u.username} retiré du statut admin'
    ))
    db.session.commit()
    flash(f'{u.username} n\'est plus administrateur.')
    return redirect(url_for('admin_utilisateurs'))


@app.route('/admin/utilisateurs/<int:user_id>/bloquer', methods=['POST'])
@login_required
def bloquer_utilisateur(user_id):
    if not current_user.is_admin:
        return render_template('403.html'), 403

    u = db.session.get(User, user_id)
    if not u:
        return render_template('404.html'), 404

    if u.id == current_user.id:
        flash('Vous ne pouvez pas vous bloquer vous-même.')
        return redirect(url_for('admin_utilisateurs'))

    if u.is_admin:
        flash('Impossible de bloquer un administrateur. Retirez-lui d\'abord le statut admin.')
        return redirect(url_for('admin_utilisateurs'))

    if u.is_blocked:
        flash(f'{u.username} est déjà bloqué.')
        return redirect(url_for('admin_utilisateurs'))

    u.is_blocked = True
    db.session.add(AdminAction(
        admin_id=current_user.id,
        action='bloquer',
        target_user_id=u.id,
        details=f'{u.username} bloqué'
    ))
    db.session.commit()
    flash(f'{u.username} a été bloqué.')
    return redirect(url_for('admin_utilisateurs'))


@app.route('/admin/utilisateurs/<int:user_id>/debloquer', methods=['POST'])
@login_required
def debloquer_utilisateur(user_id):
    if not current_user.is_admin:
        return render_template('403.html'), 403

    u = db.session.get(User, user_id)
    if not u:
        return render_template('404.html'), 404

    if not u.is_blocked:
        flash(f'{u.username} n\'est pas bloqué.')
        return redirect(url_for('admin_utilisateurs'))

    u.is_blocked = False
    db.session.add(AdminAction(
        admin_id=current_user.id,
        action='debloquer',
        target_user_id=u.id,
        details=f'{u.username} débloqué'
    ))
    db.session.commit()
    flash(f'{u.username} a été débloqué.')
    return redirect(url_for('admin_utilisateurs'))


# --- Admin : historique ---
@app.route('/admin/historique')
@login_required
def admin_historique():
    if not current_user.is_admin:
        return render_template('403.html'), 403
    actions = AdminAction.query.order_by(AdminAction.id.desc()).limit(200).all()
    return render_template('admin_historique.html', actions=actions)


# --- Admin : playbacks ---
@app.route('/admin/playbacks')
@login_required
def admin_playbacks():
    if not current_user.is_admin:
        return render_template('403.html'), 403
    playbacks = Playback.query.order_by(Playback.id.desc()).all()
    return render_template('admin_playbacks.html', playbacks=playbacks)


# --- Admin : recharges ---
@app.route('/admin/recharges')
@login_required
def admin_recharges():
    if not current_user.is_admin:
        return render_template('403.html'), 403
    pending = RechargeRequest.query.filter_by(status='pending').order_by(RechargeRequest.id).all()
    all_requests = RechargeRequest.query.order_by(RechargeRequest.id.desc()).limit(20).all()
    return render_template('admin_recharges.html', pending=pending, all_requests=all_requests)


@app.route('/admin/recharges/<int:req_id>/valider', methods=['POST'])
@login_required
def valider_recharge(req_id):
    if not current_user.is_admin:
        return render_template('403.html'), 403
    try:
        req = db.session.get(RechargeRequest, req_id)
        if not req or req.status != 'pending':
            flash('Demande introuvable ou déjà traitée.')
            return redirect(url_for('admin_recharges'))
        req.user.points += req.amount
        req.status = 'validated'

        db.session.add(Notification(
            type='recharge_validated',
            message=f'Votre recharge de {req.amount} pts ({req.amount} Ar) a été validée. Votre nouveau solde : {req.user.points} pts.',
            user_id=req.user.id,
            link='/dashboard'
        ))

        db.session.add(AdminAction(
            admin_id=current_user.id,
            action='valider_recharge',
            target_user_id=req.user.id,
            details=f'Recharge de {req.amount} pts validée'
        ))

        db.session.commit()
        flash(f'Recharge validée : {req.amount} pts crédités à {req.user.username}.')
        return redirect(url_for('admin_recharges'))
    except Exception as e:
        db.session.rollback()
        return render_template('500.html'), 500


@app.route('/admin/recharges/<int:req_id>/refuser', methods=['POST'])
@login_required
def refuser_recharge(req_id):
    if not current_user.is_admin:
        return render_template('403.html'), 403
    try:
        req = db.session.get(RechargeRequest, req_id)
        if not req or req.status != 'pending':
            flash('Demande introuvable ou déjà traitée.')
            return redirect(url_for('admin_recharges'))
        req.status = 'refused'

        db.session.add(Notification(
            type='recharge_refused',
            message=f'Votre demande de recharge de {req.amount} pts ({req.amount} Ar) a été refusée. Contactez l\'administrateur pour plus d\'informations.',
            user_id=req.user.id,
            link='/recharge'
        ))

        db.session.add(AdminAction(
            admin_id=current_user.id,
            action='refuser_recharge',
            target_user_id=req.user.id,
            details=f'Recharge de {req.amount} pts refusée'
        ))

        db.session.commit()
        flash(f'Recharge refusée pour {req.user.username}.')
        return redirect(url_for('admin_recharges'))
    except Exception as e:
        db.session.rollback()
        return render_template('500.html'), 500


# --- Admin : création playback ---
@app.route('/admin/playback/new', methods=['GET', 'POST'])
@login_required
def new_playback():
    if not current_user.is_admin:
        return render_template('403.html'), 403

    users = User.query.order_by(User.username).all()

    if request.method == 'POST':
        title = request.form.get('title')
        creator_id = int(request.form.get('creator_id'))
        price = int(request.form.get('price'))
        demo_url = (request.form.get('demo_url') or '').strip()
        full_url = (request.form.get('full_url') or '').strip()

        creator = db.session.get(User, creator_id)
        if not creator:
            flash('Utilisateur introuvable')
            return redirect(url_for('new_playback'))

        if creator.is_blocked:
            flash(f'{creator.username} est bloqué. Impossible de créer un playback pour lui.')
            return redirect(url_for('new_playback'))

        demo_source = None
        if demo_url:
            demo_source = detect_source(demo_url)
            if demo_source is None:
                flash('Lien démo non reconnu. Utilisez YouTube ou Google Drive.')
                return redirect(url_for('new_playback'))

        full_source = None
        if full_url:
            full_source = detect_source(full_url)
            if full_source is None:
                flash('Lien complet non reconnu. Utilisez YouTube ou Google Drive.')
                return redirect(url_for('new_playback'))

        pb = Playback(
            title=title,
            creator_id=creator.id,
            price=price,
            owner_count=1,
            is_free=False,
            demo_url=demo_url or None,
            demo_source=demo_source,
            full_url=full_url or None,
            full_source=full_source
        )
        db.session.add(pb)
        db.session.flush()

        db.session.add(Purchase(user_id=creator.id, playback_id=pb.id, position=1, price_paid=0))

        db.session.add(Notification(
            type='playback_created',
            message=f'Votre playback "{pb.title}" a été mis en vente à {pb.price:,} pts.'.replace(',', ' '),
            user_id=creator.id,
            link=f'/ecoute/{pb.id}'
        ))

        db.session.add(AdminAction(
            admin_id=current_user.id,
            action='creer_playback',
            target_user_id=creator.id,
            details=f'Playback "{pb.title}" créé pour {creator.username} à {pb.price} pts'
        ))

        db.session.commit()

        flash('Playback créé avec succès')
        return redirect(url_for('catalogue'))

    return render_template('admin_new_playback.html', users=users)


# --- Gestionnaires d'erreurs ---
@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


@app.errorhandler(403)
def forbidden(e):
    return render_template('403.html'), 403


@app.errorhandler(500)
def server_error(e):
    db.session.rollback()
    return render_template('500.html'), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)