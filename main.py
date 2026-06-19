import json
import time 
import glob
from services.pdfreader import extract_text 
from services.prompbuilder import build_prompt
from services.llmservice import generate_response
from services.reportgenerator import save_reports




RESUME_DIR = "data/resumes"
JD_DIR = "data/jd"

all_results = []


resume_files = sorted(glob.glob(f"{RESUME_DIR}/*.pdf"))
print(f"found {len(resume_files)} file(s)")
for f in resume_files:
    print(f"- {f}\n")



# resume_text = extract_text("data/resume.pdf")   #this is for a single file 
jd_files = glob.glob(f"{JD_DIR}/*.pdf")
jd_text = extract_text(jd_files[0])

for resume_file in resume_files:

    print(f"processing {resume_file}")

    resume_start = time.time()

    resume_text = extract_text(resume_file)

    prompt = build_prompt(resume_text, jd_text)

    llm_start = time.time()

    analysis = generate_response(prompt)

    llm_end = time.time()

    resume_end = time.time()

    try:
        analysis_dict = json.loads(analysis)
        analysis_dict["resume_file"] = resume_file
        analysis_dict["total_runtime_seconds"] = resume_end - resume_start
        analysis_dict["llm_runtime_seconds"] = llm_end - llm_start
        analysis_dict["processing_runtime_seconds"] = (resume_end - resume_start) - (llm_end - llm_start)


    except json.JSONDecodeError as e:
        print("\nJSON ERROR:")
        print(e)

        print("\nRAW RESPONSE:")
        print(analysis)

        continue 
    report_path = save_reports(analysis_dict)
    all_results.append(
        {
            "candidate_name" : analysis_dict.get("candidate_name" , "unknown"),
            "match_score" : analysis_dict.get("match_score" , 0),
            "report_path" : report_path
        }
    )
    print(f"match score = {analysis_dict.get("match_score","N/A")}")
    print(f"Report saved at : {report_path}")

print("/n" + "="*30)
print("CANDIDATE RANKING")
print("/n" + "="*30)

all_results.sort(
    key = lambda x : x["match_score"],
    reverse = True
)

for rank,candidate in enumerate(all_results, start = 1 ):
    print(
        f"{rank} . "
        f"{candidate["candidate_name"]}"
        f"({candidate["match_score"]}%)"
    )
    

# print("="*50)
# print("Resume Text:")
# print("="*50)
# print(resume_text)

# print("\n\n")

# print("="*50)
# print("Job Description Text:")
# print("="*50)
# print(jd_text)

# print("\n\n")

# print(f"resume length : {len(resume_text)} characters")
# print(f"jd length : {len(jd_text)} characters")

# prompt = build_prompt(resume_text, jd_text)
# print(prompt)

# print(f"resume length : {len(resume_text)} characters")
# print(f"jd length : {len(jd_text)} characters")
# print(f"prompt length : {len(prompt)} characters")

# llm_start = time.time()

# analysis = generate_response(prompt)
# print(analysis)

# llm_end = time.time()

# print("\n\n")
# print("="*50)
# print("RESUME ANALYSIS:")
# print("="*50)
# print(analysis)

# total_end = time.time()

# try:
#     analysis_dict = json.loads(analysis)
#     analysis_dict["total_runtime_seconds"] = total_end - total_start
#     analysis_dict["llm_runtime_seconds"] = llm_end - llm_start
#     analysis_dict["processing_runtime_seconds"] = (total_end - total_start) - (llm_end - llm_start)


# except json.JSONDecodeError as e:
#     print("\nJSON ERROR:")
#     print(e)

#     print("\nRAW RESPONSE:")
#     print(analysis)

#     exit()


# report_path = save_reports(analysis_dict)
# print(f"Report saved at : {report_path}")

