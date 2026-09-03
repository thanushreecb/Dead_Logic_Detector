from flask import Flask, request, render_template, send_file, redirect, url_for
import os
import tempfile
from pipeline import run

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return 'No file part'
    file = request.files['file']
    if file.filename == '':
        return 'No selected file'
    if file and file.filename.endswith('.py'):
        # Save uploaded file temporarily
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)
        
        # Get API key from form
        api_key = request.form.get('api_key', None)
        
        # Run the pipeline
        try:
            final_state = run(filepath, api_key)
            report_path = final_state['report_path']
            if os.path.exists(report_path):
                # Redirect to report page
                return redirect(url_for('show_report', report_filename=os.path.basename(report_path)))
            else:
                return 'Report generation failed'
        except Exception as e:
            return f'Error running pipeline: {str(e)}'
    else:
        return 'Invalid file type. Please upload a .py file'

@app.route('/report/<report_filename>')
def show_report(report_filename):
    report_path = os.path.join(app.config['UPLOAD_FOLDER'], report_filename)
    if os.path.exists(report_path):
        return send_file(report_path)
    else:
        return 'Report not found'

if __name__ == '__main__':
    app.run(debug=True)