# this code is responsible for 
# read resume.pdf
# read jd.pdf 
# return plain text of both files

import pypdf



def extract_text(file_path):
    reader = pypdf.PdfReader(file_path)
    text = ""
    for page in reader.pages:
        page_text = page.extract_text()

        if page_text:
            text = text +page_text + "\n"
        
    return text.strip()

