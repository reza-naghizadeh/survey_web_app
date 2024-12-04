from flask import Flask, render_template, request, redirect, url_for, make_response
import sqlite3
from datetime import datetime, timedelta

app = Flask(__name__)

# Initialize the SQLite database
DATABASE = 'survey.db'

def init_db():
    # Create tables if they don't exist
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS surveys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            expire_time DATETIME
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER,
            question_text TEXT NOT NULL,
            FOREIGN KEY(survey_id) REFERENCES surveys(id)
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS options (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER,
            option_text TEXT NOT NULL,
            votes INTEGER DEFAULT 0,
            FOREIGN KEY(question_id) REFERENCES questions(id)
        )''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS votes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            survey_id INTEGER NOT NULL,
            ip_address TEXT NOT NULL,
            vote_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(survey_id) REFERENCES surveys(id)
        )''')

@app.route('/')
def home():
    # Fetch all active surveys
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM surveys WHERE expire_time > ?", (datetime.now(),))
        surveys = cursor.fetchall()
    return render_template('home.html', surveys=surveys)

@app.route('/admin', methods=['GET', 'POST'])
def admin_panel():
    if request.method == 'POST':
        # Create a new survey
        title = request.form['survey-title']
        expire_duration = int(request.form['expire-time'])
        expire_unit = request.form['time-unit']
        expire_time = datetime.now() + (timedelta(minutes=expire_duration) if expire_unit == 'minutes' else timedelta(hours=expire_duration))
        
        questions = request.form.getlist('questions[]')
        options_list = request.form.getlist('options[]')

        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO surveys (title, expire_time) VALUES (?, ?)", (title, expire_time))
            survey_id = cursor.lastrowid
            
            # Insert questions and options
            for question_text in questions:
                cursor.execute("INSERT INTO questions (survey_id, question_text) VALUES (?, ?)", (survey_id, question_text))
                question_id = cursor.lastrowid
                
                for option_text in options_list:
                    cursor.execute("INSERT INTO options (question_id, option_text) VALUES (?, ?)", (question_id, option_text))
        
        return redirect(url_for('admin_panel'))
    
    # Fetch existing surveys
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM surveys")
        surveys = cursor.fetchall()
    return render_template('admin_panel.html', surveys=surveys)

@app.route('/survey/<int:survey_id>', methods=['GET', 'POST'])
def survey_panel(survey_id):
    user_ip = request.remote_addr  # Get the user's IP address

    if request.method == 'POST':
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            # Check if the user has already voted
            cursor.execute(
                "SELECT COUNT(*) FROM votes WHERE survey_id = ? AND ip_address = ?",
                (survey_id, user_ip)
            )
            already_voted = cursor.fetchone()[0] > 0

            if already_voted:
                return make_response("*شما قبلا در این نظرسنجی شرکت کرده‌اید*", 403)

            # Record the vote
            selected_options = request.form.getlist('survey-option')
            for option_id in selected_options:
                cursor.execute("UPDATE options SET votes = votes + 1 WHERE id = ?", (option_id,))
            cursor.execute(
                "INSERT INTO votes (survey_id, ip_address) VALUES (?, ?)",
                (survey_id, user_ip)
            )
        return redirect(url_for('home'))

    # Fetch survey details
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, title FROM surveys WHERE id = ?", (survey_id,))
        survey = cursor.fetchone()
        
        cursor.execute('''
            SELECT questions.id, questions.question_text, options.id AS option_id, options.option_text
            FROM questions
            JOIN options ON questions.id = options.question_id
            WHERE questions.survey_id = ?
        ''', (survey_id,))
        data = cursor.fetchall()
    
    # Organize questions and options
    questions = {}
    for qid, qtext, oid, otext in data:
        if qid not in questions:
            questions[qid] = {'text': qtext, 'options': []}
        questions[qid]['options'].append({'id': oid, 'text': otext})

    survey_data = {'id': survey[0], 'title': survey[1]} if survey else None
    
    return render_template('survey_page.html', survey=survey_data, questions=questions)


@app.route('/admin/delete/<int:survey_id>', methods=['POST'])
def delete_survey(survey_id):
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        
        # Delete related options and questions first (to maintain foreign key constraints)
        cursor.execute('DELETE FROM options WHERE question_id IN (SELECT id FROM questions WHERE survey_id = ?)', (survey_id,))
        cursor.execute('DELETE FROM questions WHERE survey_id = ?', (survey_id,))
        
        # Delete the survey itself
        cursor.execute('DELETE FROM surveys WHERE id = ?', (survey_id,))
        
    return redirect(url_for('admin_panel'))


@app.route('/results/<int:survey_id>')
def survey_results(survey_id):
    # Fetch survey results
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT title FROM surveys WHERE id = ?", (survey_id,))
        survey = cursor.fetchone()
        
        cursor.execute('''
            SELECT options.option_text, options.votes
            FROM options
            JOIN questions ON options.question_id = questions.id
            WHERE questions.survey_id = ?
        ''', (survey_id,))
        data = cursor.fetchall()

    
    # Prepare the data for the pie chart
    labels = [item[0] for item in data]  # Extract option texts
    votes = [item[1] for item in data]  # Extract vote counts
    total_votes = sum(votes) if votes else 0
    percentages = [(vote / total_votes) * 100 if total_votes > 0 else 0 for vote in votes]  # Calculate percentages
    chart_data = zip(labels, votes, percentages)  # Create data for dynamic list
    
    # Prepare color for each chart segment (just an example, you can expand this)
    colors = ['#4caf50', '#2196f3', '#ffc107', '#f44336']
    chart_data = [(label, vote, percentage, colors[i]) for i, (label, vote, percentage) in enumerate(chart_data)]

    return render_template(
        'survey_results.html',
        survey_title=survey[0],
        labels=labels,
        votes=votes,
        percentages=percentages,
        chart_data=chart_data  # Pass data for the list below the pie chart
    )


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
