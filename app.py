from flask import Flask, render_template, request
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

@app.route('/', methods=['GET', 'POST'])
def home():
    message = ""
    if request.method == 'POST':
        message = request.form.get('message')
        # Placeholder for SMS sending logic
    return render_template('index.html', message=message)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)