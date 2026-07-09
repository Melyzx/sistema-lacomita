from flask import Flask, send_from_directory, request, jsonify, send_file
from flask_socketio import SocketIO, emit
import sqlite3
import json
import uuid
import os
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='.')
app.config['SECRET_KEY'] = 'lacomita_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*")

UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

DB_FILE = 'lacomita.db'
CHAVE_MESTRA = "caiovetormestremacho62932405"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                    login TEXT PRIMARY KEY, senha TEXT, nome TEXT, foto TEXT, papel TEXT, 
                    pv INTEGER, max_pv INTEGER, san INTEGER, max_san INTEGER, 
                    fome BOOLEAN DEFAULT 1, sede BOOLEAN DEFAULT 1, 
                    dias_fome INTEGER DEFAULT 0, dias_sede INTEGER DEFAULT 0,
                    anotacoes TEXT DEFAULT '', classificacao TEXT DEFAULT 'Aliado', 
                    sub_classificacao TEXT DEFAULT 'Jogador', ocultar_status BOOLEAN DEFAULT 0, 
                    mascara_pv INTEGER DEFAULT 0, mascara_san INTEGER DEFAULT 0, 
                    mascara_detalhes TEXT DEFAULT '', estados_ativos TEXT DEFAULT '[]', 
                    defesa INTEGER DEFAULT 10, no_tabuleiro BOOLEAN DEFAULT 0
                )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS templates_itens (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, imagem TEXT, dano TEXT, efeitos TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS inventario (id INTEGER PRIMARY KEY AUTOINCREMENT, dono_login TEXT, nome TEXT, imagem TEXT, dano TEXT, efeitos TEXT, equipado BOOLEAN DEFAULT 0, FOREIGN KEY(dono_login) REFERENCES usuarios(login))''')
    c.execute('''CREATE TABLE IF NOT EXISTS templates_ataques (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, dano TEXT, custo_san INTEGER, efeitos TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS ataques (id INTEGER PRIMARY KEY AUTOINCREMENT, dono_login TEXT, nome TEXT, dano TEXT, custo_san INTEGER, efeitos TEXT, FOREIGN KEY(dono_login) REFERENCES usuarios(login))''')
    c.execute('''CREATE TABLE IF NOT EXISTS campanha (id INTEGER PRIMARY KEY, dia INTEGER, periodo TEXT DEFAULT 'Vigília', rodada INTEGER, modo_batalha BOOLEAN, evento_ativo BOOLEAN, evento_texto TEXT, turno_atual TEXT, ordem_turnos TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS registro_mundial (id INTEGER PRIMARY KEY AUTOINCREMENT, json_data TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS base_upgrades (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT, imagem TEXT, descricao TEXT, desbloqueado BOOLEAN DEFAULT 0)''')

    # Migrações seguras - Tabela Usuarios
    colunas_existentes = [col[1] for col in c.execute("PRAGMA table_info(usuarios)").fetchall()]
    if 'dias_fome' not in colunas_existentes: c.execute("ALTER TABLE usuarios ADD COLUMN dias_fome INTEGER DEFAULT 0")
    if 'dias_sede' not in colunas_existentes: c.execute("ALTER TABLE usuarios ADD COLUMN dias_sede INTEGER DEFAULT 0")
    if 'defesa' not in colunas_existentes: c.execute("ALTER TABLE usuarios ADD COLUMN defesa INTEGER DEFAULT 10")
    if 'no_tabuleiro' not in colunas_existentes: c.execute("ALTER TABLE usuarios ADD COLUMN no_tabuleiro BOOLEAN DEFAULT 0")
    
    # Migrações seguras - Tabela Campanha (O ERRO ESTAVA AQUI!)
    colunas_campanha = [col[1] for col in c.execute("PRAGMA table_info(campanha)").fetchall()]
    if 'periodo' not in colunas_campanha:
        c.execute("ALTER TABLE campanha ADD COLUMN periodo TEXT DEFAULT 'Vigília'")
    else:
        c.execute("UPDATE campanha SET periodo = 'Vigília' WHERE periodo = 'Dia'")

    if not c.execute("SELECT login FROM usuarios WHERE login = 'mestre'").fetchone():
        c.execute("INSERT INTO usuarios (login, senha, nome, papel, foto, ocultar_status, defesa, no_tabuleiro) VALUES ('mestre', ?, 'Controle Central', 'mestre', 'simbolo.png', 0, 10, 0)", (CHAVE_MESTRA,))
    if not c.execute("SELECT id FROM campanha WHERE id = 1").fetchone():
        c.execute("INSERT INTO campanha (id, dia, periodo, rodada, modo_batalha, evento_ativo, evento_texto, turno_atual, ordem_turnos) VALUES (1, 1, 'Vigília', 0, 0, 0, '', 'Livre', '[]')")
    
    conn.commit(); conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(DB_FILE); conn.row_factory = sqlite3.Row; return conn

@app.route('/uploads/<filename>')
def serve_upload(filename): return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/')
def index(): return send_from_directory('.', 'login.html')

@app.route('/<path:path>')
def serve_html(path): return send_from_directory('.', path)

@app.route('/api/backup', methods=['GET'])
def backup_db():
    try: return send_file(DB_FILE, as_attachment=True, download_name=f"lacomita_backup_{datetime.now().strftime('%d-%m-%Y_%H-%M')}.db")
    except Exception as e: return str(e)

@app.route('/api/restore', methods=['POST'])
def restore_db():
    if 'database' not in request.files: return jsonify({"sucesso": False, "erro": "Nenhum arquivo enviado"}), 400
    file = request.files['database']
    if file and file.filename.endswith('.db'):
        file.save(DB_FILE); init_db(); socketio.emit('personagens_atualizados', broadcast=True)
        return jsonify({"sucesso": True})
    return jsonify({"sucesso": False, "erro": "O arquivo tem que ser .db"}), 400

@app.route('/api/upload-foto', methods=['POST'])
def upload_foto():
    if 'foto' not in request.files: return jsonify({"sucesso": False, "erro": "Nenhum arquivo enviado"}), 400
    file = request.files['foto']; identificador = request.form.get('login') or 'upg'
    if file.filename == '': return jsonify({"sucesso": False, "erro": "Nenhum arquivo selecionado"}), 400
    if file:
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'png'
        nome_seguro = secure_filename(f"img_{identificador}_{uuid.uuid4().hex[:6]}.{ext}")
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], nome_seguro))
        caminho_web = f"/uploads/{nome_seguro}"
        
        if identificador != 'upg' and identificador != 'item':
            conn = get_db(); conn.execute("UPDATE usuarios SET foto = ? WHERE login = ?", (caminho_web, identificador)); conn.commit(); conn.close()
            socketio.emit('status_atualizado', {"login": identificador, "tipo": "foto", "valor": caminho_web}, broadcast=True)
            socketio.emit('personagens_atualizados', broadcast=True)
        return jsonify({"sucesso": True, "foto": caminho_web})

@app.route('/api/login', methods=['POST'])
def login():
    dados = request.json; conn = get_db()
    if dados.get('role') == 'mestre':
        user = conn.execute("SELECT * FROM usuarios WHERE login = 'mestre' AND senha = ?", (dados.get('senha'),)).fetchone()
        if user: return jsonify({"sucesso": True, "redirect": "mestre.html", "user": {"login": "mestre", "papel": "mestre", "nome": "Mestre Supremo", "foto": user['foto']}})
        return jsonify({"sucesso": False, "erro": "Chave mestra inválida."})
    else:
        user = conn.execute("SELECT * FROM usuarios WHERE login = ? AND senha = ? AND papel = 'agente'", (dados.get('login').lower(), dados.get('senha'))).fetchone()
        if user: u = dict(user); del u['senha']; return jsonify({"sucesso": True, "redirect": "agente.html", "user": u})
        return jsonify({"sucesso": False, "erro": "Operador não encontrado ou senha incorreta."})

@app.route('/api/registrar', methods=['POST'])
def registrar():
    dados = request.json; login_user = dados.get('login','').lower().strip(); conn = get_db()
    if not login_user: return jsonify({"sucesso": False, "erro": "Código obrigatório."})
    if conn.execute("SELECT login FROM usuarios WHERE login = ?", (login_user,)).fetchone(): return jsonify({"sucesso": False, "erro": "Código já em uso."})
    foto = dados.get('foto') or f"https://api.dicebear.com/7.x/bottts/svg?seed={login_user}"
    conn.execute(
        """INSERT INTO usuarios (login, senha, nome, foto, papel, pv, max_pv, san, max_san, fome, sede, anotacoes, ocultar_status, mascara_pv, mascara_san, mascara_detalhes, estados_ativos, defesa, no_tabuleiro) 
           VALUES (?, ?, ?, ?, 'agente', 20, 20, 50, 50, 1, 1, '', 0, 0, 0, '', '[]', 10, 1)""", 
        (login_user, dados.get('senha'), dados.get('nome'), foto)
    )
    conn.commit(); conn.close()
    return jsonify({"sucesso": True})

@app.route('/api/personagens', methods=['GET'])
def get_personagens(): return jsonify([{k: v for k, v in dict(a).items() if k != 'senha'} for a in get_db().execute("SELECT * FROM usuarios WHERE papel IN ('agente', 'npc')").fetchall()])
@app.route('/api/campanha', methods=['GET'])
def get_campanha(): return jsonify(dict(get_db().execute("SELECT * FROM campanha WHERE id = 1").fetchone()))
@app.route('/api/templates', methods=['GET'])
def get_templates(): return jsonify([dict(t) for t in get_db().execute("SELECT * FROM templates_itens").fetchall()])
@app.route('/api/templates_ataques', methods=['GET'])
def get_templates_ataques(): return jsonify([dict(t) for t in get_db().execute("SELECT * FROM templates_ataques").fetchall()])
@app.route('/api/inventario/<login>', methods=['GET'])
def get_inv(login): return jsonify([dict(i) for i in get_db().execute("SELECT * FROM inventario WHERE dono_login = ?", (login,)).fetchall()])
@app.route('/api/ataques/<login>', methods=['GET'])
def get_ataques(login): return jsonify([dict(a) for a in get_db().execute("SELECT * FROM ataques WHERE dono_login = ?", (login,)).fetchall()])
@app.route('/api/logs', methods=['GET'])
def get_logs(): return jsonify([json.loads(l['json_data']) for l in get_db().execute("SELECT json_data FROM registro_mundial ORDER BY id DESC LIMIT 60").fetchall()])
@app.route('/api/upgrades', methods=['GET'])
def get_upgrades(): return jsonify([dict(u) for u in get_db().execute("SELECT * FROM base_upgrades").fetchall()])

# --- WEBSOCKETS ---
@socketio.on('connect')
def connect(): pass

@socketio.on('enviar_rolagem')
def handle_rolagem(dados):
    dados['timestamp'] = datetime.now().strftime("%H:%M | %d/%m")
    conn = get_db(); conn.execute("INSERT INTO registro_mundial (json_data) VALUES (?)", (json.dumps(dados),)); conn.commit(); conn.close()
    emit('receber_rolagem', dados, broadcast=True)

CAMPOS_STATUS_PERMITIDOS = {
    'pv', 'max_pv', 'san', 'max_san', 'fome', 'sede', 'ocultar_status', 
    'anotacoes', 'mascara_pv', 'mascara_san', 'mascara_detalhes', 'estados_ativos',
    'nome', 'foto', 'classificacao', 'sub_classificacao', 'defesa', 'no_tabuleiro'
}

@socketio.on('atualizar_status')
def handle_status(dados):
    tipo = dados.get('tipo')
    if tipo not in CAMPOS_STATUS_PERMITIDOS: return
    conn = get_db(); conn.execute(f"UPDATE usuarios SET {tipo} = ? WHERE login = ?", (dados['valor'], dados['login'])); conn.commit(); conn.close()
    emit('status_atualizado', dados, broadcast=True)

@socketio.on('atualizar_campanha')
def handle_campanha(dados):
    conn = get_db(); conn.execute(f"UPDATE campanha SET {dados['campo']} = ? WHERE id = 1", (dados['valor'],)); conn.commit(); conn.close()
    emit('campanha_atualizada', dados, broadcast=True)

@socketio.on('avancar_dia')
def avancar_dia():
    conn = get_db()
    camp = dict(conn.execute("SELECT * FROM campanha WHERE id = 1").fetchone())
    novo_dia = camp['dia'] + 1
    agentes = conn.execute("SELECT * FROM usuarios WHERE papel = 'agente'").fetchall()
    
    for ag in agentes:
        dias_f = ag['dias_fome']
        dias_s = ag['dias_sede']
        fome_ok = ag['fome']
        sede_ok = ag['sede']
        pv = ag['pv']
        max_pv = ag['max_pv']
        san = ag['san']
        max_san = ag['max_san']
        log_msg = ""
        
        if not fome_ok and not sede_ok:
            dias_f += 1
            dias_s += 1
            if dias_f > 1 or dias_s > 1:
                pv = 0
                log_msg = f"💀 {ag['nome']} MORREU DE PRIVAÇÃO EXTREMA (Ignorou fome e sede mais de 1 dia)."
            else:
                pv -= 10; max_pv -= 10; san -= 10; max_san -= 10
                log_msg = f"⚠️ {ag['nome']} ignorou Fome e Sede! Entrou em PRIVAÇÃO (-10 PV/SAN Atuais e Máximos)."
        elif not fome_ok:
            dias_f += 1
            dias_s = 0
            if dias_f >= 3:
                pv = 0
                log_msg = f"💀 {ag['nome']} MORREU DE INANIÇÃO (3 dias sem comida)."
            else:
                pv -= 5; max_pv -= 5; san -= 5; max_san -= 5
                log_msg = f"⚠️ {ag['nome']} ignorou a Fome! Está FAMINTO (-5 PV/SAN Atuais e Máximos)."
        elif not sede_ok:
            dias_s += 1
            dias_f = 0
            if dias_s >= 2:
                pv = 0
                log_msg = f"💀 {ag['nome']} MORREU DE DESIDRATAÇÃO (2 dias sem água)."
            else:
                pv -= 5; max_pv -= 5; san -= 5; max_san -= 5
                log_msg = f"⚠️ {ag['nome']} ignorou a Sede! Está DESIDRATADO (-5 PV/SAN Atuais e Máximos)."
        else:
            dias_f = 0
            dias_s = 0
            log_msg = f"✅ {ag['nome']} alimentou-se e hidratou-se corretamente. Sobreviveu."
            
        if pv < 0: pv = 0
        if san < 0: san = 0
        if max_pv < 1: max_pv = 1
        if max_san < 1: max_san = 1
        
        conn.execute("UPDATE usuarios SET pv=?, max_pv=?, san=?, max_san=?, dias_fome=?, dias_sede=?, fome=0, sede=0 WHERE login=?", (pv, max_pv, san, max_san, dias_f, dias_s, ag['login']))
        
        if log_msg:
            log_dados = { "timestamp": datetime.now().strftime("%H:%M | %d/%m"), "jogador": "SISTEMA DE SOBREVIVÊNCIA", "qtd": 0, "faces": 0, "total": "ALERTA", "resultados": [], "razao": log_msg }
            conn.execute("INSERT INTO registro_mundial (json_data) VALUES (?)", (json.dumps(log_dados),))
            emit('receber_rolagem', log_dados, broadcast=True)

    conn.execute("UPDATE campanha SET dia = ?, periodo = 'Vigília' WHERE id = 1", (novo_dia,))
    conn.commit(); conn.close()
    
    emit('campanha_atualizada', {'campo': 'dia', 'valor': novo_dia}, broadcast=True)
    emit('campanha_atualizada', {'campo': 'periodo', 'valor': 'Vigília'}, broadcast=True)
    emit('necessidades_resetadas', broadcast=True)
    emit('personagens_atualizados', broadcast=True)

@socketio.on('atualizar_evento')
def handle_evento(dados): conn = get_db(); conn.execute("UPDATE campanha SET evento_ativo = ?, evento_texto = ? WHERE id = 1", (dados['ativo'], dados['texto'])); conn.commit(); conn.close(); emit('evento_atualizado', dados, broadcast=True)

@socketio.on('salvar_ordem_turnos')
def salvar_ordem(ordem_array): conn = get_db(); conn.execute("UPDATE campanha SET ordem_turnos = ? WHERE id = 1", (json.dumps(ordem_array),)); conn.commit(); conn.close(); emit('ordem_turnos_atualizada', ordem_array, broadcast=True)

@socketio.on('passar_turno')
def passar_turno():
    conn = get_db()
    camp = dict(conn.execute("SELECT * FROM campanha WHERE id = 1").fetchone())
    ordem = json.loads(camp['ordem_turnos']) if camp['ordem_turnos'] else []
    if not ordem: return 
    
    atual = camp['turno_atual']
    try: next_idx = (ordem.index(atual) + 1) % len(ordem)
    except ValueError: next_idx = 0
    next_turno = ordem[next_idx]

    user = conn.execute("SELECT * FROM usuarios WHERE login = ?", (next_turno,)).fetchone()
    if user and user['estados_ativos']:
        estados = json.loads(user['estados_ativos'])
        if estados:
            novo_pv = user['pv']; novo_san = user['san']
            logs_gerados = []; estados_restantes = []

            for e in estados:
                if e['duracao'] > 0:
                    if e['tipo'] == 'pv': novo_pv += e['valor']
                    elif e['tipo'] == 'san': novo_san += e['valor']
                    acao = "recuperou" if e['valor'] > 0 else "perdeu"
                    logs_gerados.append(f"{user['nome']} {acao} {abs(e['valor'])} {e['tipo'].upper()} devido a {e['nome']}.")
                    e['duracao'] -= 1
                if e['duracao'] > 0: estados_restantes.append(e)
            
            if novo_pv < 0: novo_pv = 0
            if novo_san < 0: novo_san = 0

            conn.execute("UPDATE usuarios SET pv = ?, san = ?, estados_ativos = ? WHERE login = ?", (novo_pv, novo_san, json.dumps(estados_restantes), next_turno))
            for msg in logs_gerados:
                log_dados = { "timestamp": datetime.now().strftime("%H:%M | %d/%m"), "jogador": "SISTEMA", "qtd": 0, "faces": 0, "total": "EFEITO", "resultados": [], "razao": msg }
                conn.execute("INSERT INTO registro_mundial (json_data) VALUES (?)", (json.dumps(log_dados),))
                emit('receber_rolagem', log_dados, broadcast=True)
    
    if next_idx == 0 and len(ordem) > 0 and camp['modo_batalha']:
        nova_rodada = camp['rodada'] + 1
        conn.execute("UPDATE campanha SET turno_atual = ?, rodada = ? WHERE id = 1", (next_turno, nova_rodada))
        conn.commit(); emit('campanha_atualizada', {'campo': 'rodada', 'valor': nova_rodada}, broadcast=True); emit('campanha_atualizada', {'campo': 'turno_atual', 'valor': next_turno}, broadcast=True)
    else:
        conn.execute("UPDATE campanha SET turno_atual = ? WHERE id = 1", (next_turno,))
        conn.commit(); emit('campanha_atualizada', {'campo': 'turno_atual', 'valor': next_turno}, broadcast=True)
    conn.close(); emit('personagens_atualizados', broadcast=True)

@socketio.on('criar_npc')
def criar_npc(dados):
    conn = get_db()
    if dados.get('login'): conn.execute("UPDATE usuarios SET nome=?, foto=?, pv=?, max_pv=?, san=?, max_san=?, defesa=?, classificacao=?, sub_classificacao=? WHERE login=?", (dados['nome'], dados['foto'], dados['pv'], dados['pv'], dados['san'], dados['san'], dados['defesa'], dados['classificacao'], dados['sub_classificacao'], dados['login']))
    else:
        login_npc = "npc_" + str(uuid.uuid4())[:8]
        foto = dados.get('foto') or f"https://api.dicebear.com/7.x/bottts/svg?seed={login_npc}"
        conn.execute("""INSERT INTO usuarios (login, nome, foto, papel, pv, max_pv, san, max_san, defesa, classificacao, sub_classificacao, ocultar_status, estados_ativos, no_tabuleiro) VALUES (?, ?, ?, 'npc', ?, ?, ?, ?, ?, ?, ?, 0, '[]', 0)""", (login_npc, dados['nome'], foto, dados['pv'], dados['pv'], dados['san'], dados['san'], dados['defesa'], dados['classificacao'], dados['sub_classificacao']))
    conn.commit(); conn.close(); emit('personagens_atualizados', broadcast=True)

@socketio.on('remover_npc')
def remover_npc(login): conn = get_db(); conn.execute("DELETE FROM usuarios WHERE login = ?", (login,)); conn.commit(); conn.close(); emit('personagens_atualizados', broadcast=True)
@socketio.on('criar_template_item')
def criar_template(dados): conn = get_db(); conn.execute("UPDATE templates_itens SET nome=?, imagem=?, dano=?, efeitos=? WHERE id=?" if dados.get('id') else "INSERT INTO templates_itens (nome, imagem, dano, efeitos) VALUES (?, ?, ?, ?)", (dados['nome'], dados['imagem'], dados['dano'], dados['efeitos'], dados['id']) if dados.get('id') else (dados['nome'], dados['imagem'], dados['dano'], dados['efeitos'])); conn.commit(); conn.close(); emit('templates_atualizados', broadcast=True)
@socketio.on('remover_template_item')
def remover_template_item(dados): conn = get_db(); conn.execute("DELETE FROM templates_itens WHERE id = ?", (dados['id'],)); conn.commit(); conn.close(); emit('templates_atualizados', broadcast=True)
@socketio.on('atribuir_item_template')
def atribuir_item(dados): conn = get_db(); temp = conn.execute("SELECT * FROM templates_itens WHERE id = ?", (dados['template_id'],)).fetchone(); conn.execute("INSERT INTO inventario (dono_login, nome, imagem, dano, efeitos, equipado) VALUES (?, ?, ?, ?, ?, 0)", (dados['login'], temp['nome'], temp['imagem'], temp['dano'], temp['efeitos'])) if temp else None; conn.commit(); emit('inventario_atualizado', dados['login'], broadcast=True); conn.close()
@socketio.on('equipar_arma')
def equipar_arma(dados): conn = get_db(); conn.execute("UPDATE inventario SET equipado = 0 WHERE dono_login = ?", (dados['login'],)); conn.execute("UPDATE inventario SET equipado = 1 WHERE id = ?", (dados['item_id'],)) if dados.get('item_id') else None; conn.commit(); conn.close(); emit('inventario_atualizado', dados['login'], broadcast=True)
@socketio.on('transferir_item')
def transferir_item(dados): conn = get_db(); conn.execute("UPDATE inventario SET dono_login = ?, equipado = 0 WHERE id = ?", (dados['para_login'], dados['item_id'])); conn.commit(); emit('inventario_atualizado', dados['de_login'], broadcast=True); emit('inventario_atualizado', dados['para_login'], broadcast=True); conn.close()
@socketio.on('remover_item')
def remover_item(dados): conn = get_db(); conn.execute("DELETE FROM inventario WHERE id = ?", (dados['item_id'],)); conn.commit(); emit('inventario_atualizado', dados['login'], broadcast=True)
@socketio.on('criar_template_ataque')
def criar_template_ataque(dados): conn = get_db(); conn.execute("UPDATE templates_ataques SET nome=?, dano=?, custo_san=?, efeitos=? WHERE id=?" if dados.get('id') else "INSERT INTO templates_ataques (nome, dano, custo_san, efeitos) VALUES (?, ?, ?, ?)", (dados['nome'], dados['dano'], dados['custo_san'], dados['efeitos'], dados['id']) if dados.get('id') else (dados['nome'], dados['dano'], dados['custo_san'], dados['efeitos'])); conn.commit(); conn.close(); emit('templates_ataques_atualizados', broadcast=True)
@socketio.on('remover_template_ataque')
def remover_template_ataque(dados): conn = get_db(); conn.execute("DELETE FROM templates_ataques WHERE id = ?", (dados['id'],)); conn.commit(); conn.close(); emit('templates_ataques_atualizados', broadcast=True)
@socketio.on('atribuir_ataque_template')
def atribuir_ataque(dados): conn = get_db(); temp = conn.execute("SELECT * FROM templates_ataques WHERE id = ?", (dados['template_id'],)).fetchone(); conn.execute("INSERT INTO ataques (dono_login, nome, dano, custo_san, efeitos) VALUES (?, ?, ?, ?, ?)", (dados['login'], temp['nome'], temp['dano'], temp['custo_san'], temp['efeitos'])) if temp else None; conn.commit(); emit('ataques_atualizados', dados['login'], broadcast=True); conn.close()
@socketio.on('remover_ataque')
def remover_ataque(dados): conn = get_db(); conn.execute("DELETE FROM ataques WHERE id = ?", (dados['ataque_id'],)); conn.commit(); conn.close(); emit('ataques_atualizados', dados['login'], broadcast=True)
@socketio.on('toggle_mascara')
def toggle_mascara(dados): emit('mascara_forcada', dados, broadcast=True)

@socketio.on('criar_upgrade')
def criar_upgrade(dados):
    conn = get_db()
    if dados.get('id'): conn.execute("UPDATE base_upgrades SET nome=?, imagem=?, descricao=? WHERE id=?", (dados['nome'], dados['imagem'], dados['descricao'], dados['id']))
    else: conn.execute("INSERT INTO base_upgrades (nome, imagem, descricao) VALUES (?, ?, ?)", (dados['nome'], dados['imagem'], dados['descricao']))
    conn.commit(); conn.close(); emit('upgrades_atualizados', broadcast=True)

@socketio.on('remover_upgrade')
def remover_upgrade(id_upg): conn = get_db(); conn.execute("DELETE FROM base_upgrades WHERE id = ?", (id_upg,)); conn.commit(); conn.close(); emit('upgrades_atualizados', broadcast=True)

@socketio.on('toggle_upgrade')
def toggle_upgrade(dados): conn = get_db(); conn.execute("UPDATE base_upgrades SET desbloqueado = ? WHERE id = ?", (dados['valor'], dados['id'])); conn.commit(); conn.close(); emit('upgrades_atualizados', broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=8947, debug=True)
