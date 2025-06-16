from flask import Flask, render_template, request, redirect, url_for
from flask_session import Session
import pandas as pd
import os
import re
import uuid
from werkzeug.utils import secure_filename
from twilio.rest import Client
from datetime import datetime, timedelta
from utils import load_event, save_event


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
    num = re.sub(r'\D', '', str(raw))
    if len(num) == 10:
        return '+1' + num
    return None

@app.route('/eventcreate', methods=["GET", "POST"])
def eventcreate():
    step = request.args.get('step', '1')
    event_id = request.args.get('event_id')

    if not event_id:
        event_id = str(uuid.uuid4())
        return redirect(url_for('eventcreate', step=step, event_id=event_id))

    data = load_event(event_id)

    try:
        if step == '1':
            if request.method == 'POST':
                data['event_name'] = request.form['event_name']
                data['project_code'] = request.form['project_code']
                save_event(event_id, data)
                return redirect(url_for('eventcreate', step='2', event_id=event_id))
            return render_template('eventcreate.html', step='1', event_id=event_id, event_name=data.get('event_name', ''), project_code=data.get('project_code', ''))

        elif step == '2':
            if request.method == 'POST':
                file = request.files.get('recipient_file')
                if not file or file.filename == '':
                    return render_template('eventcreate.html', step='2', event_id=event_id, error="Please upload a valid file.")
                filename = secure_filename(file.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(path)
                data['recipient_file'] = path
                df = pd.read_csv(path, dtype=str)
                data['csv_columns'] = df.columns.tolist()
                save_event(event_id, data)
                return redirect(url_for('eventcreate', step='2b', event_id=event_id))
            return render_template('eventcreate.html', step='2', event_id=event_id)

        elif step == '2b':
            columns = data.get('csv_columns', [])
            total = data.get('total', 0)
            valid = data.get('valid', 0)
            removed = data.get('removed', 0)

            if request.method == 'POST':
                data['phone_column'] = request.form['phone_column']
                data['url_column'] = request.form['url_column']
                data['first_name_column'] = request.form.get('first_name_column')
                data['last_name_column'] = request.form.get('last_name_column')

                df = pd.read_csv(data['recipient_file'], dtype=str)
                df['clean_phone'] = df[data['phone_column']].apply(normalize_us_number)
                df = df[df['clean_phone'].notnull() & df[data['url_column']].notnull() & (df[data['url_column']].str.strip() != '')]

                data['total'] = len(pd.read_csv(data['recipient_file']))
                data['valid'] = len(df)
                data['removed'] = data['total'] - data['valid']

                validated_path = os.path.join(app.config['UPLOAD_FOLDER'], 'validated.csv')
                df.to_csv(validated_path, index=False)
                data['validated_file'] = validated_path
                save_event(event_id, data)

                return redirect(url_for('eventcreate', step='3', event_id=event_id))

            return render_template('eventcreate.html', step='2b', event_id=event_id,
                                   phone_columns=columns, url_columns=columns,
                                   first_columns=columns, last_columns=columns,
                                   selected_phone=data.get('phone_column', ''),
                                   selected_url=data.get('url_column', ''),
                                   selected_first=data.get('first_name_column', ''),
                                   selected_last=data.get('last_name_column', ''),
                                   total=total, valid=valid, removed=removed)

        elif step == '3':
            if request.method == 'POST':
                date_str = request.form['event_date']
                time_str = request.form['event_time']
                timezone = request.form['timezone']

                try:
                    full_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                    now = datetime.now()
                    if full_dt < now + timedelta(minutes=5):
                        return render_template('eventcreate.html', step='3', event_id=event_id, error="Scheduled time must be at least 5 minutes from now.")
                except Exception as e:
                    return render_template('eventcreate.html', step='3', event_id=event_id, error="Invalid date or time format.")

                data['event_date'] = date_str
                data['event_time'] = time_str
                data['timezone'] = timezone
                save_event(event_id, data)
                return redirect(url_for('eventcreate', step='4', event_id=event_id))

            return render_template('eventcreate.html', step='3', event_id=event_id,
                                   event_date=data.get('event_date', ''),
                                   event_time=data.get('event_time', ''),
                                   timezone=data.get('timezone', ''))

        elif step == '4':
            if request.method == 'POST':
                data['message_body'] = request.form.get('message_body', '').strip()
                data['image_url'] = request.form.get('image_url', '').strip()
                if not data['message_body']:
                    return render_template('eventcreate.html', step='4', event_id=event_id, error="Message body is required.")
                save_event(event_id, data)
                return redirect(url_for('eventcreate', step='5', event_id=event_id))
            return render_template('eventcreate.html', step='4', event_id=event_id,
                                   message_body=data.get('message_body', ''),
                                   image_url=data.get('image_url', ''))

        elif step == '5':
            if request.method == 'POST':
                from_file = request.files.get('from_file')
                if not from_file or from_file.filename == '':
                    return render_template('eventcreate.html', step='5', event_id=event_id, error="Please upload a from-numbers file.")

                from_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(from_file.filename))
                from_file.save(from_path)
                data['from_numbers_file'] = from_path

                df = pd.read_csv(from_path, dtype=str)
                if 'from_number' not in df.columns:
                    return render_template('eventcreate.html', step='5', event_id=event_id, error="Missing 'from_number' column in the file.")

                raw_numbers = df['from_number'].dropna().tolist()
                normalized_numbers = [normalize_us_number(num) for num in raw_numbers]
                valid_numbers = [num for num in normalized_numbers if num]

                if not valid_numbers:
                    return render_template('eventcreate.html', step='5', event_id=event_id, error="No valid 10-digit phone numbers found in 'from_number' column.")

                data['from_numbers'] = valid_numbers
                save_event(event_id, data)
                return redirect(url_for('eventcreate', step='6', event_id=event_id))

            return render_template('eventcreate.html', step='5', event_id=event_id)

        elif step == '6':
            if request.method == 'POST':
                approver_name = request.form.get('approver_name', '').strip()
                approver_phone = request.form.get('approver_phone', '').strip()

                normalized = normalize_us_number(approver_phone)
                if not approver_name or not normalized:
                    return render_template('eventcreate.html', step='6', event_id=event_id, error="Approver name and a valid 10-digit phone number are required.")

                data['approver_name'] = approver_name
                data['approver_phone'] = normalized
                save_event(event_id, data)
                return redirect(url_for('eventcreate', step='7', event_id=event_id))

            return render_template('eventcreate.html', step='6', event_id=event_id,
                                   approver_name=data.get('approver_name', ''),
                                   approver_phone=data.get('approver_phone', ''))

        elif step == '7':
            if request.method == 'POST':
                data['event_saved'] = True
                save_event(event_id, data)
                return redirect(url_for('eventcreate', step='7', event_id=event_id))

            return render_template('eventcreate.html', step='7', event_id=event_id,
                                   total=data.get('total', 0),
                                   valid=data.get('valid', 0),
                                   removed=data.get('removed', 0),
                                   event_name=data.get('event_name', 'N/A'),
                                   project_code=data.get('project_code', 'N/A'),
                                   send_time=f"{data.get('event_date', 'N/A')} {data.get('event_time', '')} {data.get('timezone', '')}",
                                   approver_name=data.get('approver_name', 'N/A'),
                                   approver_phone=data.get('approver_phone', 'N/A'))

        elif step == '8':
            test_status = None
            if request.method == 'POST' and 'test_number' in request.form:
                test_number = request.form['test_number']
                from_numbers = data.get('from_numbers', [])
                message = data.get('message_body', '')
                image_url = data.get('image_url')
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
            return render_template('eventcreate.html', step='8', event_id=event_id, test_status=test_status)

        return redirect(url_for('eventcreate', event_id=event_id))

    except Exception as e:
        print(f"[Error in step {step}] {e}")
        return f"An error occurred in Step {step}. Please check your input and try again.<br>Error: {str(e)}", 400

@app.route('/eventcreate/save', methods=['POST'])
def eventcreate_save():
    return redirect(url_for('eventcreate', step='8'))

@app.route('/eventcreate/commit', methods=['POST'])
def eventcreate_commit():
    return "Campaign committed and locked. Supervisors can now send messages manually."

@app.errorhandler(400)
def handle_bad_request(e):
    return render_template('400.html'), 400

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
