"""
ui_integration.py — Flask backend for the AI Resume Analyzer UI.
Wraps main.py pipeline logic into HTTP endpoints consumed by index.html.
"""

import json
import os
import time
import glob
import tempfile
import shutil
import threading

from flask import Flask, request, jsonify, Response, stream_with_context, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from services.pdfreader import extract_text
from services.prompbuilder import build_prompt
from services.llmservice import generate_response
from services.reportgenerator import save_reports

load_dotenv()

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

REPORTS_DIR = "reports"
os.makedirs(REPORTS_DIR, exist_ok=True)

RESUMES_DIR = "data/resumes"
os.makedirs(RESUMES_DIR, exist_ok=True)

JD_DIR = "data/jd"
os.makedirs(JD_DIR, exist_ok=True)


# ── Serve the UI ──────────────────────────────────────────────────────────────

@app.route("/")
def serve_ui():
    return send_from_directory(".", "index.html")


# ── Model info ────────────────────────────────────────────────────────────────

@app.route("/api/model-info", methods=["GET"])
def model_info():
    return jsonify({
        "model_name": os.getenv("MODEL_NAME", "unknown"),
        "ollama_url": os.getenv("OLLAMA_URL", "http://localhost:11434"),
    })


# ── Analyse endpoint (SSE streaming) ─────────────────────────────────────────

@app.route("/api/analyse", methods=["POST"])
def analyse():
    """
    Accepts multipart/form-data:
      - resume_files: one or more PDF files
      - jd_file:      a PDF file  (optional if jd_text provided)
      - jd_text:      raw text    (optional if jd_file provided)

    Streams Server-Sent Events (SSE) back to the client.
    Each event is a JSON object with a `type` field.
    """

    resume_files_uploaded = request.files.getlist("resume_files")
    jd_file_uploaded = request.files.get("jd_file")
    jd_text_input = request.form.get("jd_text", "").strip()

    stored_resumes_list = request.form.getlist("stored_resumes")
    use_all_stored = request.form.get("use_all_stored_resumes") == "true"
    stored_jd_filename = request.form.get("stored_jd")

    # Write uploaded files to a temp dir so sub-processes can read them
    tmp_dir = tempfile.mkdtemp(prefix="ai_resume_")

    resume_paths = []

    # 1. Process uploaded resume files
    for rf in resume_files_uploaded:
        if rf.filename:
            path = os.path.join(tmp_dir, rf.filename)
            rf.save(path)
            resume_paths.append(path)
            
            # Save copy permanently
            perm_path = os.path.join(RESUMES_DIR, rf.filename)
            shutil.copy2(path, perm_path)

    # 2. Add stored resumes
    if use_all_stored:
        if os.path.exists(RESUMES_DIR):
            for filename in os.listdir(RESUMES_DIR):
                if filename.lower().endswith(".pdf"):
                    resume_paths.append(os.path.join(RESUMES_DIR, filename))
    elif stored_resumes_list:
        for item in stored_resumes_list:
            filenames = [f.strip() for f in item.split(",") if f.strip()]
            for fname in filenames:
                filepath = os.path.join(RESUMES_DIR, fname)
                if os.path.exists(filepath):
                    resume_paths.append(filepath)

    # De-duplicate paths
    seen = set()
    unique_paths = []
    for p in resume_paths:
        real_p = os.path.realpath(p)
        if real_p not in seen:
            seen.add(real_p)
            unique_paths.append(p)
    resume_paths = unique_paths

    if not resume_paths:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return jsonify({"error": "No resume files provided"}), 400

    jd_path = None
    jd_name = "Pasted Text"

    # 1. Check if new JD file uploaded
    if jd_file_uploaded and jd_file_uploaded.filename:
        jd_path = os.path.join(tmp_dir, jd_file_uploaded.filename)
        jd_file_uploaded.save(jd_path)
        jd_name = jd_file_uploaded.filename
        
        # Save a copy to permanent JD library
        perm_jd_path = os.path.join(JD_DIR, jd_file_uploaded.filename)
        shutil.copy2(jd_path, perm_jd_path)
        
    # 2. Check if stored JD selected
    elif stored_jd_filename:
        perm_jd_path = os.path.join(JD_DIR, stored_jd_filename)
        if os.path.exists(perm_jd_path):
            jd_path = perm_jd_path
            jd_name = stored_jd_filename
            
    # 3. Check if pasted JD text
    elif jd_text_input:
        jd_name = "Pasted Text"

    if not jd_path and not jd_text_input:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return jsonify({"error": "No JD provided"}), 400

    def generate():
        nonlocal jd_name
        try:
            # ── Step 1: JD extraction ────────────────────────────────────────
            yield _sse("step", {"step": "jd_extraction", "status": "running",
                                 "label": "Extracting Job Description"})

            if jd_path:
                jd_text = extract_text(jd_path)
            else:
                jd_text = jd_text_input
                jd_name_local = "Pasted Text"

            yield _sse("step", {"step": "jd_extraction", "status": "done",
                                 "label": "Job Description Ready",
                                 "jd_name": jd_name,
                                 "jd_chars": len(jd_text)})

            all_results = []
            session_start = time.time()
            jd_name_set = False


            for idx, resume_path in enumerate(resume_paths):
                fname = os.path.basename(resume_path)

                # ── Step: Resume extraction ──────────────────────────────────
                yield _sse("step", {"step": f"resume_{idx}_extract",
                                     "status": "running",
                                     "label": f"Reading resume: {fname}",
                                     "resume_index": idx,
                                     "resume_name": fname,
                                     "total": len(resume_paths)})

                resume_start = time.time()
                resume_text = extract_text(resume_path)

                yield _sse("step", {"step": f"resume_{idx}_extract",
                                     "status": "done",
                                     "label": f"Resume extracted: {fname}",
                                     "resume_index": idx,
                                     "resume_name": fname,
                                     "chars": len(resume_text)})

                # ── Step: Prompt build ───────────────────────────────────────
                yield _sse("step", {"step": f"resume_{idx}_prompt",
                                     "status": "running",
                                     "label": f"Building prompt for: {fname}",
                                     "resume_index": idx})

                prompt = build_prompt(resume_text, jd_text)
                
                # Ask the LLM to also extract/generate a proper name for the JD
                prompt += "\n\nCRITICAL: Please also extract or generate a short, professional title/name for this job description (e.g. 'Senior Software Engineer' or 'Data Analyst') and return it as the 'jd_name' field in the JSON object."
                prompt = prompt.replace(
                    '"candidate_name": "",',
                    '"candidate_name": "",\n    "jd_name": "Short Professional Job Title",',
                )

                yield _sse("step", {"step": f"resume_{idx}_prompt",
                                     "status": "done",
                                     "label": "Prompt ready",
                                     "resume_index": idx,
                                     "prompt_chars": len(prompt)})

                # ── Step: LLM call ───────────────────────────────────────────
                yield _sse("step", {"step": f"resume_{idx}_llm",
                                     "status": "running",
                                     "label": f"Running LLM on: {fname}",
                                     "resume_index": idx})

                llm_start = time.time()
                analysis_raw = generate_response(prompt)
                llm_end = time.time()
                resume_end = time.time()

                # ── Step: Parse JSON ─────────────────────────────────────────
                yield _sse("step", {"step": f"resume_{idx}_parse",
                                     "status": "running",
                                     "label": "Parsing LLM response",
                                     "resume_index": idx})

                analysis_dict = None
                parse_error = None
                try:
                    analysis_dict = json.loads(analysis_raw)
                except json.JSONDecodeError as e:
                    parse_error = str(e)
                    # Try json-repair if available
                    try:
                        from json_repair import repair_json
                        analysis_dict = json.loads(repair_json(analysis_raw))
                        parse_error = None
                    except Exception:
                        pass

                if analysis_dict is None:
                    yield _sse("step", {"step": f"resume_{idx}_parse",
                                         "status": "error",
                                         "label": f"JSON parse failed: {parse_error}",
                                         "resume_index": idx})
                    continue

                # ── Enrich dict ──────────────────────────────────────────────
                analysis_dict["resume_file"] = fname
                
                llm_jd_name = analysis_dict.get("jd_name", "").strip()
                if llm_jd_name and not jd_name_set:
                    jd_name = llm_jd_name
                    jd_name_set = True
                
                analysis_dict["jd_name"] = jd_name
                analysis_dict["total_runtime_seconds"] = resume_end - resume_start
                analysis_dict["llm_runtime_seconds"] = llm_end - llm_start
                analysis_dict["processing_runtime_seconds"] = (
                    (resume_end - resume_start) - (llm_end - llm_start)
                )

                yield _sse("step", {"step": f"resume_{idx}_parse",
                                     "status": "done",
                                     "label": "Response parsed",
                                     "resume_index": idx})

                # ── Step: Save report ────────────────────────────────────────
                yield _sse("step", {"step": f"resume_{idx}_save",
                                     "status": "running",
                                     "label": "Saving report",
                                     "resume_index": idx})

                report_path = save_reports(analysis_dict)

                yield _sse("step", {"step": f"resume_{idx}_save",
                                     "status": "done",
                                     "label": f"Report saved",
                                     "resume_index": idx,
                                     "report_path": report_path})

                # ── Emit individual result ───────────────────────────────────
                all_results.append({
                    "candidate_name": analysis_dict.get("candidate_name", "Unknown"),
                    "candidate_role": analysis_dict.get("candidate_role", ""),
                    "match_score":    analysis_dict.get("match_score", 0),
                    "matching_skills": analysis_dict.get("matching_skills", []),
                    "missing_skills":  analysis_dict.get("missing_skills", []),
                    "strengths":       analysis_dict.get("strengths", []),
                    "weaknesses":      analysis_dict.get("weaknesses", []),
                    "recommendations": analysis_dict.get("recommendations", []),
                    "resume_file":     fname,
                    "jd_name":         jd_name,
                    "report_path":     report_path,
                    "total_runtime_seconds":      analysis_dict.get("total_runtime_seconds", 0),
                    "llm_runtime_seconds":        analysis_dict.get("llm_runtime_seconds", 0),
                    "processing_runtime_seconds": analysis_dict.get("processing_runtime_seconds", 0),
                })

                yield _sse("candidate_result", all_results[-1])

            # ── Final ranking ────────────────────────────────────────────────
            session_end = time.time()
            all_results.sort(key=lambda x: x["match_score"], reverse=True)

            yield _sse("complete", {
                "ranking":              all_results,
                "total_session_time":   round(session_end - session_start, 2),
                "jd_name":              jd_name,
                "model_name":           os.getenv("MODEL_NAME", "unknown"),
            })

        except Exception as exc:
            yield _sse("error", {"message": str(exc)})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Reports history ───────────────────────────────────────────────────────────

@app.route("/api/reports", methods=["GET"])
def list_reports():
    """Return all saved JSON reports, grouped by JD name, sorted by match_score."""
    report_files = sorted(
        glob.glob(os.path.join(REPORTS_DIR, "*.json")),
        key=os.path.getmtime,
        reverse=True,
    )

    grouped = {}   # jd_name → list of report summaries

    for rp in report_files:
        try:
            with open(rp) as f:
                data = json.load(f)
        except Exception:
            continue

        jd_name = data.get("jd_name", "Unknown JD")
        entry = {
            "file":        os.path.basename(rp),
            "path":        rp,
            "mtime":       os.path.getmtime(rp),
            "candidate_name":  data.get("candidate_name", "Unknown"),
            "candidate_role":  data.get("candidate_role", ""),
            "match_score":     data.get("match_score", 0),
            "resume_file":     data.get("resume_file", ""),
            "jd_name":         jd_name,
            "total_runtime_seconds":      data.get("total_runtime_seconds", 0),
            "llm_runtime_seconds":        data.get("llm_runtime_seconds", 0),
            "processing_runtime_seconds": data.get("processing_runtime_seconds", 0),
            "matching_skills":  data.get("matching_skills", []),
            "missing_skills":   data.get("missing_skills", []),
            "strengths":        data.get("strengths", []),
            "weaknesses":       data.get("weaknesses", []),
            "recommendations":  data.get("recommendations", []),
        }

        grouped.setdefault(jd_name, []).append(entry)

    # Sort each group by match_score desc
    for jd in grouped:
        grouped[jd].sort(key=lambda x: x["match_score"], reverse=True)

    return jsonify(grouped)


@app.route("/api/reports/<path:filename>", methods=["GET"])
def get_report(filename):
    return send_from_directory(REPORTS_DIR, filename)


@app.route("/api/reports/delete-jd", methods=["POST"])
def delete_jd_reports():
    """Delete all JSON reports matching the given jd_name."""
    try:
        data = request.get_json() or {}
        jd_name = data.get("jd_name")
        if not jd_name:
            return jsonify({"error": "Missing jd_name"}), 400

        deleted_count = 0
        for filename in os.listdir(REPORTS_DIR):
            if filename.lower().endswith(".json"):
                filepath = os.path.join(REPORTS_DIR, filename)
                try:
                    with open(filepath, "r") as f:
                        report_data = json.load(f)
                    if report_data.get("jd_name", "Unknown JD") == jd_name:
                        os.remove(filepath)
                        deleted_count += 1
                except Exception as e:
                    print(f"Error reading/deleting report {filename}: {e}")
                    continue

        return jsonify({"success": True, "deleted_count": deleted_count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Resumes library ───────────────────────────────────────────────────────────

@app.route("/api/resumes", methods=["GET"])
def list_resumes():
    """Return all saved resumes in the resumes library."""
    try:
        resumes_list = []
        if os.path.exists(RESUMES_DIR):
            for filename in os.listdir(RESUMES_DIR):
                if filename.lower().endswith(".pdf"):
                    filepath = os.path.join(RESUMES_DIR, filename)
                    resumes_list.append({
                        "name": filename,
                        "size": os.path.getsize(filepath),
                        "mtime": os.path.getmtime(filepath)
                    })
        # Sort by mtime descending
        resumes_list.sort(key=lambda x: x["mtime"], reverse=True)
        return jsonify(resumes_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/resumes/<path:filename>", methods=["GET"])
def get_resume(filename):
    """Serve a specific resume PDF."""
    return send_from_directory(RESUMES_DIR, filename)


@app.route("/api/resumes/<path:filename>", methods=["DELETE"])
def delete_resume(filename):
    """Delete a specific resume PDF."""
    try:
        filepath = os.path.join(RESUMES_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return jsonify({"success": True})
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── JDs library ───────────────────────────────────────────────────────────────

@app.route("/api/jds", methods=["GET"])
def list_jds():
    """Return all saved JDs in the JDs library."""
    try:
        jds_list = []
        if os.path.exists(JD_DIR):
            for filename in os.listdir(JD_DIR):
                if filename.lower().endswith(".pdf"):
                    filepath = os.path.join(JD_DIR, filename)
                    jds_list.append({
                        "name": filename,
                        "size": os.path.getsize(filepath),
                        "mtime": os.path.getmtime(filepath)
                    })
        # Sort by mtime descending
        jds_list.sort(key=lambda x: x["mtime"], reverse=True)
        return jsonify(jds_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/jds/<path:filename>", methods=["GET"])
def get_jd_file(filename):
    """Serve a specific JD PDF."""
    return send_from_directory(JD_DIR, filename)


@app.route("/api/jds/<path:filename>", methods=["DELETE"])
def delete_jd_file(filename):
    """Delete a specific JD PDF."""
    try:
        filepath = os.path.join(JD_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return jsonify({"success": True})
        return jsonify({"error": "File not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sse(event_type: str, data: dict) -> str:
    payload = json.dumps({"type": event_type, **data})
    return f"data: {payload}\n\n"


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║  AI Resume Analyzer  — UI Integration    ║")
    print("║  http://localhost:5000                   ║")
    print("╚══════════════════════════════════════════╝")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
