from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import mysql.connector
from datetime import timedelta, datetime, date


# Initialiser l'application Flask
app = Flask(__name__)
app.secret_key = 'cle_secrete_Firdaous_Sanae'

# Configuration MySQL
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''  # Mot de passe par défaut pour XAMPP
app.config['MYSQL_PORT'] = 3306
app.config['MYSQL_DB'] = 'vaccination_db'

# Fonction pour se connecter à la base de données
def get_db_connection():
    try:
        conn = mysql.connector.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            password=app.config['MYSQL_PASSWORD'],
            database=app.config['MYSQL_DB'],
            port=app.config['MYSQL_PORT']
        )
        return conn
    except mysql.connector.Error as e:
        print(f"Erreur de connexion MySQL: {e}")
        return None

@app.route('/')
def home():
    return render_template('index.html')

def insert_vaccins_for_child(conn, id_enfant):
    if not conn or not conn.is_connected():
        print("Connection is not available. Reconnecting...")
        conn = get_db_connection()

    if conn:
        try:
            cursor = conn.cursor(dictionary=True)

            # Récupérer la date de naissance de l'enfant
            query_enfant = "SELECT id, date_naissance FROM enfants WHERE user_id = %s"
            cursor.execute(query_enfant, (id_enfant,))
            enfant = cursor.fetchone()

            if not enfant:
                app.logger.warning(f"Enfant avec user_id {id_enfant} introuvable.")
                return

            date_naissance = enfant['date_naissance']

            # Récupérer les données du calendrier vaccinal
            cursor.execute("SELECT id_vaccin, age, jour FROM calendrier_vaccinal")
            calendrier = cursor.fetchall()

            # Conversion des jours en indices (Lundi = 0, Mardi = 1, ...)
            jours_semaine = {
                "Lundi": 0,
                "Mardi": 1,
                "Mercredi": 2,
                "Jeudi": 3,
                "Vendredi": 4,
                "Samedi": 5,
                "Dimanche": 6
            }

            def calculate_vaccine_date(start_date, age_in_months, desired_day):

                target_date = start_date + timedelta(days=age_in_months * 30)  # Approximativement 1 mois = 30 jours
                days_until_desired_day = (desired_day - target_date.weekday() + 7) % 7
                return target_date + timedelta(days=days_until_desired_day)

            # Calculer les dates des vaccins
            vaccins_a_inserer = []
            for vaccin in calendrier:
                # Convertir le jour en indice
                jour_semaine = jours_semaine.get(vaccin['jour'])
                if jour_semaine is not None:
                    date_vaccin = calculate_vaccine_date(date_naissance, vaccin['age'], jour_semaine)
                    vaccins_a_inserer.append((
                        vaccin['id_vaccin'],
                        enfant['id'],
                        date_vaccin.strftime('%Y-%m-%d'),
                        0
                    ))

            # Insérer dans la table `vaccins`
            insert_query = """
            INSERT INTO vaccins (id_vaccin, id_enfant, date_vaccin, status)
            VALUES (%s, %s, %s, %s)
            """
            cursor.executemany(insert_query, vaccins_a_inserer)
            conn.commit()
            app.logger.info(f"Vaccins insérés pour l'enfant ID: {id_enfant}")
        except Exception as e:
            app.logger.error(f"Erreur lors de l'insertion des vaccins pour l'enfant ID {id_enfant}: {e}")
            conn.rollback()
        finally:
            cursor.close()
    else:
        print("Failed to establish a database connection.")

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        app.logger.info(f"Reçu email: {email}, password: {'****' if password else None}")

        if not email or not password:
            flash("Veuillez fournir un nom d'utilisateur et un mot de passe.")
            return render_template('login.html')

        # Connexion à la base de données
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)  # Utiliser des résultats sous forme de dictionnaire
        query = "SELECT id, password, user_type, first_login FROM users WHERE email = %s"
        cursor.execute(query, (email,))
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user and user['password'] == password:  # Vérification basique, à sécuriser
            session['logged_in'] = True
            session['user_id'] = user['id']
            session['user_type'] = user['user_type']

            # Vérifiez la première connexion
            if user['first_login'] == 1:
                if user['user_type'] == 'enfant' and user['id']:
                    insert_vaccins_for_child(conn, user['id'])
                
                return redirect(url_for('change_password'))

            # Redirigez selon le type d'utilisateur
            if user['user_type'] == 'enfant':
                return redirect(url_for('dashboard_kid'))
            elif user['user_type'] == 'health_pro':
                return redirect(url_for('dashboard_pro'))

        flash("Nom d'utilisateur ou mot de passe incorrect.")
    return render_template('login.html')



@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash("Les mots de passe ne correspondent pas.")
            return render_template('change_password.html')

        # Mettre à jour le mot de passe et `first_login`
        conn = get_db_connection()
        cursor = conn.cursor()
        query = "UPDATE users SET password = %s, first_login = 0 WHERE id = %s"
        cursor.execute(query, (new_password, session['user_id']))
        conn.commit()
        cursor.close()
        conn.close()

        flash("Mot de passe changé avec succès.")
        # Redirigez vers le tableau de bord approprié
        if session['user_type'] == 'enfant':
            return redirect(url_for('dashboard_kid'))
        elif session['user_type'] == 'health_pro':
            return redirect(url_for('dashboard_pro'))

    return render_template('change_password.html')



@app.route('/dashboard_kid')
def dashboard_kid():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    # Connexion à la base de données
    conn = get_db_connection()

    try:
        # Récupérer l'ID de l'utilisateur depuis la session
        user_id = session.get('user_id')  # Assurez-vous que 'user_id' est défini dans la session lors de la connexion
        if not user_id:
            return redirect(url_for('login'))
        
        cursor = conn.cursor(dictionary=True)

        # Récupérer l'ID de l'enfant correspondant
        query_enfant = "SELECT id FROM enfants WHERE user_id = %s"
        cursor.execute(query_enfant, (user_id,))
        enfant = cursor.fetchone()

        if not enfant:
            return "Aucun enfant trouvé pour cet utilisateur.", 404
        
        id_enfant = enfant['id']

        # Récupérer les vaccins non administrés pour l'enfant
        query_vaccins = """
        SELECT 
            GROUP_CONCAT(cv.nom_vaccin_simple ORDER BY cv.nom_vaccin_simple SEPARATOR ', ') AS vaccins, 
            GROUP_CONCAT(v.id_vaccination ORDER BY v.id_vaccination SEPARATOR ', ') AS ids_vaccinations,
            cv.age, 
            cv.jour, 
            v.date_vaccin 
        FROM 
            calendrier_vaccinal cv
        JOIN 
            vaccins v ON cv.id_vaccin = v.id_vaccin
        WHERE 
            v.status = 0 
            AND v.id_enfant = %s 
            AND v.date_vaccin > CURDATE()
        GROUP BY 
            cv.jour, cv.age, v.date_vaccin
        ORDER BY 
            v.date_vaccin
        """
        cursor.execute(query_vaccins, (id_enfant,))
        vaccins_non_administres = cursor.fetchall()
        print(vaccins_non_administres)

        # Afficher la page du tableau de bord avec les vaccins non administrés
        return render_template('dashboard_kid.html', vaccins_na=vaccins_non_administres)
    
    except Exception as e:
        app.logger.error(f"Erreur lors de l'affichage des vaccins non administrés : {e}")
        return "Une erreur est survenue.", 500
    
    finally:
        cursor.close()
        conn.close()

@app.route('/report_vaccin/<ids>', methods=['GET', 'POST'])
def report_vaccin(ids):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Découper les IDs et les convertir en entiers
    ids_list = list(map(int, ids.split(',')))

    if request.method == 'POST':
        # Récupérer la nouvelle date depuis le formulaire
        nouvelle_date = request.form.get('nouvelle_date')

        # Mettre à jour la date du vaccin pour chaque ID
        update_query = "UPDATE vaccins SET date_vaccin = %s WHERE id_vaccination = %s"
        for vaccin_id in ids_list:
            cursor.execute(update_query, (nouvelle_date, vaccin_id))
        conn.commit()

        flash("Les dates des vaccins ont été modifiées avec succès.", "success")
        return redirect(url_for('dashboard_kid'))

    # Récupérer les informations des vaccins pour les IDs donnés
    select_query = "SELECT DISTINCT date_vaccin FROM vaccins WHERE id_vaccination IN ({})".format(
        ', '.join(['%s'] * len(ids_list))
    )
    cursor.execute(select_query, ids_list)
    result = cursor.fetchone()

    if not result or not result['date_vaccin']:
        flash("Aucun vaccin trouvé pour les IDs fournis.", "error")
        return redirect(url_for('dashboard_kid'))

    # Extraire la date actuelle des vaccins
    date_actuelle = result['date_vaccin']
    # Calculer les options de nouvelles dates pour chaque vaccin
    options_dates = [
        (date_actuelle + timedelta(days=7)).strftime('%Y-%m-%d'),
        (date_actuelle + timedelta(days=14)).strftime('%Y-%m-%d')
    ]
    
    print(options_dates)

    return render_template('report_vaccin.html', options_dates=options_dates)

@app.route('/kid_info')
def kid_info():
    if 'user_id' not in session:
        flash("Veuillez vous connecter pour accéder à cette page.", "error")
        return redirect(url_for('login_page'))

    user_id = session['user_id']  # Récupérer user_id de la session
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    query = """
        SELECT *
        FROM enfants 
        WHERE user_id = %s
    """
    cursor.execute(query, (user_id,))
    kid_info = cursor.fetchone()

    if not kid_info:
        flash("Aucune information trouvée pour cet enfant.", "error")
        return redirect(url_for('dashboard_kid'))

    return render_template('kid_info.html', kid_info=kid_info)


@app.route('/dashboard_pro')
def dashboard_pro():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    current_date = date.today().strftime('%Y-%m-%d')  # Date actuelle au format 'YYYY-MM-DD'
    conn = get_db_connection()

    cursor = conn.cursor(dictionary=True)

    # Requête SQL pour récupérer les vaccins à administrer aujourd'hui
    query = """
        SELECT e.nom_prenom AS nom_enfant, cv.nom_vaccin_simple AS vaccin, cv.age, v.date_vaccin, v.status, v.id_vaccination
        FROM enfants e
        JOIN vaccins v ON e.id = v.id_enfant
        JOIN calendrier_vaccinal cv ON v.id_vaccin = cv.id_vaccin
        WHERE v.date_vaccin = %s AND v.status = 0
    """
    cursor.execute(query, (current_date,))
    vaccins_du_jour = cursor.fetchall()

    # Rendu de la page avec les données
    return render_template('dashboard_pro.html', vaccins_du_jour=vaccins_du_jour)

@app.route('/vaccin_done/<int:id_vaccination>', methods=['GET'])
def vaccin_done(id_vaccination):
    # Vérification que l'utilisateur est connecté
    if 'user_id' not in session:
        flash("Veuillez vous connecter pour accéder à cette page.", "error")
        return redirect(url_for('login_page'))

    # Récupération de l'ID du professionnel de santé depuis la session
    user_id = session.get('user_id')

    # Connexion à la base de données
    conn = get_db_connection()
    if conn is None:
        flash("Erreur de connexion à la base de données.", "error")
        return redirect(url_for('dashboard_pro'))  # On retourne après un échec de connexion

    try:
        cursor = conn.cursor(dictionary=True)

        # Vérification de l'existence du vaccin avec l'ID spécifié
        cursor.execute("SELECT * FROM vaccins WHERE id_vaccination = %s", (id_vaccination,))
        vaccin = cursor.fetchone()

        if not vaccin:
            flash(f"Aucun vaccin trouvé avec l'ID {id_vaccination}.", "error")
            return redirect(url_for('dashboard_pro'))

        # Afficher les informations du vaccin pour vérifier la récupération
        print(vaccin)

        cursor.execute("SELECT id FROM health_pro WHERE user_id = %s", (user_id,))
        id_prof_sante = cursor.fetchone()

        id_prof_sante = id_prof_sante['id']

        # Requête SQL pour mettre à jour le statut et l'ID du professionnel de santé
        update_query = """
            UPDATE vaccins
            SET status = 1, id_prof_sante = %s
            WHERE id_vaccination = %s
        """
        print(f"Mise à jour avec ID Professionnel de santé : {id_prof_sante} et ID Vaccination : {id_vaccination}")
        cursor.execute(update_query, (id_prof_sante, id_vaccination))
        conn.commit()

        flash("Le vaccin a été marqué comme administré avec succès.", "success")
        return redirect(url_for('dashboard_pro'))
    except Exception as e:
        conn.rollback()  # En cas d'erreur, annuler la transaction
        flash(f"Une erreur s'est produite : {e}", "error")
    finally:
        cursor.close()
        conn.close()

    # Rediriger vers la page du tableau de bord après l'opération
    return redirect(url_for('dashboard_pro'))

@app.route('/historique_vaccins', methods=['GET'])
def historique_vaccins():
    # Vérification que l'utilisateur est connecté
    if 'user_id' not in session:
        flash("Veuillez vous connecter pour accéder à cette page.", "error")
        return redirect(url_for('login_page'))

    user_id = session.get('user_id')

    # Connexion à la base de données
    conn = get_db_connection()
    if conn is None:
        flash("Erreur de connexion à la base de données.", "error")
        return redirect(url_for('dashboard_pro'))

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id FROM health_pro WHERE user_id = %s", (user_id,))
        id_prof_sante = cursor.fetchone()

        id_prof_sante = id_prof_sante['id']

        # Requête pour récupérer l'historique des vaccins
        cursor.execute("""
            SELECT e.nom_prenom AS nom_enfant, cv.nom_vaccin_simple AS vaccin, cv.age, v.date_vaccin
            FROM enfants e
            JOIN vaccins v ON e.id = v.id_enfant
            JOIN calendrier_vaccinal cv ON v.id_vaccin = cv.id_vaccin
            WHERE v.status = 1 AND v.id_prof_sante = %s
            ORDER BY v.date_vaccin DESC
        """, (id_prof_sante,))
        vaccins_historique = cursor.fetchall()

        return render_template('historique_vaccins.html', vaccins_historique=vaccins_historique)

    except Exception as e:
        flash(f"Une erreur s'est produite : {e}", "error")
        return redirect(url_for('dashboard_pro'))

    finally:
        cursor.close()
        conn.close()

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# # Gestion des enfants (ajout et récupération)
# @app.route('/enfants', methods=['GET', 'POST'])
# def enfants():
#     conn = get_db_connection()
#     cursor = conn.cursor(dictionary=True)

#     if request.method == 'POST':
#         # Récupérer les données JSON envoyées par le client
#         data = request.json
#         nom = data.get('nom')
#         date_naissance = data.get('date_naissance')
#         sexe = data.get('sexe')
#         parent_contact = data.get('parent_contact')

#         # Insérer un nouvel enfant dans la base de données
#         cursor.execute(
#             "INSERT INTO enfants (nom, date_naissance, sexe, parent_contact) VALUES (%s, %s, %s, %s)",
#             (nom, date_naissance, sexe, parent_contact)
#         )
#         conn.commit()
#         conn.close()
#         return jsonify({'message': 'Enfant ajouté avec succès'}), 201

#     # Récupérer tous les enfants de la base de données
#     cursor.execute("SELECT * FROM enfants")
#     enfants = cursor.fetchall()
#     conn.close()
#     return jsonify(enfants)

def test_db_connection():
    try:
        # Tenter de se connecter à la base de données
        conn = mysql.connector.connect(
            host=app.config['MYSQL_HOST'],
            user=app.config['MYSQL_USER'],
            password=app.config['MYSQL_PASSWORD'],
            database=app.config['MYSQL_DB']
        )
        if conn.is_connected():
            print("Connexion à la base de données réussie.")
            conn.close()
    except mysql.connector.Error as e:
        print(f"Erreur de connexion à la base de données : {e}")

@app.route('/test-db')
def test_database():
    try:
        conn = get_db_connection()
        if conn.is_connected():
            conn.close()
            return "Connexion à la base de données réussie.", 200
    except mysql.connector.Error as e:
        return f"Erreur de connexion à la base de données : {e}", 500


# Démarrer l'application Flask
if __name__ == '__main__':
    app.run(debug=True)
