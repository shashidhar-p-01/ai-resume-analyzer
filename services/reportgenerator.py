import datetime
import json 
import os 
import datetime

timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


def save_reports(report_data):
    name = report_data.get("candidate_name","unknown")
    role = report_data.get("candidate_role","unknown")
    name = name.lower().replace(" ", "_")
    role = role.lower().replace(" ", "_")
    filename = f"{name}_{role}_{timestamp}.json"
    os.makedirs("reports", exist_ok=True)
    report_path = os.path.join("reports" , filename)
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=4)
    return report_path
