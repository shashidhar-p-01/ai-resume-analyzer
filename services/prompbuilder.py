def build_prompt(resume_text, jd_text):
    prompt = f"""
you are an expert ATS (Application Tracking System ) and resume reviewer . 

your task is to compare the candidate's resume with the job description . 

Analyze the resume and provide : 
1. match score (0-100)
2. Matching skills 
3. missing skills 
4. strengths 
5. weaknesses 
6. recommendations to improve the resume to match the job description

JOB DESCRIPTION :
{jd_text}
CANDIDATE RESUME :
{resume_text}

OUTPUT FORMAT :
1. Match Score : <match score>
2. Matching Skills : 
-...
3. Missing Skills : 
-...
4. Strengths : 
-...
5. Weaknesses : 
-...
6. Recommendations : 
-...
"""
    return prompt.strip()