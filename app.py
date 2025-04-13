import os
from flask import Flask, render_template, request, redirect, session, url_for # type: ignore
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash# type: ignore
from werkzeug.utils import secure_filename # type: ignore
app = Flask(__name__)
app.secret_key = 'super_secret_key'  # À changer en prod
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 Mo max par image
# --- DB INIT ---
def init_db():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Table utilisateurs
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL
                )''')

    # Table des dons
    c.execute('''CREATE TABLE IF NOT EXISTS donations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    location TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )''')
    
    # Table des demandes de dons
    c.execute('''CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                donation_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                status TEXT DEFAULT 'en attente',
                requested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (donation_id) REFERENCES donations(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )''')


    conn.commit()
    conn.close()


init_db()
def add_is_read_column():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE messages ADD COLUMN is_read INTEGER DEFAULT 0")
        print("✅ Colonne 'is_read' ajoutée.")
    except sqlite3.OperationalError:
        print("ℹ️ Colonne 'is_read' existe déjà.")
    conn.commit()
    conn.close()

add_is_read_column()


def create_messages_table():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            donation_id INTEGER,
            content TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users(id),
            FOREIGN KEY (receiver_id) REFERENCES users(id),
            FOREIGN KEY (donation_id) REFERENCES donations(id)
        )
    ''')
    conn.commit()
    conn.close()

create_messages_table()

def add_coords_columns():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE donations ADD COLUMN latitude REAL")
        c.execute("ALTER TABLE donations ADD COLUMN longitude REAL")
        print("✅ Colonnes latitude et longitude ajoutées.")
    except sqlite3.OperationalError:
        print("ℹ️ Colonnes déjà existantes.")
    conn.commit()
    conn.close()

add_coords_columns()

import requests

OPENCAGE_API_KEY = '3b2026fb85a74645923528f340bffcd4'

def geocode_location(location):
    url = f"https://api.opencagedata.com/geocode/v1/json?q={location}&key={OPENCAGE_API_KEY}&language=fr&limit=1"
    try:
        response = requests.get(url)
        data = response.json()
        if data['results']:
            lat = data['results'][0]['geometry']['lat']
            lng = data['results'][0]['geometry']['lng']
            return lat, lng
    except Exception as e:
        print(f"Erreur géocodage : {e}")
    return None, None


# --- ROUTES ---
@app.route('/')
def home():
    return render_template('home.html')


@app.route('/index')
def index():
    location_filter = request.args.get('location')
    category_filter = request.args.get('category')

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    query = "SELECT id,title, description, category, location, created_at,image FROM donations WHERE 1=1"
    params = []

    if location_filter:
        query += " AND location LIKE ?"
        params.append('%' + location_filter + '%')

    if category_filter and category_filter != 'all':
        query += " AND category = ?"
        params.append(category_filter)

    query += " ORDER BY created_at DESC"

    c.execute(query, params)
    donations = c.fetchall()
    conn.close()

    return render_template('index.html', donations=donations, location_filter=location_filter, category_filter=category_filter)



@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (name, email, password) VALUES (?, ?, ?)", (name, email, password))
            conn.commit()
        except sqlite3.IntegrityError:
            return "Email déjà utilisé"
        finally:
            conn.close()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute("SELECT id, password FROM users WHERE email = ?", (email,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):
            session['user_id'] = user[0]
            return redirect(url_for('profile'))
        else:
            return "Identifiants invalides"
    return render_template('login.html')

@app.route('/profile')
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Infos utilisateur
    c.execute("SELECT name, email, profile_pic FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()

    # Dons créés
    c.execute("SELECT id, title, description, category, location, created_at FROM donations WHERE user_id = ?", (user_id,))
    donations = c.fetchall()

    # Nombre de demandes
    c.execute("SELECT COUNT(*) FROM requests WHERE user_id = ?", (user_id,))
    demande_count = c.fetchone()[0]

    # Discussions (messages)
    c.execute('''
        SELECT COUNT(DISTINCT donation_id || "-" || CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END)
        FROM messages WHERE sender_id = ? OR receiver_id = ?
    ''', (user_id, user_id, user_id))
    discussion_count = c.fetchone()[0]

    conn.close()
    return render_template('profile.html',
                           user=user,
                           donations=donations,
                           demande_count=demande_count,
                           discussion_count=discussion_count)


import requests

@app.route('/create_donation', methods=['GET', 'POST'])
def create_donation():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        location = request.form['location']
        user_id = session['user_id']

        image_file = request.files.get('image')
        image_filename = None

        if image_file and image_file.filename != '':
            image_filename = secure_filename(image_file.filename)
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
            image_file.save(image_path)

        # Géocodage de l'adresse pour obtenir lat/lng
        lat, lng = None, None
        try:
            response = requests.get("https://api.opencagedata.com/geocode/v1/json", params={
                'key': '3b2026fb85a74645923528f340bffcd4',  # ta clé ici
                'q': location,
                'limit': 1,
                'language': 'fr'
            })
            data = response.json()
            if data['results']:
                lat = data['results'][0]['geometry']['lat']
                lng = data['results'][0]['geometry']['lng']
        except Exception as e:
            print("Erreur géocodage:", e)

        conn = sqlite3.connect('database.db')
        c = conn.cursor()

        # Enregistrement du don avec coordonnées
        c.execute('''
            INSERT INTO donations (user_id, title, description, category, location, image, latitude, longitude)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, title, description, category, location, image_filename, lat, lng))

        conn.commit()
        conn.close()
        return redirect(url_for('profile'))

    return render_template('create_donation.html')


@app.route('/donation/<int:donation_id>')
def donation_detail(donation_id):
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    c.execute('''
        SELECT title, description, category, location, created_at, image,user_id
        FROM donations WHERE id = ?
    ''', (donation_id,))
    donation = c.fetchone()

    if not donation:
        return "Don introuvanle", 404
    
    donateur_id=donation[6]

    # Vérifie s’il y a une demande acceptée pour ce don
    c.execute('''
        SELECT COUNT(*) FROM requests
        WHERE donation_id = ? AND status = 'acceptée'
    ''', (donation_id,))
    demande_acceptee = c.fetchone()[0] > 0

    conn.close()

    return render_template('donation_detail.html', donation=donation, donation_id=donation_id,donateur_id=donateur_id, demande_acceptee=demande_acceptee)


@app.route('/request_donation/<int:donation_id>', methods=['POST'])
def request_donation(donation_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Vérifie si une demande a déjà été faite pour ce don par ce user
    c.execute("SELECT * FROM requests WHERE donation_id = ? AND user_id = ?", (donation_id, user_id))
    already_requested = c.fetchone()

    if not already_requested:
        c.execute("INSERT INTO requests (donation_id, user_id) VALUES (?, ?)", (donation_id, user_id))
        conn.commit()

    conn.close()
    return redirect(url_for('donation_detail', donation_id=donation_id))

@app.route('/mes_demandes')
def mes_demandes():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''SELECT donations.title, donations.category, donations.location, requests.status, requests.requested_at
                 FROM requests
                 JOIN donations ON requests.donation_id = donations.id
                 WHERE requests.user_id = ?
                 ORDER BY requests.requested_at DESC''', (user_id,))
    
    demandes = c.fetchall()
    conn.close()

    return render_template('mes_demandes.html', demandes=demandes)

@app.route('/edit_profile', methods=['GET', 'POST'])
def edit_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        profile_pic = request.files.get('profile_pic')

        image_filename = None
        if profile_pic and profile_pic.filename:
            image_filename = secure_filename(profile_pic.filename)
            profile_path = os.path.join('static', 'profiles', image_filename)
            profile_pic.save(profile_path)

        # Si mot de passe non vide, on le change
        if password.strip():
            password_hash = generate_password_hash(password)
            c.execute("""UPDATE users SET name=?, email=?, password=?, profile_pic=COALESCE(?, profile_pic)
                         WHERE id=?""", (name, email, password_hash, image_filename, user_id))
        else:
            c.execute("""UPDATE users SET name=?, email=?, profile_pic=COALESCE(?, profile_pic)
                         WHERE id=?""", (name, email, image_filename, user_id))

        conn.commit()
        conn.close()
        return redirect(url_for('profile'))

    # GET → préremplir le formulaire
    c.execute("SELECT name, email FROM users WHERE id = ?", (user_id,))
    user = c.fetchone()
    conn.close()

    return render_template('edit_profile.html', user=user)

@app.route('/chat/<int:donation_id>/<int:receiver_id>', methods=['GET', 'POST'])
def chat(donation_id, receiver_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    sender_id = session['user_id']
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Envoi de message
    if request.method == 'POST':
        content = request.form['message']
        if content.strip():
            c.execute('''INSERT INTO messages (sender_id, receiver_id, donation_id, content)
                         VALUES (?, ?, ?, ?)''', (sender_id, receiver_id, donation_id, content))
            conn.commit()

    # Marquer les messages comme lus (reçus par l'utilisateur connecté)
    c.execute('''
        UPDATE messages
        SET is_read = 1
        WHERE donation_id = ?
        AND receiver_id = ?
        AND sender_id = ?
        AND is_read = 0
        ''', (donation_id, session['user_id'], receiver_id))
    conn.commit()

    # Récupération de tous les messages entre les 2 utilisateurs sur ce don
    c.execute('''
        SELECT sender_id, content, sent_at FROM messages
        WHERE donation_id = ?
        AND ((sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?))
        ORDER BY sent_at ASC
    ''', (donation_id, sender_id, receiver_id, receiver_id, sender_id))

    messages = c.fetchall()

    # Récup info user
    c.execute("SELECT name FROM users WHERE id = ?", (receiver_id,))
    receiver_name = c.fetchone()[0]

    conn.close()
    return render_template('message.html',
                           messages=messages,
                           receiver_name=receiver_name,
                           donation_id=donation_id,
                           receiver_id=receiver_id)

@app.route('/mes_messages')
def mes_messages():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Récupère les discussions (distincts par utilisateur + don)
    c.execute('''
        SELECT DISTINCT
            CASE WHEN sender_id = ? THEN receiver_id ELSE sender_id END AS other_user,
            donation_id
        FROM messages
        WHERE sender_id = ? OR receiver_id = ?
        ORDER BY donation_id
    ''', (user_id, user_id, user_id))
    threads = c.fetchall()

    # Récupère les noms + titres des dons
    discussions = []
    for other_user_id, donation_id in threads:
        # nom de l'autre utilisateur
        c.execute("SELECT name FROM users WHERE id = ?", (other_user_id,))
        other_name = c.fetchone()
        other_name = other_name[0] if other_name else "Utilisateur inconnu"

        # titre du don
        c.execute("SELECT title FROM donations WHERE id = ?", (donation_id,))
        don = c.fetchone()
        don_title = don[0] if don else "Don supprimé"

        discussions.append({
            "user_id": other_user_id,
            "user_name": other_name,
            "donation_id": donation_id,
            "donation_title": don_title
        })

    conn.close()
    return render_template("mes_messages.html", discussions=discussions)

@app.route('/carte')
def carte():
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, title, description, latitude, longitude FROM donations WHERE latitude IS NOT NULL AND longitude IS NOT NULL")
    donations = c.fetchall()
    conn.close()
    return render_template('carte.html', donations=donations)

@app.route('/supprimer_don/<int:donation_id>', methods=['POST'])
def supprimer_don(donation_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Vérifier si le don appartient bien à l'utilisateur connecté
    c.execute("SELECT image FROM donations WHERE id = ? AND user_id = ?", (donation_id, session['user_id']))
    result = c.fetchone()

    if result:
        image_filename = result[0]
        
        # Supprimer l'image du dossier static/uploads si elle existe
        if image_filename:
            import os
            image_path = os.path.join('static', 'uploads', image_filename)
            if os.path.exists(image_path):
                os.remove(image_path)

        # Supprimer le don
        c.execute("DELETE FROM donations WHERE id = ?", (donation_id,))
        conn.commit()

    conn.close()
    return redirect(url_for('profile'))


@app.route('/modifier_don/<int:donation_id>', methods=['GET', 'POST'])
def modifier_don(donation_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    conn = sqlite3.connect('database.db')
    c = conn.cursor()

    # Récupération du don (pour vérification)
    c.execute("SELECT title, description, category, location, image FROM donations WHERE id = ? AND user_id = ?", (donation_id, session['user_id']))
    don = c.fetchone()

    if not don:
        conn.close()
        return "Don introuvable ou non autorisé", 403

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        location = request.form['location']

        # Géolocalisation à nouveau si localisation changée
        latitude, longitude = geocode_location(location)

        # Image facultative
        image_filename = don[4]  # image actuelle par défaut
        if 'image' in request.files:
            image = request.files['image']
            if image.filename != '':
                image_filename = secure_filename(image.filename)
                image.save(os.path.join('static/uploads', image_filename))

        c.execute('''
            UPDATE donations
            SET title = ?, description = ?, category = ?, location = ?, image = ?, latitude = ?, longitude = ?
            WHERE id = ?
        ''', (title, description, category, location, image_filename, latitude, longitude, donation_id))
        conn.commit()
        conn.close()

        return redirect(url_for('profile'))

    conn.close()
    return render_template('modifier_don.html', don=don, donation_id=donation_id)

@app.route('/demandes_reçues')
def demandes_recues():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        SELECT requests.id, users.name, donations.title, requests.status
        FROM requests
        JOIN users ON requests.user_id = users.id
        JOIN donations ON requests.donation_id = donations.id
        WHERE donations.user_id = ?
        ORDER BY requests.requested_at DESC
    ''', (user_id,))
    demandes = c.fetchall()
    conn.close()

    return render_template('demandes_recues.html', demandes=demandes)

@app.route('/traiter_demande/<int:demande_id>/<action>', methods=['POST'])
def traiter_demande(demande_id, action):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    if action not in ['accepter', 'refuser']:
        return "Action non valide", 400

    status = 'acceptée' if action == 'accepter' else 'refusée'

    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''
        UPDATE requests
        SET status = ?
        WHERE id = ?
    ''', (status, demande_id))
    conn.commit()
    conn.close()

    return redirect(url_for('demandes_recues'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.context_processor
def inject_unread_count():
    if 'user_id' in session:
        conn = sqlite3.connect('database.db')
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM messages WHERE receiver_id = ? AND is_read = 0', (session['user_id'],))
        count = c.fetchone()[0]
        conn.close()
        return {'unread_count': count}
    return {'unread_count': 0}


if __name__ == '__main__':
    app.run(debug=True)
