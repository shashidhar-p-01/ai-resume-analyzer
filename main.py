import json
import time 
from services.pdfreader import extract_text 
from services.prompbuilder import build_prompt
from services.llmservice import generate_response
from services.reportgenerator import save_reports



total_start = time.time()

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

llm_start = time.time()

analysis = generate_response(prompt)
print(analysis)

llm_end = time.time()

print("\n\n")
print("="*50)
print("RESUME ANALYSIS:")
print("="*50)
print(analysis)

total_end = time.time()

try:
    analysis_dict = json.loads(analysis)
    analysis_dict["total_runtime_seconds"] = total_end - total_start
    analysis_dict["llm_runtime_seconds"] = llm_end - llm_start
    analysis_dict["processing_runtime_seconds"] = (total_end - total_start) - (llm_end - llm_start)


except json.JSONDecodeError as e:
    print("\nJSON ERROR:")
    print(e)

    print("\nRAW RESPONSE:")
    print(analysis)

    exit()


report_path = save_reports(analysis_dict)
print(f"Report saved at : {report_path}")

