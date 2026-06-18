from services.pdfreader import extract_text 
from services.prompbuilder import build_prompt
from services.llmservice import generate_response

resume_text = extract_text("data/resume.pdf")
jd_text = extract_text("data/jd.pdf")

print("="*50)
print("Resume Text:")
print("="*50)
print(resume_text)

print("\n\n")

print("="*50)
print("Job Description Text:")
print("="*50)
print(jd_text)

print("\n\n")

print(f"resume length : {len(resume_text)} characters")
print(f"jd length : {len(jd_text)} characters")

prompt = build_prompt(resume_text, jd_text)
print(prompt)

print(f"resume length : {len(resume_text)} characters")
print(f"jd length : {len(jd_text)} characters")
print(f"prompt length : {len(prompt)} characters")

analysis = generate_response(prompt)
print(analysis)

print("\n\n")
print("="*50)
print("RESUME ANALYSIS:")
print("="*50)
print(analysis)
