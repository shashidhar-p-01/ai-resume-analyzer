import datetime
import json 
import os 
import datetime
import re



def save_reports(report_data):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    name = report_data.get("candidate_name","unknown")
    role = report_data.get("candidate_role","unknown")

    name = re.sub(r"[^a-zA-Z0-9_-]","_",name.lower())
    role = re.sub(r"[^a-zA-Z0-9_-]","_",role.lower())

    filename = f"{name}_{role}_{timestamp}.json"
    os.makedirs("reports", exist_ok=True)
    report_path = os.path.join("reports" , filename)
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=4)
    return report_path
