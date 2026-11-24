
import streamlit as st
import sqlite3
import os
import json
import pandas as pd
import mimetypes

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
DB = "civicpulse.db"
MODEL = "gemini-3.8-flash"

st.set_page_config(
    page_title="CivicPulse AI",
    page_icon="🏙️",
    layout="wide"
)


# ---------------- DATABASE ----------------

def init_db():
    conn = sqlite3.connect(DB)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            issue TEXT,
            category TEXT,
            severity TEXT,
            department TEXT,
            location TEXT,
            description TEXT,
            recommendation TEXT,
            letter TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------------- SAVE COMPLAINT ----------------

def save_complaint(data):
    conn = sqlite3.connect(DB)

    conn.execute("""
        INSERT INTO complaints
        (issue, category, severity, department, location,
         description, recommendation, letter)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data["issue"],
        data["category"],
        data["severity"],
        data["department"],
        data["location"],
        data["description"],
        data["recommendation"],
        data["letter"]
    ))

    conn.commit()
    conn.close()


# ---------------- GET COMPLAINTS ----------------

def get_complaints():
    conn = sqlite3.connect(DB)

    df = pd.read_sql_query(
        "SELECT * FROM complaints ORDER BY id DESC",
        conn
    )

    conn.close()
    return df


# ---------------- UPDATE STATUS ----------------

def update_status(cid, status):
    conn = sqlite3.connect(DB)

    conn.execute(
        "UPDATE complaints SET status=? WHERE id=?",
        (status, cid)
    )

    conn.commit()
    conn.close()


# ---------------- GEMINI IMAGE ANALYSIS ----------------

def analyze_image(image, description, location, mime_type):
    client = genai.Client(api_key=API_KEY)

    prompt = f"""
    Analyse this civic problem image and citizen description.

    Citizen description: {description}
    Location: {location}

    Identify the civic issue and return ONLY valid JSON:

    {{
      "issue": "short issue name",
      "category": "Roads, Water, Sanitation, Electricity or Other",
      "severity": "Low, Medium, High or Critical",
      "department": "suggested responsible department",
      "description": "clear explanation of the problem",
      "recommendation": "suggested action"
    }}

    Estimate severity based on visible evidence.
    Do not invent facts that cannot be seen or confirmed.
    """

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            prompt,
            types.Part.from_bytes(
                data=image,
                mime_type=mime_type
            )
        ]
    )

    result = response.text.strip()

    result = result.replace("```json", "")
    result = result.replace("```", "").strip()

    return json.loads(result)


# ---------------- GEMINI COMPLAINT LETTER ----------------

def generate_letter(data, location, citizen_description):
    client = genai.Client(api_key=API_KEY)

    prompt = f"""
    Write a polite and formal civic complaint letter.

    Issue: {data['issue']}
    Location: {location}
    Citizen description: {citizen_description}
    Department: {data['department']}
    Recommendation: {data['recommendation']}

    Request the concerned department to inspect and resolve the issue.
    Do not invent personal details or official information.
    """

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt
    )

    return response.text


# ---------------- BACKUP ANALYSIS ----------------

def fallback_analysis(description):
    text_input = description.lower()

    if "pothole" in text_input or "road" in text_input:
        return {
            "issue": "Pothole on Road",
            "category": "Roads",
            "severity": "High",
            "department": "Municipal Roads Department",
            "description": description,
            "recommendation": "Inspect and repair the pothole to reduce road accidents."
        }

    elif "garbage" in text_input or "waste" in text_input:
        return {
            "issue": "Garbage Dumping",
            "category": "Sanitation",
            "severity": "Medium",
            "department": "Sanitation Department",
            "description": description,
            "recommendation": "Remove the dumped garbage and clean the affected area."
        }

    elif "water" in text_input or "leak" in text_input:
        return {
            "issue": "Water Leakage",
            "category": "Water",
            "severity": "High",
            "department": "Water Supply Department",
            "description": description,
            "recommendation": "Inspect and repair the water leakage."
        }

    elif "light" in text_input or "electric" in text_input:
        return {
            "issue": "Broken Streetlight",
            "category": "Electricity",
            "severity": "Medium",
            "department": "Electrical Department",
            "description": description,
            "recommendation": "Inspect and repair or replace the streetlight."
        }

    else:
        return {
            "issue": "General Civic Problem",
            "category": "Other",
            "severity": "Medium",
            "department": "Municipal Department",
            "description": description,
            "recommendation": "Inspect the reported issue and take appropriate action."
        }


# ---------------- BACKUP LETTER ----------------

def fallback_letter(data, location, description):
    return f"""
To,
The {data['department']}

Subject: Complaint regarding {data['issue']}

Dear Sir/Madam,

I would like to report a civic issue at {location}.

Problem: {description}

Severity: {data['severity']}

I kindly request the concerned department to inspect
this issue and take appropriate action as soon as possible.

Recommended action: {data['recommendation']}

Thank you for your attention.

Regards,
Concerned Citizen
"""


# ---------------- SIDEBAR ----------------

st.sidebar.title("🏙️ CivicPulse AI")

page = st.sidebar.radio(
    "Navigation",
    ["Report an Issue", "Admin Dashboard"]
)

st.title("🏙️ CivicPulse AI")
st.caption("Detect. Prioritize. Resolve.")


# ================= CITIZEN PAGE =================

if page == "Report an Issue":

    st.header("Report a Civic Problem")

    uploaded_file = st.file_uploader(
        "Upload an issue image",
        type=["jpg", "jpeg", "png"]
    )

    description = st.text_area(
        "Describe the problem",
        placeholder="Example: A large pothole is present near the bus stop."
    )

    location = st.text_input(
        "Location",
        placeholder="Enter street, area and city"
    )

    if st.button("Analyse with AI", type="primary"):

        if uploaded_file is None:
            st.error("Please upload an image.")

        elif not description.strip():
            st.error("Please describe the problem.")

        elif not location.strip():
            st.error("Please enter the location.")

        else:

            with st.spinner("Analysing your civic problem..."):

                image_bytes = uploaded_file.getvalue()

                mime_type = (
                    uploaded_file.type
                    or mimetypes.guess_type(uploaded_file.name)[0]
                    or "image/jpeg"
                )

                # ---- ANALYSIS ----

                try:

                    if not API_KEY:
                        raise Exception("Gemini API key is missing.")

                    analysis = analyze_image(
                        image_bytes,
                        description,
                        location,
                        mime_type
                    )

                    analysis_method = "Gemini AI"

                except Exception as e:

                    analysis = fallback_analysis(description)

                    analysis_method = "Backup Rule-Based Analysis"

                # ---- LETTER ----

                try:

                    if API_KEY:
                        letter = generate_letter(
                            analysis,
                            location,
                            description
                        )

                        letter_method = "Gemini AI"

                    else:
                        raise Exception("Gemini API key is missing.")

                except Exception:

                    letter = fallback_letter(
                        analysis,
                        location,
                        description
                    )

                    letter_method = "Backup Template"

                # ---- STORE IN SESSION ----

                analysis["letter"] = letter

                st.session_state["analysis"] = analysis
                st.session_state["location"] = location
                st.session_state["description"] = description
                st.session_state["saved"] = False

                st.session_state["analysis_method"] = analysis_method
                st.session_state["letter_method"] = letter_method


    # ---- DISPLAY RESULTS ----

    if "analysis" in st.session_state:

        data = st.session_state["analysis"]

        st.subheader("Analysis Results")

        if st.session_state["analysis_method"] == "Gemini AI":

            st.success("Issue analysis completed using Gemini AI.")

        else:

            st.warning(
                "Gemini was unavailable. This result is based on "
                "description-based backup rules, not image AI analysis."
            )

        st.write("**Issue:**", data["issue"])
        st.write("**Category:**", data["category"])
        st.write("**Severity:**", data["severity"])
        st.write("**Suggested Department:**", data["department"])

        st.write("**Description:**")
        st.write(data["description"])

        st.write("**Recommended Action:**")
        st.write(data["recommendation"])

        st.subheader("Generated Complaint Letter")

        if st.session_state["letter_method"] == "Gemini AI":
            st.caption("Letter generated using Gemini AI.")
        else:
            st.caption("Letter generated using a backup template.")

        st.text_area(
            "Complaint letter",
            value=data["letter"],
            height=250
        )

        # ---- SUBMIT COMPLAINT ----

        if not st.session_state.get("saved", False):

            if st.button("Submit Complaint", type="primary"):

                save_complaint({
                    **data,
                    "location": st.session_state["location"]
                })

                st.session_state["saved"] = True

                st.success("Complaint submitted successfully!")

                st.rerun()

        else:

            st.success("This complaint has already been submitted.")


# ================= ADMIN DASHBOARD =================

elif page == "Admin Dashboard":

    st.header("Admin Dashboard")

    df = get_complaints()

    if df.empty:

        st.info("No complaints submitted yet.")

    else:

        total = len(df)

        pending = len(
            df[df["status"] == "Pending"]
        )

        resolved = len(
            df[df["status"] == "Resolved"]
        )

        high = len(
            df[df["severity"].isin(["High", "Critical"])]
        )

        # ---- METRICS ----

        c1, c2, c3, c4 = st.columns(4)

        c1.metric("Total Complaints", total)
        c2.metric("Pending", pending)
        c3.metric("Resolved", resolved)
        c4.metric("High Priority", high)

        # ---- CHARTS ----

        st.subheader("Complaints by Category")

        st.bar_chart(
            df["category"].value_counts()
        )

        st.subheader("Complaints by Severity")

        st.bar_chart(
            df["severity"].value_counts()
        )

        # ---- RECORDS ----

        st.subheader("Complaint Records")

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )

        # ---- STATUS UPDATE ----

        st.subheader("Update Complaint Status")

        complaint_id = st.selectbox(
            "Select Complaint ID",
            df["id"].tolist()
        )

        new_status = st.selectbox(
            "New Status",
            ["Pending", "In Progress", "Resolved"]
        )

        if st.button("Update Status"):

            update_status(
                complaint_id,
                new_status
            )

            st.success("Status updated!")

            st.rerun()

        # ---- CSV DOWNLOAD ----

        st.subheader("Download Report")

        csv = df.to_csv(index=False).encode("utf-8")

        st.download_button(
            "Download Complaints CSV",
            data=csv,
            file_name="civic_complaints.csv",
            mime="text/csv"
        )
