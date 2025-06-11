from flask import Flask, render_template, request, redirect, session
import pandas as pd
import os
import re

app = Flask(__name__)
app.secret_key = 'supersecret'
UPLOAD_FOLDER = 'uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# Helper to normalize phone numbers
def normalize_us_number(raw):
    if pd.isna(raw):
        return None
    num = re.sub(r'\D', '', str(raw))  # remove non-digits
    if len(num) == 10:
        return '+1' + num
    elif len(num) == 11 and num.startswith('1'):
        return '+' + num
    return None

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files["csv_file"]
        if file:
            filepath = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
            file.save(filepath)
            df = pd.read_csv(filepath, dtype=str)
            session['csv_path'] = filepath
            session['columns'] = df.columns.tolist()
            return render_template("index.html", columns=df.columns)
    return render_template("index.html")

@app.route("/map", methods=["POST"])
def map_columns():
    phone_col = request.form.get("phone_column")
    url_col = request.form.get("url_column")
    path = session.get('csv_path')

    if not path or not os.path.exists(path):
        return redirect("/")

    df = pd.read_csv(path, dtype=str)

    # Normalize phone numbers
    df["clean_phone"] = df[phone_col].apply(normalize_us_number)
    valid_df = df[df["clean_phone"].notnull()]
    invalid_count = len(df) - len(valid_df)

    # Store cleaned data
    valid_df = valid_df[[phone_col, url_col, "clean_phone"]]
    valid_df.to_csv(os.path.join(UPLOAD_FOLDER, "validated.csv"), index=False)

    summary = {
        "total": len(df),
        "valid": len(valid_df),
        "invalid": invalid_count
    }

    return render_template("index.html", summary=summary)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

