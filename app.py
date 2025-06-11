from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
import pandas as pd
import os
import re
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
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
    elif len(num) == 11 and num.startswith('1'):
        return '+' + num
    return None

@app.route('/eventcreate', methods=["GET", "POST"])
def eventcreate():
    step = request.args.get('step', '1')

    if request.method == 'POST':
        if step == '2':
            event_name = request.form.get("event_name")
            project_code = request.form.get("project_code")
            if not event_name or not project_code:
                return "Missing data", 400
            session['event_name'] = event_name
            session['project_code'] = project_code
            return redirect(url_for('eventcreate', step='2'))

        elif step == '3':
            session['phone_column'] = request.form['phone_column']
            session['url_column'] = request.form['url_column']
            session['first_name_column'] = request.form.get('first_name_column')
            session['last_name_column'] = request.form.get('last_name_column')

            recipient_file = session.get('recipient_file')
            df = pd.read_csv(recipient_file, dtype=str)

            phone_col = session['phone_column']
            url_col = session['url_column']

            df['clean_phone'] = df[phone_col].apply(normalize_us_number)
            df = df[df['clean_phone'].notnull() & df[url_col].notnull() & (df[url_col].str.strip() != '')]

            session['total'] = len(df) + len(df[df['clean_phone'].isnull()])
            session['valid'] = len(df)
            session['removed'] = session['total'] - session['valid']

            validated_path = os.path.join(app.config['UPLOAD_FOLDER'], 'validated.csv')
            df.to_csv(validated_path, index=False)
            session['validated_file'] = validated_path

            return redirect(url_for('eventcreate', step='3'))

        elif step == '4':
            session['event_date'] = request.form['event_date']
            session['event_time'] = request.form['event_time']
            session['timezone'] = request.form['timezone']
            return redirect(url_for('eventcreate', step='4'))

        elif step == '5':
            session['message_body'] = request.form['message_body']
            session['image_url'] = request.form.get('image_url')
            return redirect(url_for('eventcreate', step='5'))

        elif step == '6':
            from_file = request.files['from_file']
            from_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(from_file.filename))
            from_file.save(from_path)
            session['from_numbers_file'] = from_path
            return redirect(url_for('eventcreate', step='6'))

        elif step == '7':
            session['approver_name'] = request.form['approver_name']
            session['approver_phone'] = request.form['approver_phone']
            return redirect(url_for('eventcreate', step='7'))

    # GET requests
    if step == '1':
        return render_template('eventcreate.html', step='1')

    elif step == '2':
        phone_columns = url_columns = first_columns = last_columns = []

        if 'csv_columns' in session:
            phone_columns = url_columns = first_columns = last_columns = session['csv_columns']

        return render_template('eventcreate.html', step='2', phone_columns=phone_columns,
                               url_columns=url_columns, first_columns=first_columns, last_columns=last_columns)

    elif step == '3':
        return render_template('eventcreate.html', step='3')

    elif step == '4':
        return render_template('eventcreate.html', step='4')

    elif step == '5':
        return render_template('eventcreate.html', step='5')

    elif step == '6':
        return render_template('eventcreate.html', step='6')

    elif step == '7':
        return render_template('eventcreate.html', step='7', total=session.get('total'),
                               valid=session.get('valid'), removed=session.get('removed'),
                               send_time=f"{session.get('event_date')} {session.get('event_time')} {session.get('timezone')}")

    return redirect(url_for('eventcreate'))

@app.route('/eventcreate/commit', methods=['POST'])
def eventcreate_commit():
    # Placeholder for actual commit processing logic
    return "✅ Campaign committed. Ready for manual message sending."

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
