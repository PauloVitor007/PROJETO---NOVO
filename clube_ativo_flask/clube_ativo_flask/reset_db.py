# Em reset_db.py

import os
import shutil
# Importe o app e o db do seu arquivo principal
from app import app, db

# Use o 'app_context' para garantir que as configurações do app sejam carregadas
with app.app_context():
    print("--- INICIANDO RESET TOTAL DO BANCO DE DADOS ---")

    # Pega o caminho do banco DE DENTRO da configuração do app
    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')

    # Apaga o banco de dados se ele existir
    if os.path.exists(db_path):
        os.remove(db_path)
        print(f"✅ Banco de dados em '{db_path}' foi apagado.")

    # Apaga a pasta de migrações se ela existir
    if os.path.exists('migrations'):
        shutil.rmtree('migrations')
        print("✅ Pasta 'migrations' foi apagada.")

    # Cria o novo banco de dados e tabelas
    print("⏳ Criando todas as tabelas...")
    db.create_all()  # Agora isso VAI usar o caminho correto!
    print("🎉 Banco de dados e tabelas criados com sucesso!")