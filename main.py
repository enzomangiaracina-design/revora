
from datetime import date, datetime

import streamlit as st
import pandas as pd

from database import (
    initialize_database,
    get_all_prospects,
    get_prospect_by_id,
    get_interactions,
    create_task,
    get_tasks,
    complete_task,
    get_verticals,
    count_prospect_activity,
    delete_prospect,
    get_all_interactions,
    get_all_tasks,
    get_activity_summary
)

from core.activity_service import (
    CHANNELS,
    DIRECTIONS,
    RESULTS,
    PERIODS,
    TASK_OPEN,
    log_interaction,
    group_tasks,
    period_bounds,
    count_by_channel,
    format_duration
)

from core.prospect_service import (
    STATUSES,
    CSV_TEMPLATE,
    create_prospect,
    update_prospect,
    filter_prospects,
    read_prospect_csv,
    import_prospects
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
st.sidebar.caption("VERSION 0.5.0")


# ==========================================
# 3 bis. OUTILS D'INTERFACE PARTAGES
# ==========================================

def show_flash_message():
    """Affiche le message laisse par l'action precedente.

    Concept : st.rerun() relance tout le script, ce qui efface un st.success()
    affiche juste avant. On range donc le message dans st.session_state
    (une memoire qui survit aux relances) et on l'affiche au tour suivant.
    """

    message = st.session_state.pop("flash", None)

    if message:
        st.success(message)


def prospect_form(form_key, verticals, submit_label, defaults=None):
    """Formulaire prospect, vide (creation) ou pre-rempli (modification).

    Retourne (bouton_clique, donnees_saisies).
    """

    defaults = defaults or {}

    vertical_options = list(verticals)
    if defaults.get("vertical") and defaults["vertical"] not in vertical_options:
        vertical_options.append(defaults["vertical"])

    status_options = list(STATUSES)
    if defaults.get("status") and defaults["status"] not in status_options:
        status_options.append(defaults["status"])

    with st.form(form_key, clear_on_submit=not defaults):

        col1, col2 = st.columns(2)

        first_name = col1.text_input("First name *", value=defaults.get("first_name") or "")
        last_name = col2.text_input("Last name *", value=defaults.get("last_name") or "")

        company_name = col1.text_input("Company *", value=defaults.get("company_name") or "")
        vertical = col2.selectbox(
            "Vertical",
            vertical_options,
            index=(
                vertical_options.index(defaults["vertical"])
                if defaults.get("vertical") else None
            ),
            accept_new_options=True,
            placeholder="Choose or type a new vertical"
        )

        job_title = col1.text_input("Job title", value=defaults.get("job_title") or "")
        status = col2.selectbox(
            "Status",
            status_options,
            index=status_options.index(defaults.get("status") or "A prospecter")
        )

        email = col1.text_input("Email", value=defaults.get("email") or "")
        phone = col2.text_input("Phone", value=defaults.get("phone") or "")

        source = col1.text_input(
            "Source", value=defaults.get("source") or "",
            placeholder="Example: HubSpot list, trade show, referral"
        )
        owner = col2.text_input("Sales owner", value=defaults.get("owner") or "")

        submitted = st.form_submit_button(submit_label, width="stretch")

    data = {
        "first_name": first_name,
        "last_name": last_name,
        "company_name": company_name,
        "vertical": vertical,
        "job_title": job_title,
        "status": status,
        "email": email,
        "phone": phone,
        "source": source,
        "owner": owner,
    }

    return submitted, data


def interaction_form(form_key, prospect_options=None):
    """Formulaire d'enregistrement d'une interaction.

    prospect_options : {libelle: contact_id}. S'il est fourni, le formulaire
    propose de choisir le prospect (page Activity) ; sinon le prospect est
    deja connu (fiche prospect).

    Retourne (bouton_clique, contact_id ou None, donnees_saisies).
    """

    with st.form(form_key, clear_on_submit=True):

        contact_label = None

        if prospect_options:
            contact_label = st.selectbox("Prospect", list(prospect_options))

        col1, col2, col3 = st.columns(3)

        channel = col1.selectbox("Interaction type", CHANNELS)
        direction = col2.selectbox("Direction", DIRECTIONS)
        event_type = col3.selectbox("Result", RESULTS)

        col1, col2, col3 = st.columns(3)

        day = col1.date_input("Date", value="today", max_value=date.today())
        time = col2.time_input("Time", value="now")
        duration = col3.number_input(
            "Call duration (minutes)", min_value=0.0, step=1.0,
            help="Calls only. Leave 0 if unknown."
        )

        subject = st.text_input("Subject")

        content = st.text_area(
            "Notes / interaction details",
            placeholder="What happened during this interaction?"
        )

        col1, col2 = st.columns(2)

        outcome = col1.text_input(
            "Next step",
            placeholder="Example: Call back next Tuesday"
        )
        follow_up_date = col2.date_input(
            "Follow-up date (optional)", value=None,
            help="Creates a follow-up task with the next step as title."
        )

        submitted = st.form_submit_button("Save interaction", width="stretch")

    data = {
        "channel": channel,
        "direction": direction,
        "event_type": event_type,
        "subject": subject,
        "content": content,
        "outcome": outcome,
        "occurred_at": datetime.combine(day, time),
        "duration_minutes": duration,
        "follow_up_date": follow_up_date,
    }

    contact_id = prospect_options[contact_label] if prospect_options else None

    return submitted, contact_id, data


def follow_up_card(task, show_prospect=True):
    """Affiche une relance avec un bouton pour la marquer comme terminee."""

    with st.container(border=True):

        col_text, col_button = st.columns([4, 1])

        col_text.markdown(f"**{task['title']}**")

        details = [f"Due: {task['due_at'] or 'no date'}"]

        if show_prospect and task.get("first_name"):
            details.insert(0, f"{task['first_name']} {task['last_name']} — {task['company_name']}")

        col_text.caption(" · ".join(details))

        if task.get("description"):
            col_text.write(task["description"])

        if task["status"] == TASK_OPEN:
            if col_button.button("Done", key=f"done_{task['id']}", width="stretch"):
                complete_task(task["id"])
                st.session_state["flash"] = f"Follow-up completed: {task['title']}"
                st.rerun()

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
    st.caption("Create, find, update and import your prospects.")

    show_flash_message()

    verticals = get_verticals()

    # key : Streamlit memorise l'onglet ouvert, qui reste affiche apres
    # une relance du script (ex. apres le depot d'un fichier CSV).
    tab_list, tab_new, tab_import = st.tabs(
        ["Database", "New prospect", "Import CSV"],
        key="prospects_tabs"
    )

    # ---------- RECHERCHE, FILTRES, MODIFICATION, SUPPRESSION ----------

    with tab_list:

        if not prospects:
            st.info("No prospects registered. Create one or import a CSV file.")

        else:
            col_search, col_vertical, col_status, col_source = st.columns([2, 1, 1, 1])

            query = col_search.text_input(
                "Search", placeholder="Name, company, email or phone"
            )
            selected_verticals = col_vertical.multiselect("Vertical", verticals)
            selected_statuses = col_status.multiselect("Status", STATUSES)
            selected_sources = col_source.multiselect(
                "Source", sorted({p["source"] for p in prospects if p["source"]})
            )

            filtered = filter_prospects(
                prospects, query, selected_verticals, selected_statuses, selected_sources
            )

            st.caption(f"{len(filtered)} of {len(prospects)} prospects")

            if filtered:
                df = pd.DataFrame(filtered)
                df["Prospect"] = df["first_name"] + " " + df["last_name"]

                # Compteurs automatiques calcules depuis les interactions et relances
                summary = get_activity_summary()

                for column, key in [
                    ("Calls", "calls"),
                    ("Emails", "emails"),
                    ("Last activity", "last_interaction_at"),
                    ("Next follow-up", "next_task_due"),
                ]:
                    df[column] = df["id"].map(lambda i, k=key: summary.get(i, {}).get(k))

                st.dataframe(
                    df[[
                        "Prospect", "company_name", "vertical", "job_title",
                        "email", "phone", "status", "Calls", "Emails",
                        "Last activity", "Next follow-up", "source", "owner"
                    ]].rename(columns={
                        "company_name": "Company",
                        "vertical": "Vertical",
                        "job_title": "Job title",
                        "email": "Email",
                        "phone": "Phone",
                        "status": "Status",
                        "source": "Source",
                        "owner": "Owner"
                    }),
                    width="stretch",
                    hide_index=True
                )
            else:
                st.info("No prospect matches these filters.")

            st.divider()
            st.subheader("Edit a prospect")

            edit_options = {
                f"{p['first_name']} {p['last_name']} — {p['company_name']}": p["id"]
                for p in prospects
            }

            selected_label = st.selectbox("Prospect to edit", list(edit_options))
            contact_id = edit_options[selected_label]
            prospect = get_prospect_by_id(contact_id)

            # La cle du formulaire inclut l'id : changer de prospect
            # recharge bien les valeurs pre-remplies.
            submitted, data = prospect_form(
                f"edit_form_{contact_id}", verticals, "Save changes", defaults=prospect
            )

            if submitted:
                ok, message = update_prospect(contact_id, data)

                if ok:
                    st.session_state["flash"] = message
                    st.rerun()
                else:
                    st.error(message)

            with st.expander("Delete this prospect"):

                counts = count_prospect_activity(contact_id)

                st.warning(
                    f"This permanently deletes **{selected_label}** together with "
                    f"{counts['interactions']} interaction(s), {counts['tasks']} "
                    f"follow-up(s) and {counts['scores']} score record(s). "
                    "The company is kept. This cannot be undone."
                )

                confirmed = st.checkbox(
                    "I understand and want to delete this prospect permanently",
                    key=f"confirm_delete_{contact_id}"
                )

                if st.button(
                    "Delete prospect",
                    type="primary",
                    disabled=not confirmed,
                    key=f"delete_{contact_id}"
                ):
                    delete_prospect(contact_id)
                    st.session_state["flash"] = f"{selected_label} deleted."
                    st.rerun()

    # ---------- CREATION ----------

    with tab_new:

        submitted, data = prospect_form("create_form", verticals, "Create prospect")

        if submitted:
            ok, message = create_prospect(data)

            if ok:
                st.session_state["flash"] = message
                st.rerun()
            else:
                st.error(message)

    # ---------- IMPORT CSV ----------

    with tab_import:

        st.write(
            "Required columns: **first_name, last_name, company_name**. "
            "Optional: vertical, email, phone, job_title, status, source, owner. "
            "French headers (prénom, nom, entreprise…) and HubSpot export "
            "headers are recognized."
        )

        st.download_button(
            "Download CSV template",
            data=CSV_TEMPLATE,
            file_name="revora_import_template.csv",
            mime="text/csv"
        )

        report = st.session_state.pop("import_report", None)

        if report:
            st.success(f"{report['created']} prospect(s) created.")

            if report["duplicates"]:
                with st.expander(f"{len(report['duplicates'])} duplicate(s) skipped"):
                    st.dataframe(pd.DataFrame(report["duplicates"]), hide_index=True)

            if report["errors"]:
                with st.expander(f"{len(report['errors'])} row(s) rejected"):
                    st.dataframe(pd.DataFrame(report["errors"]), hide_index=True)

        uploaded_file = st.file_uploader("CSV file", type=["csv"])

        if uploaded_file:
            try:
                import_df, ignored_columns = read_prospect_csv(uploaded_file)

            except ValueError as error:
                st.error(str(error))

            else:
                st.caption(f"{len(import_df)} row(s) detected.")

                if ignored_columns:
                    st.caption("Ignored columns: " + ", ".join(map(str, ignored_columns)))

                st.dataframe(import_df.head(20), width="stretch", hide_index=True)

                default_source = st.text_input(
                    "Source for rows without a source", value="Import CSV"
                )

                if st.button("Import prospects", type="primary"):
                    st.session_state["import_report"] = import_prospects(
                        import_df, default_source
                    )
                    st.rerun()

# ==========================================
# 6. PROSPECT DETAILS
# ==========================================

elif page == "Prospect Details":

    st.title("Prospect Details")
    st.caption("Your complete commercial memory.")

    show_flash_message()

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

            # ACTIVITY COUNTERS (calcules automatiquement)

            counts = count_by_channel(interactions)
            summary = get_activity_summary().get(contact_id, {})

            col1, col2, col3, col4 = st.columns(4)

            col1.metric("Calls", counts["Call"])
            col2.metric("Emails", counts["Email"])
            col3.metric("LinkedIn", counts["LinkedIn"])
            col4.metric("Notes", counts["Note"])

            col1, col2 = st.columns(2)

            col1.metric(
                "Last interaction",
                summary.get("last_interaction_at") or "None yet"
            )
            col2.metric(
                "Next action",
                (
                    f"{summary['next_task_due'] or 'no date'} · {summary['next_task_title']}"
                    if summary.get("next_task_title") else "None scheduled"
                )
            )

            st.divider()

            # ADD INTERACTION

            st.subheader("Record an interaction")

            submitted, _, data = interaction_form(f"interaction_form_{contact_id}")

            if submitted:
                ok, message = log_interaction(contact_id, data)

                if ok:
                    st.session_state["flash"] = message
                    st.rerun()
                else:
                    st.error(message)

            st.divider()

            # ACTIVITY TIMELINE

            st.subheader("Activity timeline")

            if interactions:

                for item in interactions:

                    with st.container(border=True):

                        st.markdown(
                            f"**{item['channel']} · {item['event_type']}**"
                        )

                        details = [
                            item["occurred_at_local"],
                            item["direction"] or "Not specified",
                            format_duration(item["metadata"]),
                        ]

                        st.caption(" · ".join(d for d in details if d))

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

                        st.session_state["flash"] = "Follow-up scheduled."
                        st.rerun()

            groups = group_tasks(get_tasks(contact_id))
            open_tasks = groups["overdue"] + groups["today"] + groups["upcoming"] + groups["no_date"]

            if groups["overdue"]:
                st.warning(f"{len(groups['overdue'])} overdue follow-up(s).")

            for task in open_tasks:
                follow_up_card(task, show_prospect=False)

            if not open_tasks:
                st.info("No open follow-ups.")

            if groups["done"]:
                with st.expander(f"Completed follow-ups ({len(groups['done'])})"):
                    for task in groups["done"]:
                        st.caption(f"✓ {task['title']} · due {task['due_at'] or 'no date'}")

# ==========================================
# 7. OTHER MODULES
# ==========================================

elif page == "Prospecting Pipeline":
    st.title("Prospecting Pipeline")
    st.info("Pipeline development is coming next.")

elif page == "Activity":

    st.title("Activity Manager")
    st.caption("Every call, email, LinkedIn message and note — and what to do next.")

    show_flash_message()

    today_start, today_end = period_bounds("Today")
    week_start, week_end = period_bounds("Last 7 days")

    today_counts = count_by_channel(get_all_interactions(start_date=today_start, end_date=today_end))
    week_total = len(get_all_interactions(start_date=week_start, end_date=week_end))
    task_groups = group_tasks(get_all_tasks())

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Calls today", today_counts["Call"])
    col2.metric("Emails today", today_counts["Email"])
    col3.metric("Interactions (7 days)", week_total)
    col4.metric("Due today", len(task_groups["today"]))
    col5.metric("Overdue", len(task_groups["overdue"]))

    tab_timeline, tab_follow_ups, tab_log = st.tabs(
        ["Timeline", "Follow-ups", "Log activity"],
        key="activity_tabs"
    )

    # ---------- TIMELINE GLOBALE ----------

    with tab_timeline:

        col_period, col_channel, col_search = st.columns([1, 2, 2])

        period = col_period.selectbox("Period", PERIODS, index=1)
        selected_channels = col_channel.multiselect("Type", CHANNELS)
        search = col_search.text_input("Prospect or company")

        start, end = period_bounds(period)
        activity = get_all_interactions(selected_channels, start, end)

        if search.strip():
            needle = search.strip().lower()
            activity = [
                item for item in activity
                if needle in f"{item['first_name']} {item['last_name']} {item['company_name'] or ''}".lower()
            ]

        st.caption(f"{len(activity)} interaction(s)")

        if activity:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Date": item["occurred_at_local"],
                        "Prospect": f"{item['first_name']} {item['last_name']}",
                        "Company": item["company_name"],
                        "Type": item["channel"],
                        "Direction": item["direction"],
                        "Result": item["event_type"],
                        "Duration": format_duration(item["metadata"]),
                        "Subject": item["subject"],
                        "Notes": item["content"],
                        "Next step": item["outcome"],
                    }
                    for item in activity
                ]),
                width="stretch",
                hide_index=True
            )
        else:
            st.info("No interaction for these filters.")

    # ---------- RELANCES ----------

    with tab_follow_ups:

        sections = [
            ("overdue", "Overdue"),
            ("today", "Today"),
            ("upcoming", "Upcoming"),
            ("no_date", "No due date"),
        ]

        if not any(task_groups[key] for key, _ in sections):
            st.info("No open follow-ups. Schedule one from a prospect file or when logging an activity.")

        for key, label in sections:
            if task_groups[key]:
                st.subheader(f"{label} ({len(task_groups[key])})")

                for task in task_groups[key]:
                    follow_up_card(task)

        if task_groups["done"]:
            with st.expander(f"Completed ({len(task_groups['done'])})"):
                for task in task_groups["done"]:
                    st.caption(
                        f"✓ {task['title']} · {task['first_name']} {task['last_name']}"
                        f" · due {task['due_at'] or 'no date'}"
                    )

    # ---------- SAISIE RAPIDE ----------

    with tab_log:

        if not prospects:
            st.info("Add a prospect before logging an activity.")

        else:
            options = {
                f"{p['first_name']} {p['last_name']} — {p['company_name']}": p["id"]
                for p in prospects
            }

            submitted, contact_id, data = interaction_form("log_activity_form", options)

            if submitted:
                ok, message = log_interaction(contact_id, data)

                if ok:
                    st.session_state["flash"] = message
                    st.rerun()
                else:
                    st.error(message)

elif page == "Objections":
    st.title("Objection Intelligence")
    st.info("Objection analysis is coming next.")

elif page == "AI Copilot":
    st.title("AI Sales Copilot")
    st.info("Your AI assistant is coming next.")

elif page == "Performance":
    st.title("Performance Analytics")
    st.info("Performance analytics are coming next.")
