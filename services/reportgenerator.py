import json 
import os 

def save_reports(report_data , filename = "report.json"):
    os.makedirs("reports", exist_ok=True)
    report_path = os.path.join("reports" , filename)
    with open(report_path, "w") as f:
        json.dump(report_data, f, indent=4)
    return report_path