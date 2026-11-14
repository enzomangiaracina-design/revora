
import streamlit as st
import pandas as pd

from database import (
    initialize_database,
    get_all_prospects,
    get_prospect_by_id,
    add_interaction,
    get_interactions,
    create_task,
    get_tasks,
    complete_task
)

# ==========================================
# 1. CONFIGURATION
# ==========================================

st.set_page_config(
    page_title="REVORA | Sales Workspace",
    page_icon="⚡",
    layout="wide"
)

initialize_database()

prospects = get_all_prospects()

# ==========================================
# 2. IDENTITE VISUELLE
# ==========================================

st.markdown("""
<style>
    .stApp {
        background-color: #10131D;
        color: #F5F5F7;
    }

    [data-testid="stSidebar"] {
        background-color: #171B29;
    }

    h1, h2, h3 {
        color: #FFFFFF !important;
    }

    div[data-testid="stMetric"] {
        background-color: #202536;
        padding: 18px;
        border-radius: 12px;
        border: 1px solid #303447;
    }

    div[data-testid="stMetricValue"] {
        color: #B9A7FF;
    }

    div[data-testid="stMetricLabel"] {
        color: #AEB3C2;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 3. NAVIGATION
# ==========================================

st.sidebar.markdown("# REVORA")
st.sidebar.caption("SALES WORKSPACE")
st.sidebar.divider()

page = st.sidebar.radio(
    "NAVIGATION",
    [
        "Overview",
        "Prospecting Pipeline",
        "Prospects",
        "Prospect Details",
        "Activity",
        "Objections",
        "AI Copilot",
        "Performance"
    ]
)

st.sidebar.divider()
st.sidebar.caption("VERSION 0.3.0")

# ==========================================
# 4. OVERVIEW
# ==========================================

if page == "Overview":

    st.title("Good morning.")
    st.caption("Here is your prospecting overview.")

    st.divider()

    interactions_count = sum(
        len(get_interactions(p["id"]))
        for p in prospects
    )

    tasks_count = sum(
        len([
            t for t in get_tasks(p["id"])
            if t["status"] == "A faire"
        ])
        for p in prospects
    )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Total prospects", len(prospects))
    col2.metric("Interactions", interactions_count)
    col3.metric("Open follow-ups", tasks_count)
    col4.metric("Companies", len(set(
        p["company_name"] for p in prospects
        if p["company_name"]
    )))

    st.divider()
    st.subheader("Your prospecting database")

    if prospects:
        df = pd.DataFrame(prospects)

        df["Prospect"] = (
            df["first_name"] + " " + df["last_name"]
        )

        df = df.rename(columns={
            "company_name": "Company",
            "vertical": "Vertical",
            "email": "Email",
            "phone": "Phone",
            "job_title": "Job title",
            "status": "Status"
        })

        st.dataframe(
            df[[
                "Prospect",
                "Company",
                "Vertical",
                "Job title",
                "Email",
                "Phone",
                "Status"
            ]],
            width="stretch",
            hide_index=True
        )
    else:
        st.info("Your prospect database is empty.")

# ==========================================
# 5. PROSPECTS
# ==========================================

elif page == "Prospects":

    st.title("Prospect Intelligence")
    st.caption("Your prospect database.")

    if prospects:
        for prospect in prospects:
            with st.container(border=True):
                st.markdown(
                    f"**{prospect['first_name']} "
                    f"{prospect['last_name']}**"
                )
                st.caption(
                    f"{prospect['company_name']} · "
                    f"{prospect['vertical']}"
                )
                st.write(prospect["email"] or "No email")
                st.write(prospect["phone"] or "No phone")
    else:
        st.info("No prospects registered.")

# ==========================================
# 6. PROSPECT DETAILS
# ==========================================

elif page == "Prospect Details":

    st.title("Prospect Details")
    st.caption("Your complete commercial memory.")

    if not prospects:
        st.info("Add a prospect before opening a prospect file.")

    else:

        prospect_options = {
            f"{p['first_name']} {p['last_name']} — {p['company_name']}": p["id"]
            for p in prospects
        }

        selected_name = st.selectbox(
            "Select a prospect",
            list(prospect_options.keys())
        )

        contact_id = prospect_options[selected_name]

        prospect = get_prospect_by_id(contact_id)

        if prospect:

            full_name = (
                prospect["first_name"] + " "
                + prospect["last_name"]
            )

            interactions = get_interactions(contact_id)
            tasks = get_tasks(contact_id)

            st.divider()

            st.title(full_name)
            st.caption(
                f"{prospect['job_title'] or 'Position not specified'}"
                f" · {prospect['company_name']}"
                f" · {prospect['vertical']}"
            )

            # CONTACT INFORMATION

            st.subheader("Contact information")

            col1, col2, col3 = st.columns(3)

            col1.write("**Email**")
            col1.write(prospect["email"] or "Not provided")

            col2.write("**Phone**")
            col2.write(prospect["phone"] or "Not provided")

            col3.write("**Status**")
            col3.write(prospect["status"])

            st.divider()

            # ACTIVITY COUNTERS

            calls_count = sum(
                1 for item in interactions
                if item["channel"] == "Call"
            )

            emails_count = sum(
                1 for item in interactions
                if item["channel"] == "Email"
            )

            notes_count = sum(
                1 for item in interactions
                if item["channel"] == "Note"
            )

            col1, col2, col3 = st.columns(3)

            col1.metric("Calls", calls_count)
            col2.metric("Emails", emails_count)
            col3.metric("Notes", notes_count)

            st.divider()

            # ADD INTERACTION

            st.subheader("Record an interaction")

            with st.form("interaction_form"):

                channel = st.selectbox(
                    "Interaction type",
                    ["Call", "Email", "Note"]
                )

                direction = st.selectbox(
                    "Direction",
                    ["Outbound", "Inbound", "Internal"]
                )

                event_type = st.selectbox(
                    "Result",
                    [
                        "Completed",
                        "No answer",
                        "Voicemail",
                        "Positive response",
                        "Objection",
                        "Meeting booked",
                        "Information shared",
                        "Other"
                    ]
                )

                subject = st.text_input("Subject")

                content = st.text_area(
                    "Notes / interaction details",
                    placeholder="What happened during this interaction?"
                )

                outcome = st.text_input(
                    "Next step or outcome",
                    placeholder="Example: Call back next Tuesday"
                )

                save_interaction = st.form_submit_button(
                    "Save interaction",
                    width="stretch"
                )

                if save_interaction:

                    if not content.strip() and not subject.strip():
                        st.error("Enter a subject or interaction note.")

                    else:
                        add_interaction(
                            contact_id,
                            channel,
                            direction,
                            event_type,
                            subject,
                            content,
                            outcome
                        )

                        st.success("Interaction saved.")
                        st.rerun()

            st.divider()

            # ACTIVITY TIMELINE

            st.subheader("Activity timeline")

            if interactions:

                for item in interactions:

                    with st.container(border=True):

                        st.markdown(
                            f"**{item['channel']} · {item['event_type']}**"
                        )

                        st.caption(
                            f"{item['occurred_at']} · "
                            f"{item['direction'] or 'Not specified'}"
                        )

                        if item["subject"]:
                            st.write(f"**{item['subject']}**")

                        if item["content"]:
                            st.write(item["content"])

                        if item["outcome"]:
                            st.info(f"Outcome: {item['outcome']}")

            else:
                st.info("No interactions recorded yet.")

            st.divider()

            # NEXT ACTION

            st.subheader("Next actions")

            with st.form("task_form"):

                task_title = st.text_input(
                    "Action",
                    placeholder="Example: Call Thomas back"
                )

                task_description = st.text_area(
                    "Description"
                )

                due_date = st.date_input(
                    "Due date"
                )

                save_task = st.form_submit_button(
                    "Schedule follow-up",
                    width="stretch"
                )

                if save_task:

                    if not task_title.strip():
                        st.error("Enter an action title.")

                    else:
                        create_task(
                            contact_id,
                            task_title,
                            task_description,
                            due_date.isoformat()
                        )

                        st.success("Follow-up scheduled.")
                        st.rerun()

            tasks = get_tasks(contact_id)

            if tasks:

                for task in tasks:

                    with st.container(border=True):

                        st.markdown(f"**{task['title']}**")

                        st.caption(
                            f"Due: {task['due_at']} · "
                            f"Status: {task['status']}"
                        )

                        if task["description"]:
                            st.write(task["description"])

                        if task["status"] == "A faire":

                            if st.button(
                                "Mark as completed",
                                key=f"complete_{task['id']}"
                            ):
                                complete_task(task["id"])
                                st.rerun()

            else:
                st.info("No follow-ups scheduled.")

# ==========================================
# 7. OTHER MODULES
# ==========================================

elif page == "Prospecting Pipeline":
    st.title("Prospecting Pipeline")
    st.info("Pipeline development is coming next.")

elif page == "Activity":
    st.title("Activity Manager")
    st.info("Centralized activity management is coming next.")

elif page == "Objections":
    st.title("Objection Intelligence")
    st.info("Objection analysis is coming next.")

elif page == "AI Copilot":
    st.title("AI Sales Copilot")
    st.info("Your AI assistant is coming next.")

elif page == "Performance":
    st.title("Performance Analytics")
    st.info("Performance analytics are coming next.")
