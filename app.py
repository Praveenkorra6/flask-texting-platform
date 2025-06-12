from flask import Flask, render_template, request, redirect, session, url_for
from flask_session import Session
import pandas as pd
import os
import re
from werkzeug.utils import secure_filename
from twilio.rest import Client


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
    elif len(num) == 11 and num.startswith('1'):
        return '+' + num
    return None

@app.route('/eventcreate', methods=["GET", "POST"])
def eventcreate():
    if session.get('event_committed') and request.method == 'POST':
        return "This event is locked. No changes allowed.", 403

    step = request.args.get('step', '1')

    # STEP 1
    if step == '1':
        if request.method == 'POST':
            session['event_name'] = request.form['event_name']
            session['project_code'] = request.form['project_code']
            return redirect(url_for('eventcreate', step='2'))
        return render_template('eventcreate.html', step='1')

    # STEP 2
    # STEP 2a: Upload CSV
    elif step == '2':
        if request.method == 'POST':
            file = request.files.get('recipient_file')
            if file:
                filename = secure_filename(file.filename)
                path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(path)
                session['recipient_file'] = path
                df = pd.read_csv(path, dtype=str)
                session['csv_columns'] = df.columns.tolist()
                return redirect(url_for('eventcreate', step='2b'))
        return render_template('eventcreate.html', step='2')

    # STEP 2b: Map Columns
    elif step == '2b':
        if request.method == 'POST':
            session['phone_column'] = request.form['phone_column']
            session['url_column'] = request.form['url_column']
            session['first_name_column'] = request.form.get('first_name_column')
            session['last_name_column'] = request.form.get('last_name_column')

            df = pd.read_csv(session['recipient_file'], dtype=str)
            df['clean_phone'] = df[session['phone_column']].apply(normalize_us_number)
            df = df[df['clean_phone'].notnull() & df[session['url_column']].notnull() & (df[session['url_column']].str.strip() != '')]

            session['total'] = len(pd.read_csv(session['recipient_file']))
            session['valid'] = len(df)
            session['removed'] = session['total'] - session['valid']

            validated_path = os.path.join(app.config['UPLOAD_FOLDER'], 'validated.csv')
            df.to_csv(validated_path, index=False)
            session['validated_file'] = validated_path

            return redirect(url_for('eventcreate', step='3'))

        columns = session.get('csv_columns', [])
        return render_template('eventcreate.html', step='2b',
                               phone_columns=columns, url_columns=columns,
                               first_columns=columns, last_columns=columns)


    # STEP 3
    elif step == '3':
        if request.method == 'POST':
            session['event_date'] = request.form['event_date']
            session['event_time'] = request.form['event_time']
            session['timezone'] = request.form['timezone']
            return redirect(url_for('eventcreate', step='4'))
        return render_template('eventcreate.html', step='3')

    # STEP 4
    elif step == '4':
        if request.method == 'POST':
            session['message_body'] = request.form['message_body']
            session['image_url'] = request.form.get('image_url')
            return redirect(url_for('eventcreate', step='5'))
        return render_template('eventcreate.html', step='4')


    # STEP 5
    elif step == '5':
        if request.method == 'POST':
            from_file = request.files['from_file']
            from_path = os.path.join(app.config['UPLOAD_FOLDER'], secure_filename(from_file.filename))
            from_file.save(from_path)
            session['from_numbers_file'] = from_path
    
            # Read from numbers and store in session
            df = pd.read_csv(from_path, dtype=str)
            session['from_numbers'] = df['from_number'].dropna().tolist()
    
            return redirect(url_for('eventcreate', step='6'))
        return render_template('eventcreate.html', step='5')



    # STEP 6
    elif step == '6':
        if request.method == 'POST':
            session['approver_name'] = request.form['approver_name']
            session['approver_phone'] = request.form['approver_phone']
            return redirect(url_for('eventcreate', step='7'))
        return render_template('eventcreate.html', step='6')


    # STEP 7
    elif step == '7':
        if request.method == 'POST':
            session['event_saved'] = True
            return redirect(url_for('eventcreate', step='8'))
        
        return render_template('eventcreate.html', step='7',
                               total=session.get('total'),
                               valid=session.get('valid'),
                               removed=session.get('removed'),
                               event_name=session.get('event_name'),
                               project_code=session.get('project_code'),
                               send_time=f"{session.get('event_date')} {session.get('event_time')} {session.get('timezone')}",
                               approver_name=session.get('approver_name'),
                               approver_phone=session.get('approver_phone'))

    # STEP 8
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

@app.route('/eventcreate/save', methods=['POST'])
def eventcreate_save():
    session['event_saved'] = True
    return redirect(url_for('eventcreate', step='8'))
    
@app.route('/eventcreate/commit', methods=['POST'])
def eventcreate_commit():
    session['event_committed'] = True
    return "Campaign committed and locked. Supervisors can now send messages manually."



if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
