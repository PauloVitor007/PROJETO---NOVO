import os
import uuid
from functools import wraps
from datetime import datetime, timezone, date, timedelta
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, g
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# --- 1. CONFIGURAÇÃO DA APLICAÇÃO ---
app = Flask(__name__)
try:
    os.makedirs(app.instance_path)
except OSError:
    pass

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(app.instance_path, 'database.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = '77cd9b0684a5113200d4810755f4a9e5455a3c860df49cf7'

app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.googlemail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() in ['true', '1', 't']
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = ('Hub Comunitário', os.getenv('MAIL_USERNAME'))

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])
db = SQLAlchemy(app)
migrate = Migrate(app, db)

# --- CONFIGURAÇÃO DE UPLOADS ---
UPLOAD_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/profile_pics')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

CLUB_MEDIA_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/club_media')
ALLOWED_MEDIA_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'mp4', 'mov', 'webp'}
app.config['CLUB_MEDIA_FOLDER'] = CLUB_MEDIA_FOLDER
os.makedirs(CLUB_MEDIA_FOLDER, exist_ok=True)

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

# --- 3. MODELOS DA BASE DE DADOS ---
inscricao_evento_tabela = db.Table('inscricao_evento',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('evento_id', db.Integer, db.ForeignKey('evento.id'), primary_key=True)
)
membros_clube_tabela = db.Table('membros_clube',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('clube_id', db.Integer, db.ForeignKey('clube.id'), primary_key=True)
)
user_badges_tabela = db.Table('user_badges',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('badge_id', db.Integer, db.ForeignKey('badge.id'), primary_key=True)
)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(12), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    image_file = db.Column(db.String(100), nullable=False, default='default.jpg')
    eventos_inscritos = db.relationship('Evento', secondary=inscricao_evento_tabela, back_populates='alunos_inscritos', lazy='dynamic')
    clubes_membro = db.relationship('Clube', secondary=membros_clube_tabela, back_populates='membros', lazy='dynamic')
    clubes_liderados = db.relationship('Clube', backref='lider', lazy='dynamic', foreign_keys='Clube.lider_id')
    topicos_criados = db.relationship('ForumTopico', backref='autor', lazy='dynamic', cascade="all, delete-orphan")
    posts_criados = db.relationship('ForumPost', backref='autor', lazy='dynamic', cascade="all, delete-orphan")
    badges = db.relationship('Badge', secondary=user_badges_tabela, back_populates='users', lazy='dynamic')
    def get_reset_token(self, expires_sec=1800): return serializer.dumps({'user_id': self.id}, salt='password-reset-salt')
    @staticmethod
    def verify_reset_token(token, expires_sec=1800):
        try:
            data = serializer.loads(token, salt='password-reset-salt', max_age=expires_sec)
            return User.query.get(data['user_id'])
        except (SignatureExpired, Exception): return None

class Clube(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    categoria = db.Column(db.String(50), nullable=False)
    lider_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    membros = db.relationship('User', secondary=membros_clube_tabela, back_populates='clubes_membro', lazy='dynamic')
    eventos = db.relationship('Evento', backref='clube_organizador', lazy='dynamic', cascade="all, delete-orphan")
    forum_topicos = db.relationship('ForumTopico', backref='clube', lazy='dynamic', cascade="all, delete-orphan")
    media_files = db.relationship('ClubeMedia', backref='clube', lazy='dynamic', cascade="all, delete-orphan")

class Evento(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    vagas = db.Column(db.Integer, nullable=False)
    data_evento = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    clube_id = db.Column(db.Integer, db.ForeignKey('clube.id'), nullable=False)
    alunos_inscritos = db.relationship('User', secondary=inscricao_evento_tabela, back_populates='eventos_inscritos', lazy='dynamic')
    noticias = db.relationship('Noticia', backref='evento', lazy='dynamic', cascade="all, delete-orphan")
    @property
    def vagas_restantes(self): return self.vagas - self.alunos_inscritos.count()

class Noticia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    data_publicacao = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    evento_id = db.Column(db.Integer, db.ForeignKey('evento.id'), nullable=True)

class ForumTopico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    conteudo = db.Column(db.Text, nullable=False)
    data_criacao = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    clube_id = db.Column(db.Integer, db.ForeignKey('clube.id'), nullable=False)
    posts = db.relationship('ForumPost', backref='topico', lazy='dynamic', cascade="all, delete-orphan")

class ForumPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conteudo = db.Column(db.Text, nullable=False)
    data_criacao = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topico_id = db.Column(db.Integer, db.ForeignKey('forum_topico.id'), nullable=False)

class Badge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    icon_class = db.Column(db.String(50), nullable=False)
    users = db.relationship('User', secondary=user_badges_tabela, back_populates='badges', lazy='dynamic')

class CardapioRU(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, unique=True, nullable=False)
    prato_principal = db.Column(db.String(150), nullable=False)
    vegetariano = db.Column(db.String(150), nullable=False)
    acompanhamento = db.Column(db.String(200), nullable=False)
    salada = db.Column(db.String(150), nullable=False)
    sobremesa = db.Column(db.String(100), nullable=False)

class CalendarioAcademico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.Date, nullable=False)
    descricao = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(50), nullable=False)

class ClubeMedia(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    descricao = db.Column(db.String(200), nullable=True)
    data_upload = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    clube_id = db.Column(db.Integer, db.ForeignKey('clube.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    uploader = db.relationship('User', backref='uploaded_media')

# --- 4. LÓGICA AUXILIAR E DECORATORS ---
@app.before_request
def load_logged_in_user():
    user_id = session.get('user_id')
    g.user = User.query.get(user_id) if user_id else None
    if user_id and g.user is None: session.clear()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if g.user is None:
            flash('Você precisa fazer login para acessar esta página.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def club_leader_required(clube_id_arg='clube_id'):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            clube_id = kwargs.get(clube_id_arg)
            clube = Clube.query.get_or_404(clube_id)
            if g.user is None or clube.lider_id != g.user.id:
                flash('Acesso restrito ao líder do clube.', 'danger')
                return redirect(url_for('detalhe_clube', clube_id=clube.id))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def club_member_required(clube_id_arg='clube_id'):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            clube_id = kwargs.get(clube_id_arg)
            clube = Clube.query.get_or_404(clube_id)
            if g.user is None or clube not in g.user.clubes_membro.all():
                flash('Você precisa ser membro deste clube para acessar esta área.', 'warning')
                return redirect(url_for('detalhe_clube', clube_id=clube.id))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def user_has_badge(user, badge_name): return user.badges.filter_by(nome=badge_name).count() > 0

def award_badge(user, badge_name, show_flash=True):
    if not user_has_badge(user, badge_name):
        badge = Badge.query.filter_by(nome=badge_name).first()
        if badge:
            user.badges.append(badge)
            db.session.commit()
            if show_flash:
                flash(f'Selo Desbloqueado: "{badge.nome}"!', 'special')

@app.context_processor
def inject_utils():
    return dict(
        current_user_data=g.user,
        current_year=datetime.now(timezone.utc).year,
        timedelta=timedelta
    )

# --- 5. ROTAS DE AUTENTICAÇÃO E CONTA ---
@app.route('/')
def index(): return redirect(url_for('login')) if g.user is None else redirect(url_for('noticias'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if g.user: return redirect(url_for('noticias'))
    if request.method == 'POST':
        email, username = request.form.get('email'), request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(email=email).first(): flash('Este e-mail já está em uso.', 'warning')
        elif User.query.filter_by(username=username).first(): flash('Esta matrícula já está registrada.', 'warning')
        else:
            novo_user = User(email=email, username=username, password_hash=generate_password_hash(password))
            db.session.add(novo_user)
            db.session.commit()
            if User.query.count() <= 10: award_badge(novo_user, 'Membro Pioneiro')
            flash('Conta criada com sucesso! Pode fazer o login.', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if g.user: return redirect(url_for('noticias'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password_hash, request.form.get('password')):
            session.clear(); session['user_id'] = user.id
            return redirect(url_for('noticias'))
        else: flash('Matrícula ou senha inválidos.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Você saiu da sua conta.', 'info')
    return redirect(url_for('login'))

@app.route('/account', methods=['GET', 'POST'])
@login_required
def account():
    if request.method == 'POST':
        if 'picture' not in request.files: flash('Nenhuma parte do arquivo encontrada no formulário.', 'danger')
        else:
            file = request.files['picture']
            if file.filename == '': flash('Nenhum arquivo selecionado.', 'warning')
            elif file and allowed_file(file.filename, ALLOWED_EXTENSIONS):
                ext = os.path.splitext(file.filename)[1]
                filename = secure_filename(f"{g.user.username}{ext}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                g.user.image_file = filename
                db.session.commit()
                flash('Foto de perfil atualizada com sucesso!', 'success')
            else: flash('Tipo de arquivo inválido. Use png, jpg, jpeg ou gif.', 'danger')
        return redirect(url_for('account'))
    image_file = url_for('static', filename='profile_pics/' + g.user.image_file)
    return render_template('account.html', image_file=image_file, eventos=g.user.eventos_inscritos)

def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Redefinição de Senha - Hub Comunitário', recipients=[user.email])
    msg.html = f'''<p>Para redefinir sua senha, visite o seguinte link:</p>
<a href="{url_for('reset_password', token=token, _external=True)}">
    {url_for('reset_password', token=token, _external=True)}
</a>
<p>Se você não fez esta solicitação, ignore este e-mail.</p>
'''
    mail.send(msg)

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if g.user: return redirect(url_for('noticias'))
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form.get('email')).first()
        if user:
            send_reset_email(user)
            flash('Um e-mail com instruções para redefinir sua senha foi enviado.', 'info')
            return redirect(url_for('login'))
        else:
            flash('Nenhuma conta encontrada com este e-mail.', 'warning')
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if g.user: return redirect(url_for('noticias'))
    user = User.verify_reset_token(token)
    if not user:
        flash('O token é inválido ou expirou.', 'warning')
        return redirect(url_for('forgot_password'))
    if request.method == 'POST':
        user.password_hash = generate_password_hash(request.form.get('password'))
        db.session.commit()
        flash('Sua senha foi atualizada! Você já pode fazer login.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)

@app.route('/account/change_password', methods=['POST'])
@login_required
def change_password():
    if not check_password_hash(g.user.password_hash, request.form.get('old_password')):
        flash('A senha antiga está incorreta.', 'danger')
    elif request.form.get('new_password') != request.form.get('confirm_password'):
        flash('A nova senha e a confirmação não correspondem.', 'danger')
    else:
        g.user.password_hash = generate_password_hash(request.form.get('new_password'))
        db.session.commit()
        flash('Senha alterada com sucesso!', 'success')
    return redirect(url_for('account'))

@app.route('/account/delete', methods=['POST'])
@login_required
def delete_account():
    if not check_password_hash(g.user.password_hash, request.form.get('password')):
        flash('Senha incorreta. A exclusão da conta foi cancelada.', 'danger')
        return redirect(url_for('account'))
    user_to_delete = g.user
    session.clear()
    db.session.delete(user_to_delete)
    db.session.commit()
    flash('Sua conta foi excluída permanentemente.', 'info')
    return redirect(url_for('login'))


# --- 6. ROTAS PRINCIPAIS DA APLICAÇÃO ---
@app.route('/noticias')
@login_required
def noticias():
    todas_noticias = Noticia.query.order_by(Noticia.data_publicacao.desc()).all()
    return render_template('noticias.html', noticias=todas_noticias)

@app.route('/clubes')
@login_required
def clubes():
    todos_clubes = Clube.query.order_by(Clube.nome).all()
    return render_template('clubes.html', clubes=todos_clubes)

@app.route('/clube/<int:clube_id>')
@login_required
def detalhe_clube(clube_id):
    clube = Clube.query.get_or_404(clube_id)
    agora = datetime.now(timezone.utc)
    eventos_futuros = clube.eventos.filter(Evento.data_evento >= agora).order_by(Evento.data_evento.asc()).all()
    eventos_passados = clube.eventos.filter(Evento.data_evento < agora).order_by(Evento.data_evento.desc()).all()
    is_member = g.user in clube.membros
    is_leader = g.user.id == clube.lider_id
    return render_template('detalhe_clube.html', clube=clube, eventos_futuros=eventos_futuros, eventos_passados=eventos_passados, is_member=is_member, is_leader=is_leader)

@app.route('/ranking')
@login_required
def ranking():
    clubes_rankeados = sorted(Clube.query.all(), key=lambda c: c.membros.count(), reverse=True)
    return render_template('ranking.html', clubes=clubes_rankeados)

@app.route('/hub_servicos')
@login_required
def hub_servicos():
    eventos_futuros = Evento.query.filter(Evento.data_evento >= datetime.now(timezone.utc)).order_by(Evento.data_evento.asc()).limit(3).all()
    return render_template('hub_servicos.html', eventos_futuros=eventos_futuros)

@app.route('/eventos')
@login_required
def eventos():
    todos_eventos = Evento.query.order_by(Evento.data_evento.asc()).all()
    return render_template('eventos.html', eventos=todos_eventos)

@app.route('/evento/<int:evento_id>')
@login_required
def detalhe_evento(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    ja_inscrito = evento in g.user.eventos_inscritos.all()
    return render_template('detalhe_evento.html', evento=evento, ja_inscrito=ja_inscrito)

@app.route('/evento/<int:evento_id>/inscrever', methods=['POST'])
@login_required
def inscrever_evento(evento_id):
    evento = Evento.query.get_or_404(evento_id)
    if evento in g.user.eventos_inscritos.all(): flash('Você já está inscrito neste evento.', 'info')
    elif evento.vagas_restantes <= 0: flash('Vagas esgotadas para este evento!', 'danger')
    else:
        g.user.eventos_inscritos.append(evento)
        if g.user.eventos_inscritos.count() == 1: award_badge(g.user, 'Participante Ativo')
        if g.user.eventos_inscritos.count() == 5: award_badge(g.user, 'Entusiasta de Eventos')
        db.session.commit()
        flash('Inscrição realizada com sucesso!', 'success')
    return redirect(url_for('detalhe_evento', evento_id=evento_id))

# --- 7. NOVAS ROTAS PARA CLUBES ---
@app.route('/clube/<int:clube_id>/join', methods=['POST'])
@login_required
def join_club(clube_id):
    clube = Clube.query.get_or_404(clube_id)
    if clube not in g.user.clubes_membro:
        g.user.clubes_membro.append(clube)
        if g.user.clubes_membro.count() == 1: award_badge(g.user, 'Explorador de Clubes')
        if g.user.clubes_membro.count() == 3: award_badge(g.user, 'Socialite do Campus')
        db.session.commit()
        flash(f'Bem-vindo ao {clube.nome}!', 'success')
    return redirect(url_for('detalhe_clube', clube_id=clube_id))

@app.route('/clube/<int:clube_id>/leave', methods=['POST'])
@login_required
def leave_club(clube_id):
    clube = Clube.query.get_or_404(clube_id)
    if clube in g.user.clubes_membro:
        g.user.clubes_membro.remove(clube)
        db.session.commit()
        flash(f'Você saiu do {clube.nome}.', 'info')
    return redirect(url_for('detalhe_clube', clube_id=clube_id))

@app.route('/clube/<int:clube_id>/criar_evento', methods=['GET', 'POST'])
@login_required
@club_leader_required()
def criar_evento_clube(clube_id):
    clube = Clube.query.get_or_404(clube_id)
    if request.method == 'POST':
        titulo, descricao = request.form.get('titulo'), request.form.get('descricao')
        vagas = request.form.get('vagas', type=int)
        data_str = request.form.get('data_evento')
        try:
            data_evento = datetime.fromisoformat(data_str).replace(tzinfo=timezone.utc)
            if titulo and descricao and vagas and data_evento:
                novo_evento = Evento(titulo=titulo, descricao=descricao, vagas=vagas, data_evento=data_evento, clube_organizador=clube)
                noticia = Noticia(titulo=f"Novo Evento: {titulo}", conteudo=f"O {clube.nome} anunciou um novo evento para {data_evento.strftime('%d/%m/%Y às %H:%M')}. {descricao}", evento=novo_evento)
                db.session.add_all([novo_evento, noticia])
                db.session.commit()
                award_badge(g.user, 'Organizador de Eventos')
                flash('Evento criado e divulgado com sucesso!', 'success')
                return redirect(url_for('detalhe_evento', evento_id=novo_evento.id))
        except (ValueError, TypeError): flash('Dados inválidos. Verifique a data e os outros campos.', 'danger')
    return render_template('criar_evento.html', clube=clube)

# --- 8. ROTAS DE FÓRUM, MÍDIA E SERVIÇOS ---
@app.route('/clube/<int:clube_id>/forum')
@login_required
@club_member_required()
def clube_forum(clube_id):
    clube = Clube.query.get_or_404(clube_id)
    topicos = clube.forum_topicos.order_by(ForumTopico.data_criacao.desc()).all()
    return render_template('clube_forum.html', clube=clube, topicos=topicos)

@app.route('/clube/<int:clube_id>/forum/novo', methods=['GET', 'POST'])
@login_required
@club_member_required()
def clube_criar_topico(clube_id):
    clube = Clube.query.get_or_404(clube_id)
    if request.method == 'POST':
        titulo, conteudo = request.form.get('titulo'), request.form.get('conteudo')
        if titulo and conteudo:
            novo_topico = ForumTopico(titulo=titulo, conteudo=conteudo, autor=g.user, clube=clube)
            db.session.add(novo_topico)
            db.session.commit()
            award_badge(g.user, 'Pioneiro do Fórum')
            flash('Tópico criado com sucesso!', 'success')
            return redirect(url_for('clube_detalhe_topico', clube_id=clube.id, topico_id=novo_topico.id))
    return render_template('clube_criar_topico.html', clube=clube)

@app.route('/clube/<int:clube_id>/forum/topico/<int:topico_id>', methods=['GET', 'POST'])
@login_required
@club_member_required()
def clube_detalhe_topico(clube_id, topico_id):
    clube = Clube.query.get_or_404(clube_id)
    topico = ForumTopico.query.filter_by(id=topico_id, clube_id=clube.id).first_or_404()
    if request.method == 'POST':
        if conteudo := request.form.get('conteudo'):
            novo_post = ForumPost(conteudo=conteudo, autor=g.user, topico=topico)
            db.session.add(novo_post)
            db.session.commit()
            flash('Resposta adicionada!', 'success')
            return redirect(url_for('clube_detalhe_topico', clube_id=clube.id, topico_id=topico.id))
    posts = topico.posts.order_by(ForumPost.data_criacao.asc()).all()
    return render_template('clube_detalhe_topico.html', topico=topico, posts=posts, clube=clube)

@app.route('/clube/<int:clube_id>/media', methods=['GET', 'POST'])
@login_required
@club_member_required()
def clube_media(clube_id):
    clube = Clube.query.get_or_404(clube_id)
    if request.method == 'POST':
        if g.user.id != clube.lider_id: flash('Apenas o líder do clube pode enviar arquivos.', 'danger')
        elif 'media_file' not in request.files or request.files['media_file'].filename == '': flash('Nenhum arquivo selecionado.', 'warning')
        else:
            file = request.files['media_file']
            if allowed_file(file.filename, ALLOWED_MEDIA_EXTENSIONS):
                ext = os.path.splitext(file.filename)[1]
                filename = secure_filename(f"clube{clube.id}_{uuid.uuid4().hex}{ext}")
                file.save(os.path.join(app.config['CLUB_MEDIA_FOLDER'], filename))
                nova_media = ClubeMedia(filename=filename, descricao=request.form.get('descricao'), clube=clube, uploader=g.user)
                db.session.add(nova_media)
                db.session.commit()
                flash('Arquivo enviado com sucesso!', 'success')
            else: flash(f"Tipo de arquivo inválido. Permitidos: {', '.join(ALLOWED_MEDIA_EXTENSIONS)}", 'danger')
        return redirect(url_for('clube_media', clube_id=clube_id))
    media_files = clube.media_files.order_by(ClubeMedia.data_upload.desc()).all()
    return render_template('clube_media.html', clube=clube, media_files=media_files)

@app.route('/cardapio')
@login_required
def cardapio():
    hoje = date.today()
    start_of_week = hoje - timedelta(days=hoje.weekday())
    cardapio_semana_obj = CardapioRU.query.filter(CardapioRU.data >= start_of_week).order_by(CardapioRU.data.asc()).limit(7).all()
    cardapio_semana = {item.data.weekday(): item for item in cardapio_semana_obj}
    return render_template('cardapio_ru.html', cardapio_semana=cardapio_semana, start_of_week=start_of_week)

@app.route('/calendario_academico')
@login_required
def calendario_academico():
    hoje = date.today()
    eventos = CalendarioAcademico.query.filter(CalendarioAcademico.data >= hoje).order_by(CalendarioAcademico.data.asc()).all()
    return render_template('calendario_academico.html', eventos=eventos)

# --- 9. COMANDO PARA POPULAR O BANCO ---
@app.cli.command('seed-db')
def seed_db_command():
    print("Limpando tabelas existentes...")
    db.drop_all()
    db.create_all()
    print("Criando selos (badges)...")
    badges = [
        Badge(nome='Membro Pioneiro', descricao='Um dos 10 primeiros usuários a se registrar na plataforma.', icon_class='fas fa-rocket'),
        Badge(nome='Explorador de Clubes', descricao='Entrou no seu primeiro clube.', icon_class='fas fa-compass'),
        Badge(nome='Socialite do Campus', descricao='Membro de 3 ou mais clubes.', icon_class='fas fa-users'),
        Badge(nome='Participante Ativo', descricao='Inscreveu-se no seu primeiro evento.', icon_class='fas fa-calendar-check'),
        Badge(nome='Entusiasta de Eventos', descricao='Participou de 5 ou mais eventos.', icon_class='fas fa-star'),
        Badge(nome='Organizador de Eventos', descricao='Liderou um clube e criou um evento.', icon_class='fas fa-bullhorn'),
        Badge(nome='Pioneiro do Fórum', descricao='Criou seu primeiro tópico em um fórum.', icon_class='fas fa-feather-alt')]
    db.session.add_all(badges)
    db.session.commit()

    print("Criando usuários de exemplo...")
    u1 = User(email='lider.prog@ifpb.edu.br', username='202511110001', password_hash=generate_password_hash('123456'))
    u2 = User(email='membro.comum@ifpb.edu.br', username='202511110002', password_hash=generate_password_hash('123456'))
    u3 = User(email='lider.teatro@ifpb.edu.br', username='202522220001', password_hash=generate_password_hash('123456'))
    db.session.add_all([u1, u2, u3])
    db.session.commit()

    award_badge(u1, 'Membro Pioneiro', show_flash=False)
    award_badge(u2, 'Membro Pioneiro', show_flash=False)
    award_badge(u3, 'Membro Pioneiro', show_flash=False)
    
    print("Criando clubes...")
    clube_prog = Clube(nome='Clube de Programação', descricao='Para entusiastas de código, desenvolvimento de software e competições.', categoria='Tecnologia', lider_id=u1.id)
    clube_teatro = Clube(nome='Clube de Teatro', descricao='Explore a arte da atuação, expressão corporal e montagem de peças.', categoria='Arte & Cultura', lider_id=u3.id)
    clube_esportes = Clube(nome='Clube de Esportes', descricao='Organização de treinos e campeonatos de diversas modalidades.', categoria='Esportes')
    clube_robotica = Clube(nome='Clube de Robótica', descricao='Construção e programação de robôs para desafios e aprendizado.', categoria='Tecnologia')
    clube_literatura = Clube(nome='Clube de Literatura', descricao='Leituras, debates e análises de obras clássicas e contemporâneas.', categoria='Arte & Cultura')
    db.session.add_all([clube_prog, clube_teatro, clube_esportes, clube_robotica, clube_literatura])
    db.session.commit()

    clube_prog.membros.extend([u1, u2])
    clube_teatro.membros.extend([u3, u2])
    clube_robotica.membros.append(u1)
    clube_literatura.membros.append(u2)
    db.session.commit()
    
    award_badge(u1, 'Explorador de Clubes', show_flash=False)
    award_badge(u2, 'Explorador de Clubes', show_flash=False)
    award_badge(u3, 'Explorador de Clubes', show_flash=False)
    
    print("Criando eventos e notícias...")
    # Eventos Futuros
    e1 = Evento(titulo='Maratona de Programação', descricao='Resolva desafios de programação em equipe.', vagas=50, clube_id=clube_prog.id, data_evento=datetime(2025, 9, 10, 9, 0, 0, tzinfo=timezone.utc))
    e2 = Evento(titulo='Oficina de Arduino', descricao='Aprenda os primeiros passos com a plataforma Arduino.', vagas=25, clube_id=clube_robotica.id, data_evento=datetime(2025, 9, 22, 14, 0, 0, tzinfo=timezone.utc))
    e3 = Evento(titulo='Debate sobre "1984"', descricao='Análise da obra de George Orwell e suas implicações atuais.', vagas=30, clube_id=clube_literatura.id, data_evento=datetime(2025, 10, 5, 18, 30, 0, tzinfo=timezone.utc))
    # Evento Passado
    e_passado = Evento(titulo='Apresentação Teatral de Verão', descricao='Performance da peça "Sonho de uma Noite de Verão".', vagas=100, clube_id=clube_teatro.id, data_evento=datetime(2025, 7, 20, 19, 0, 0, tzinfo=timezone.utc))
    db.session.add_all([e1, e2, e3, e_passado])
    db.session.commit()

    # Notícias
    n1 = Noticia(titulo='Inscrições Abertas para a Maratona de Programação!', conteudo='As inscrições para a maratona de programação já começaram. Monte sua equipe e participe!', evento_id=e1.id)
    n2 = Noticia(titulo='Edital de Monitoria 2025.2', conteudo='Estão abertas as inscrições para o programa de monitoria. Os interessados devem procurar a coordenação do seu curso para mais informações sobre vagas e disciplinas disponíveis.')
    n3 = Noticia(titulo='Vem aí a Oficina de Arduino!', conteudo='O Clube de Robótica convida a todos para uma oficina prática e introdutória sobre a plataforma Arduino. Não é necessário conhecimento prévio!', evento_id=e2.id)
    n4 = Noticia(titulo='Novo Horário da Biblioteca', conteudo='Atenção, estudantes! A partir da próxima semana, a biblioteca funcionará em horário estendido, das 7h30 às 21h30, de segunda a sexta.')
    n5 = Noticia(titulo='Relembre: Sucesso na Apresentação Teatral', conteudo='O Clube de Teatro agradece a presença de todos na incrível apresentação da peça "Sonho de uma Noite de Verão" que ocorreu no mês passado. Foi um sucesso de público e crítica!', evento_id=e_passado.id)
    db.session.add_all([n1, n2, n3, n4, n5])
    db.session.commit()
    
    award_badge(u1, 'Organizador de Eventos', show_flash=False)
    
    print("Criando cardápio e calendário...")
    hoje = date.today()
    start_of_week = hoje - timedelta(days=hoje.weekday())
    for i in range(5):
        menu = CardapioRU(data=start_of_week + timedelta(days=i), prato_principal='Frango Grelhado com Arroz e Feijão', vegetariano='Torta de Legumes', acompanhamento='Batata Doce Assada', salada='Mix de Folhas com Tomate', sobremesa='Fruta da Estação')
        db.session.add(menu)
    cal_events = [
        CalendarioAcademico(data=date(2025, 8, 15), descricao="Início do Semestre Letivo 2025.2", tipo="Acadêmico"),
        CalendarioAcademico(data=date(2025, 9, 7), descricao="Feriado Nacional - Independência do Brasil", tipo="Feriado")]
    db.session.add_all(cal_events)
    db.session.commit()
    print("Banco de dados populado com sucesso!")

if __name__ == '__main__':
    app.run(debug=True)
