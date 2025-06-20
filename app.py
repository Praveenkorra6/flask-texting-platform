from flask import Flask, render_template, request, redirect, url_for
from flask_session import Session
import pandas as pd
import os
import re
import uuid
import shutil
import traceback 
from utils import normalize_us_number
from werkzeug.utils import secure_filename
from twilio.rest import Client
from datetime import datetime, timedelta
import mysql.connector

app = Flask(__name__)
app.secret_key = 'supersecret'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def get_db():
    return mysql.connector.connect(
        host=os.getenv("MYSQL_HOST"),
        user=os.getenv("MYSQL_USER"),
        password=os.getenv("MYSQL_PASSWORD"),
        database=os.getenv("MYSQL_DATABASE")
    )

@app.route('/eventcreate', methods=['GET', 'POST'])
def eventcreate():
    step = request.args.get('step', '1')
    event_id = request.args.get('event_id')

    US_STATES = [
        "National", "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID",
        "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT",
        "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
    ]


    if step == '1':
        if request.method == 'POST':
            event_name = request.form['event_name']
            project_code = request.form['project_code']
            state = request.form['state']
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("INSERT IGNORE INTO campaigns (id, name, state) VALUES (%s, %s, %s)", (project_code, event_name, state))
            cursor.execute("SELECT COUNT(*) FROM events WHERE campaign_id = %s", (project_code,))
            count = cursor.fetchone()[0] + 1
            event_id = f"{project_code}_{count}"
            cursor.execute("INSERT INTO events (id, campaign_id, name) VALUES (%s, %s, %s)", (event_id, project_code, event_name))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('eventcreate', step='2', event_id=event_id))
        return render_template('eventcreate.html', step='1', event_id=event_id, state_list=US_STATES)

    elif step == '2':
        if request.method == 'POST':
            if 'recipient_file' not in request.files or request.files['recipient_file'].filename == '':
                return render_template('eventcreate.html', step='2', event_id=event_id, error="Please upload a file.")
            
            file = request.files['recipient_file']
            path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
            file.save(path)
            df = pd.read_csv(path, dtype=str)
            columns = df.columns.tolist()
            return redirect(url_for('eventcreate', step='2b', event_id=event_id, file_path=path))
    
        # For GET request — just show the upload page
        return render_template('eventcreate.html', step='2', event_id=event_id)



    elif step == '2b':
        if request.method == 'POST':
            try:
                file_path = request.form['file_path']
                if not file_path or not os.path.exists(file_path):
                    return render_template('eventcreate.html', step='2', event_id=event_id, error="Uploaded file is missing or was deleted.")
    
                df = pd.read_csv(file_path, dtype=str)
                columns = df.columns.tolist()
    
                phone_col = request.form['phone_column']
                url_col = request.form['url_column']
                first_col = request.form.get('first_name_column', '')
                last_col = request.form.get('last_name_column', '')
    
                # Validate column names
                for col in [phone_col, url_col]:
                    if col not in df.columns:
                        return render_template(
                            'eventcreate.html',
                            step='2b',
                            event_id=event_id,
                            columns=columns,
                            file_path=file_path,
                            error=f"Selected column '{col}' not found in uploaded file."
                        )
    
                df['clean_phone'] = df[phone_col].apply(normalize_us_number)
                df = df[df['clean_phone'].notnull() & df[url_col].notnull() & (df[url_col].str.strip() != '')]
                valid_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{event_id}_validated.csv')
                df.to_csv(valid_path, index=False)
    
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE events SET validated_file=%s, recipient_count=%s WHERE id=%s",
                    (valid_path, len(df), event_id)
                )
                conn.commit()
                cursor.close()
                conn.close()
    
                return redirect(url_for('eventcreate', step='3', event_id=event_id))
            
            except Exception as e:
                error_msg = f"Step 2b POST failed: {e}"
                print(error_msg)
                traceback.print_exc()  # ← Logs full error stack trace
                return render_template('eventcreate.html', step='2b', event_id=event_id, error=error_msg, file_path=file_path, columns=columns)



    elif step == '3':
        if request.method == 'POST':
            event_date = request.form['event_date']
            event_time = request.form['event_time']
            timezone = request.form['timezone']
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE events SET event_date=%s, event_time=%s, timezone=%s WHERE id=%s",
                           (event_date, event_time, timezone, event_id))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('eventcreate', step='4', event_id=event_id))
        return render_template('eventcreate.html', step='3', event_id=event_id)

    elif step == '4':
        if request.method == 'POST':
            message = request.form['message_body']
            image_url = request.form.get('image_url', '')
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE events SET message_body=%s, image_url=%s WHERE id=%s",
                           (message, image_url, event_id))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('eventcreate', step='5', event_id=event_id))
        return render_template('eventcreate.html', step='4', event_id=event_id)

    elif step == '5':
        if request.method == 'POST':
            file = request.files['from_file']
            path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(file.filename))
            file.save(path)
            df = pd.read_csv(path, dtype=str)
            numbers = df['from_number'].dropna().apply(normalize_us_number).dropna().tolist()
            from_file_path = os.path.join(app.config['UPLOAD_FOLDER'], f'{event_id}_from.csv')
            pd.DataFrame({'from_number': numbers}).to_csv(from_file_path, index=False)
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE events SET from_numbers_file=%s WHERE id=%s", (from_file_path, event_id))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('eventcreate', step='6', event_id=event_id))
        return render_template('eventcreate.html', step='5', event_id=event_id)

    elif step == '6':
        if request.method == 'POST':
            approver_name = request.form['approver_name']
            approver_phone = normalize_us_number(request.form['approver_phone'])
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("UPDATE events SET approver_name=%s, approver_phone=%s WHERE id=%s",
                           (approver_name, approver_phone, event_id))
            conn.commit()
            cursor.close()
            conn.close()
            return redirect(url_for('eventcreate', step='7', event_id=event_id))
        return render_template('eventcreate.html', step='6', event_id=event_id)

    elif step == '7':
        return render_template('eventcreate.html', step='7', event_id=event_id)

    elif step == '8':
        test_status = None
        if request.method == 'POST':
            test_number = request.form['test_number']
            conn = get_db()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM events WHERE id=%s", (event_id,))
            event = cursor.fetchone()
            cursor.close()
            conn.close()

            message = event['message_body']
            image_url = event['image_url']
            from_file = event['from_numbers_file']
            from_df = pd.read_csv(from_file, dtype=str)
            from_number = from_df['from_number'].dropna().iloc[0]

            try:
                if image_url:
                    client.messages.create(
                        body=message,
                        from_=from_number,
                        to=test_number,
                        media_url=[image_url]
                    )
                else:
                    client.messages.create(
                        body=message,
                        from_=from_number,
                        to=test_number
                    )
                test_status = "Test message sent."
            except Exception as e:
                test_status = f"Error sending message: {e}"
        return render_template('eventcreate.html', step='8', event_id=event_id, test_status=test_status)

@app.route('/eventcreate/save', methods=['POST'])
def eventcreate_save():
    return redirect(url_for('eventcreate', step='8'))

@app.route('/eventcreate/commit', methods=['POST'])
def eventcreate_commit():
    return "Campaign committed and locked. Supervisors can now send messages manually."

@app.errorhandler(400)
def handle_bad_request(e):
    return render_template('400.html'), 400

@app.route('/delete_event_data/<event_id>')
def delete_event_data(event_id):
    folder_path = os.path.join("event_data", event_id)
    if os.path.exists(folder_path):
        shutil.rmtree(folder_path)
        return f"Deleted event data folder: {folder_path}"
    return f"No folder found for event ID: {event_id}"

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
