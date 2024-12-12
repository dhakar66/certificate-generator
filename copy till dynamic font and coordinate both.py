import pandas as pd # type: ignore
from PIL import Image, ImageDraw, ImageFont # type: ignore
import os
import re
from fpdf import FPDF # type: ignore
from flask import Flask, request, render_template, send_file, flash, redirect, url_for # type: ignore
from werkzeug.utils import secure_filename # type: ignore
from io import BytesIO

# suppress the warning and allow Pillow to handle larger images without quality loss.
Image.MAX_IMAGE_PIXELS = None

app = Flask(__name__)

# Configuration
UPLOAD_FOLDER = "static/uploads"
CERTIFICATE_FOLDER = "static/certificates"
app.secret_key = 'your_secret_key'

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER 
app.config['CERTIFICATE_FOLDER'] = CERTIFICATE_FOLDER  

# Ensure folders exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['CERTIFICATE_FOLDER'], exist_ok=True)

# route for the upload page.
@app.route("/")
def upload_file():
    return render_template("upload.html")


# handle file uploads and certificate generation
def generate_certificate(data_row, template_path, output_path, column_coordinates, column_fonts):
    template = Image.open(template_path)
    draw = ImageDraw.Draw(template)
    

    
    # Iterate through column names and coordinates
    for column, coord_str in column_coordinates.items():
        if column not in data_row:
            continue  # Skip if column is not in the Excel row

        # Parse coordinates
        try:
            x1, y1, x2, y2 = map(int, coord_str.split(","))
        except ValueError:
            print(f"Invalid coordinates for column {column}: {coord_str}")
            continue
        
        font_path = column_fonts.get(column, "Baskerville.ttc")  # Use a default font if not provided
        font = ImageFont.truetype(font_path, 250)

        # Get text content
        text = str(data_row[column])

        # Measure text and adjust font size dynamically
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        box_width = x2 - x1

        if text_width > box_width:
            font_size = int(font.size * (box_width / text_width))
            font = ImageFont.truetype(font_path, font_size)

        # Center the text within the box
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_x = x1 + (box_width - (text_bbox[2] - text_bbox[0])) // 2
        text_y = y1 + ((y2 - y1) - (text_bbox[3] - text_bbox[1])) // 2

        # Draw the text
        draw.text((text_x, text_y), text, fill="black", font=font)

    # Save the certificate
    template.save(output_path, "PDF", resolution=100.0)
    print(f"Certificate generated at {output_path}")


# **************************************************************************************************

# CREATING A FUNCTION THAT GENERATES CERTIFICATES FOR ALL THE PARTICIPANTS
@app.route('/generate', methods=['POST'])
def handle_upload():
    if 'template' not in request.files or 'data' not in request.files:
        flash('Both files are required!')
        return redirect(url_for('upload_file'))
    # all the variables or the values or the data is coming from upload.html file. where the user enters everything manually
    # The template file (image) and data file (Excel) are accessed using their respective names (template and data) specified in the HTML form.
    template_file = request.files['template']
    data_file = request.files['data']

    # Secure filenames --- are used to sanitize the filenames of two uploaded files, ensuring they are safe and secure before further processing or saving to the server.
    # secure_filename(): Ensures the file names are safe for saving on the server.

     # Retrieve and save fonts
    column_fonts = {}
    for column_name in request.form.get('column_names', '').split(','):
        column_name = column_name.strip()
        font_key = f'font_{column_name}'  # The input name for the font file
        if font_key in request.files:
            font_file = request.files[font_key]
            font_filename = secure_filename(font_file.filename)
            font_path = os.path.join(app.config['UPLOAD_FOLDER'], font_filename)
            font_file.save(font_path)
            column_fonts[column_name] = font_path
    

    template_filename = secure_filename(template_file.filename)
    data_filename = secure_filename(data_file.filename)

    template_path = os.path.join(app.config['UPLOAD_FOLDER'], template_filename)
    data_path = os.path.join(app.config['UPLOAD_FOLDER'], data_filename)


    # Save files
    template_file.save(template_path)
    data_file.save(data_path)

    column_coordinates = {}
    for column_name in request.form.get('column_names', '').split(','):
        column_name = column_name.strip()
        key = f"coordinates_{column_name}"
        column_coordinates[column_name] = request.form.get(key)

    # Get the naming convention from the user input
    generation_mode = request.form.get('generation_mode')
    naming_convention = request.form.get('naming_convention')

    if not naming_convention:
        flash('Please provide a naming convention for the PDFs.')
        return redirect(url_for('upload_file'))
    
    data = pd.read_excel(data_path, engine='openpyxl')
    output_folder = app.config['CERTIFICATE_FOLDER']

# ------------------- only if the generation mode is range ----------------------------
    if generation_mode == 'range':
        # asking user to enter the value
        try:
            start = int(request.form.get('start', 1)) - 1  # Default: start from 1st row
            end = int(request.form.get('end', 0))         # Default: process all rows
        except ValueError:
            flash('Please provide valid integer values for start and end rows.')
            return redirect(url_for('upload_file'))
        
        if end == 0 or end > len(data):  # Adjust 'end' to process all rows if not specified
            end = len(data)

        if start < 0 or start >= len(data) or start >= end:
            flash('Invalid range. Please check your start and end values.')
            return redirect(url_for('upload_file'))
        
        
        for index, row in data.iloc[start:end].iterrows():
            output_filename = naming_convention.format(**row.to_dict(), index=index+1)
            sanitized_name = re.sub(r'[\\/*?:"<>|]', "_", output_filename)
            output_path = os.path.join(output_folder, f"{sanitized_name}.pdf")
            generate_certificate(row, template_path, output_path, column_coordinates, column_fonts)


        flash(f'Certificates generated successfully for rows {start + 1} to {end}.')
        return redirect(url_for('upload_file'))
    # -------------- if the the generation mode is specific ----------------------
    elif generation_mode == "specific":
        # serial number is coming from the form.
        serial_number = request.form.get('serial_number')

        if not serial_number:
            flash("Please enter a serial number")
            return redirect(url_for('upload_file'))
        
        try: 
            serial_number = int(serial_number)
        except:
            flash("Please enter a valid serial number")
            return redirect(url_for('upload_file'))
        
        # Adjust for 1-based index
        index = serial_number - 1

        if index < 0 or index >= len(data):
            flash(f'Invalid serial number: {serial_number}. No participant found.')
            return redirect(url_for('upload_file'))

        # Generate certificate for the specific participant
        participant_row = data.iloc[index]
        output_filename = naming_convention.format(**participant_row.to_dict(), index=index+1)
        sanitized_name = re.sub(r'[\\/*?:"<>|]', "_", output_filename)
        output_path = os.path.join(output_folder, f"{sanitized_name}.pdf")

        generate_certificate(participant_row, template_path, output_path, column_coordinates, column_fonts)

        flash(f'Certificate generated successfully for {participant_row["name"]}.')
        return redirect(url_for('upload_file'))
    
    else:
        flash("Invalid genration mode selected.")
        return redirect(url_for("upload_file"))
    
    return redirect(url_for('upload_file'))


if __name__ == '__main__':
    app.run(debug=True)
