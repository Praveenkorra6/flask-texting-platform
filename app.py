from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
import pandas as pd
import os
import re
from werkzeug.utils import secure_filename
from twilio.rest import Client
from datetime import datetime, timedelta

app = Flask(__name__)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
app.secret_key = 'supersecret'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def normalize_us_number(raw):
    if pd.isna(raw):
        return None
    num = re.sub(r'\D', '', str(raw))  # Remove all non-digits
    if len(num) == 10:
        return '+1' + num
    return None  # Invalid if not exactly 10 digits


@app.route('/eventcreate', methods=["GET", "POST"])
def eventcreate():
    if 'event_saved' not in session:
        session['event_saved'] = False
    if session.get('event_committed') and request.method == 'POST':
        return "This event is locked. No changes allowed.", 403

    step = request.args.get('step', '1')

    try:
        if step == '1':
            if request.method == 'POST':
                session['event_name'] = request.form['event_name']
                session['project_code'] = request.form['project_code']
                session['event_saved'] = False
                return redirect(url_for('eventcreate', step='2'))
            return render_template('eventcreate.html', step='1')

        elif step == '2':
            if request.method == 'POST':
                file = request.files.get('recipient_file')
                if not file or file.filename == '':
                    return render_template('eventcreate.html', step='2', error="Please upload a valid file.")
                filename = secure_filename(file.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(path)
                session['recipient_file'] = path
                df = pd.read_csv(path, dtype=str)
                session['csv_columns'] = df.columns.tolist()
                return redirect(url_for('eventcreate', step='2b'))
            return render_template('eventcreate.html', step='2')

        elif step == '2b':
            columns = session.get('csv_columns', [])
        
            if request.method == 'POST':
                # 1) Save mapping selection
                session['phone_column']      = request.form['phone_column']
                session['url_column']        = request.form['url_column']
                session['first_name_column'] = request.form.get('first_name_column')
                session['last_name_column']  = request.form.get('last_name_column')
        
                # 2) Load & clean
                df = pd.read_csv(session['recipient_file'], dtype=str)
                df['clean_phone'] = df[session['phone_column']].apply(normalize_us_number)
                df = df[
                    df['clean_phone'].notnull() &
                    df[session['url_column']].notnull() &
                    (df[session['url_column']].str.strip() != '')
                ]
        
                # 3) Store counts
                session['total']   = len(pd.read_csv(session['recipient_file']))
                session['valid']   = len(df)
                session['removed'] = session['total'] - session['valid']
        
                # 4) Save validated file
                validated_path = os.path.join(app.config['UPLOAD_FOLDER'], 'validated.csv')
                df.to_csv(validated_path, index=False)
                session['validated_file'] = validated_path
        
                # 5) Redirect back to 2b so user can see the summary
                return redirect(url_for('eventcreate', step='2b'))
        
            # GET: show mapping form *and* any counts from a previous POST
            return render_template(
                'eventcreate.html',
                step='2b',
                phone_columns=columns, url_columns=columns,
                first_columns=columns, last_columns=columns,
                total=session.get('total'),
                valid=session.get('valid'),
                removed=session.get('removed')
            )


        elif step == '3':
            if request.method == 'POST':
                date_str = request.form['event_date']
                time_str = request.form['event_time']
                timezone = request.form['timezone']
            
                try:
                    full_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                    now = datetime.now()
                    if full_dt < now + timedelta(minutes=5):
                        return render_template('eventcreate.html', step='3', error="Scheduled time must be at least 5 minutes from now.")
                except Exception as e:
                    return render_template('eventcreate.html', step='3', error="Invalid date or time format.")
            
                session['event_date'] = date_str
                session['event_time'] = time_str
                session['timezone'] = timezone
                session['event_saved'] = False
                return redirect(url_for('eventcreate', step='4'))


        elif step == '4':
            if request.method == 'POST':
                session['message_body'] = request.form.get('message_body', '').strip()
                session['image_url'] = request.form.get('image_url', '').strip()
                if not session['message_body']:
                    return render_template('eventcreate.html', step='4', error="Message body is required.")
                return redirect(url_for('eventcreate', step='5'))
            return render_template('eventcreate.html', step='4')

        elif step == '5':
            if request.method == 'POST':
                from_file = request.files.get('from_file')
                if not from_file or from_file.filename == '':
                    return render_template('eventcreate.html', step='5', error="Please upload a from-numbers file.")
                
                from_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(from_file.filename))
                from_file.save(from_path)
                session['from_numbers_file'] = from_path
        
                df = pd.read_csv(from_path, dtype=str)
                if 'from_number' not in df.columns:
                    return render_template('eventcreate.html', step='5', error="Missing 'from_number' column in the file.")
                
                # Normalize phone numbers and filter out invalid ones
                raw_numbers = df['from_number'].dropna().tolist()
                normalized_numbers = [normalize_us_number(num) for num in raw_numbers]
                valid_numbers = [num for num in normalized_numbers if num]
        
                if not valid_numbers:
                    return render_template('eventcreate.html', step='5', error="No valid 10-digit phone numbers found in 'from_number' column.")
        
                session['from_numbers'] = valid_numbers
                session['event_saved'] = False
                return redirect(url_for('eventcreate', step='6'))
        
            return render_template('eventcreate.html', step='5')

        elif step == '6':
            if request.method == 'POST':
                approver_name = request.form.get('approver_name', '').strip()
                approver_phone = request.form.get('approver_phone', '').strip()
            
                normalized = normalize_us_number(approver_phone)
                if not approver_name or not normalized:
                    return render_template('eventcreate.html', step='6', error="Approver name and a valid 10-digit phone number are required.")
            
                session['approver_name'] = approver_name
                session['approver_phone'] = normalized
                session['event_saved'] = False
                return redirect(url_for('eventcreate', step='7'))
            return render_template('eventcreate.html', step='6')

        elif step == '7':
            if request.method == 'POST':
                session['event_saved'] = True
                return redirect(url_for('eventcreate', step='7'))  # Stay on 7 after saving
            # Construct default/fallback values
            total = session.get('total', 0)
            valid = session.get('valid', 0)
            removed = session.get('removed', 0)
            send_time = f"{session.get('event_date', 'N/A')} {session.get('event_time', '')} {session.get('timezone', '')}"
            event_name = session.get('event_name', 'N/A')
            project_code = session.get('project_code', 'N/A')
            approver_name = session.get('approver_name', 'N/A')
            approver_phone = session.get('approver_phone', 'N/A')
            return render_template('eventcreate.html', step='7',
                                   total=total,
                                   valid=valid,
                                   removed=removed,
                                   event_name=event_name,
                                   project_code=project_code,
                                   send_time=send_time,
                                   approver_name=approver_name,
                                   approver_phone=approver_phone)

        elif step == '8':
            test_status = None
            if request.method == 'POST' and 'test_number' in request.form:
                test_number = request.form['test_number']
                from_numbers = session.get('from_numbers', [])
                message = session.get('message_body', '')
                image_url = session.get('image_url')
                if not from_numbers:
                    test_status = "No from numbers available."
                else:
                    try:
                        from_number = from_numbers[0]
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
                        test_status = "Test message sent. Please review and commit."
                    except Exception as e:
                        test_status = f"Error sending message: {e}"
            return render_template('eventcreate.html', step='8', test_status=test_status)

        return redirect(url_for('eventcreate'))

    except Exception as e:
        print(f"[Error in step {step}] {e}")
        return f"An error occurred in Step {step}. Please check your input and try again.<br>Error: {str(e)}", 400

@app.route('/eventcreate/save', methods=['POST'])
def eventcreate_save():
    session['event_saved'] = True
    return redirect(url_for('eventcreate', step='8'))

@app.route('/eventcreate/commit', methods=['POST'])
def eventcreate_commit():
    session['event_committed'] = True
    return "Campaign committed and locked. Supervisors can now send messages manually."

@app.errorhandler(400)
def handle_bad_request(e):
    return render_template('400.html'), 400

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
