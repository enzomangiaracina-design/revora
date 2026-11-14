
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

from database import (
    get_stages,
    get_stage_names,
    add_stage,
    rename_stage,
    move_stage,
    set_stage_closed,
    delete_stage,
    set_prospect_stage
)

from core.pipeline_service import (
    DEFAULT_STALE_DAYS,
    build_board,
    days_since,
    is_stale,
    prioritize
)

from core.prospect_service import (
    CSV_TEMPLATE,
    create_prospect,
    update_prospect,
    filter_prospects,
    read_prospect_csv,
    import_prospects
)

from database import (
    QUALIFICATION_FIELDS,
    update_qualification,
    get_score_history
)

from core.scoring import DEFAULT_CONFIG
from core.score_service import (
    load_config,
    save_config,
    refresh_scores,
    score_changes,
    calibration_by_stage
)

from database import get_integrations, get_sync_logs
from core.sync_service import run_sync, import_hubspot_contacts
from integrations.config import get_secret
from integrations.hubspot.connector import HubSpotConnector
from integrations.gmail.connector import GmailConnector

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

# Etapes du pipeline (personnalisables) : servent aussi de liste de statuts
stage_names = get_stage_names()

# Scores recalcules a chaque affichage (rapide) ; seules les VARIATIONS
# sont ajoutees a l'historique en base.
scores = refresh_scores()

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
        "Performance",
        "Settings"
    ]
)

st.sidebar.divider()
st.sidebar.caption("VERSION 0.8.0")


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

    status_options = list(stage_names)
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
            index=status_options.index(defaults.get("status") or status_options[0])
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


def _move_prospect(contact_id, widget_key):
    """Appele quand l'etape d'une carte change (callback du selectbox).

    Concept : un "callback" est une fonction que Streamlit execute juste
    apres le changement d'un widget, avant de relancer la page. La page
    affiche donc directement le prospect dans sa nouvelle colonne.
    """

    ok, message = set_prospect_stage(contact_id, st.session_state[widget_key])
    st.session_state["flash"] = message if ok else f"Error: {message}"


TEMPERATURE_COLORS = {"Hot": "red", "Warm": "orange", "Cold": "blue"}


def score_label(result):
    """Libelle colore du score, ex. ":red[72 · Hot]" (syntaxe de couleur Streamlit)."""

    if not result:
        return "No score"

    color = TEMPERATURE_COLORS[result["temperature"]]

    return f":{color}[{result['global']} · {result['temperature']}]"


def pipeline_card(prospect, summary, stale_days):
    """Carte d'un prospect dans le tableau Kanban."""

    with st.container(border=True):

        st.markdown(f"**{prospect['first_name']} {prospect['last_name']}**")
        st.caption(f"{prospect['company_name']} · {prospect['vertical'] or '—'}")
        st.caption(score_label(scores.get(prospect["id"])))

        if summary.get("next_task_title"):
            due = summary["next_task_due"] or ""
            text = f"→ {due or 'no date'} · {summary['next_task_title']}"

            if due and due[:10] < date.today().isoformat():
                st.caption(f":red[Overdue {text}]")
            else:
                st.caption(text)

        days = days_since(summary.get("last_interaction_at"))

        if days is None:
            st.caption(":orange[Never contacted]")
        elif days >= stale_days:
            st.caption(f":orange[No activity for {days} days]")
        else:
            st.caption(f"Last activity: {days} day(s) ago")

        key = f"stage_of_{prospect['id']}"

        st.selectbox(
            "Stage",
            stage_names,
            index=stage_names.index(prospect["status"]) if prospect["status"] in stage_names else 0,
            key=key,
            label_visibility="collapsed",
            on_change=_move_prospect,
            args=(prospect["id"], key)
        )


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

    col1, col2, col3, col4, col5 = st.columns(5)

    col1.metric("Total prospects", len(prospects))
    col2.metric("Interactions", interactions_count)
    col3.metric("Open follow-ups", tasks_count)
    col4.metric("Companies", len(set(
        p["company_name"] for p in prospects
        if p["company_name"]
    )))
    col5.metric("Hot prospects", sum(
        1 for result in scores.values() if result["temperature"] == "Hot"
    ))

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
            col_search, col_vertical, col_status, col_source, col_owner = st.columns(
                [2, 1, 1, 1, 1]
            )

            query = col_search.text_input(
                "Search", placeholder="Name, company, email or phone"
            )
            selected_verticals = col_vertical.multiselect("Vertical", verticals)
            selected_statuses = col_status.multiselect("Status", stage_names)
            selected_sources = col_source.multiselect(
                "Source", sorted({p["source"] for p in prospects if p["source"]})
            )
            selected_owners = col_owner.multiselect(
                "Sales owner", sorted({p["owner"] for p in prospects if p["owner"]})
            )

            filtered = filter_prospects(
                prospects, query, selected_verticals, selected_statuses,
                selected_sources, selected_owners
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

                df["Score"] = df["id"].map(lambda i: scores[i]["global"] if i in scores else None)
                df["Temperature"] = df["id"].map(lambda i: scores[i]["temperature"] if i in scores else None)

                st.dataframe(
                    df[[
                        "Prospect", "company_name", "vertical", "job_title",
                        "Score", "Temperature",
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

            # SCORE

            st.subheader("Score")

            result = scores.get(contact_id)

            if result:

                col1, col2, col3, col4 = st.columns(4)

                col1.metric("Global score", result["global"])
                col2.metric("Fit", result["fit"] if result["fit"] is not None else "n/a")
                col3.metric("Engagement", result["engagement"])
                col4.metric("Intent", result["intent"])

                st.markdown(score_label(result))

                with st.expander("Why this score?"):

                    st.caption(
                        "Observed = seen in recorded interactions · Confirmed = entered by you · "
                        "Rule = scoring rule applied. Nothing is inferred by AI."
                    )

                    st.dataframe(
                        pd.DataFrame([
                            {
                                "Dimension": item["dimension"].capitalize(),
                                "Signal": item["signal"],
                                "Points": item["points"],
                                "Type": item["type"].capitalize(),
                            }
                            for item in result["explanation"]
                        ]),
                        width="stretch",
                        hide_index=True
                    )

                history = score_changes(get_score_history(contact_id))

                with st.expander(f"Score history ({len(history)} change(s))"):

                    if len(history) > 1:
                        st.line_chart(
                            pd.DataFrame([
                                {
                                    "Date": row["calculated_at_local"],
                                    "Global": row["global_score"],
                                    "Engagement": row["engagement_score"],
                                    "Intent": row["intent_score"],
                                }
                                for row in history
                            ]).set_index("Date")
                        )

                    st.dataframe(
                        pd.DataFrame([
                            {
                                "Date": row["calculated_at_local"],
                                "Global": row["global_score"],
                                "Change": row["delta"],
                                "Fit": row["fit_score"],
                                "Engagement": row["engagement_score"],
                                "Intent": row["intent_score"],
                            }
                            for row in reversed(history)
                        ]),
                        width="stretch",
                        hide_index=True
                    )

            # QUALIFICATION (informations confirmees par le commercial)

            with st.form(f"qualification_form_{contact_id}"):

                st.markdown("**Qualification**")
                st.caption(
                    "Tick only what the prospect has explicitly confirmed. "
                    "These facts feed the Intent score."
                )

                labels = {
                    "need_identified": "Need identified",
                    "is_decision_maker": "Decision maker",
                    "budget_confirmed": "Budget confirmed",
                    "demo_requested": "Demo requested",
                }

                values = {}

                for column, field in zip(st.columns(len(QUALIFICATION_FIELDS)), QUALIFICATION_FIELDS):
                    values[field] = column.checkbox(labels[field], value=bool(prospect.get(field)))

                if st.form_submit_button("Save qualification", width="stretch"):
                    update_qualification(contact_id, values)
                    st.session_state["flash"] = "Qualification saved. Score updated."
                    st.rerun()

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
    st.caption("Where every prospect stands — and who needs your attention.")

    show_flash_message()

    stages = get_stages()
    summaries = get_activity_summary()

    # ---------- FILTRES (communs au tableau et aux priorites) ----------

    col_search, col_vertical, col_owner, col_days, col_toggles = st.columns([2, 1, 1, 1, 1])

    query = col_search.text_input(
        "Search", placeholder="Name, company, email or phone", key="pipeline_search"
    )
    selected_verticals = col_vertical.multiselect(
        "Vertical", get_verticals(), key="pipeline_verticals"
    )
    selected_owners = col_owner.multiselect(
        "Sales owner",
        sorted({p["owner"] for p in prospects if p["owner"]}),
        key="pipeline_owners"
    )
    stale_days = col_days.number_input(
        "Inactive after (days)", min_value=1, value=DEFAULT_STALE_DAYS, key="stale_days"
    )
    only_stale = col_toggles.toggle("Only inactive", key="pipeline_only_stale")
    show_closed = col_toggles.toggle("Show closed stages", key="pipeline_show_closed")

    col_score, col_temperature, _ = st.columns([2, 2, 2])

    min_score = col_score.slider("Minimum score", 0, 100, 0, key="pipeline_min_score")
    selected_temperatures = col_temperature.multiselect(
        "Temperature", ["Hot", "Warm", "Cold"], key="pipeline_temperatures"
    )

    filtered = filter_prospects(
        prospects, query, selected_verticals, None, None, selected_owners
    )

    if only_stale:
        filtered = [
            p for p in filtered if is_stale(summaries.get(p["id"]), stale_days)
        ]

    filtered = [
        p for p in filtered
        if scores[p["id"]]["global"] >= min_score
        and (not selected_temperatures or scores[p["id"]]["temperature"] in selected_temperatures)
    ]

    tab_board, tab_priorities, tab_stages = st.tabs(
        ["Board", "Priorities", "Stages"], key="pipeline_tabs"
    )

    # ---------- TABLEAU KANBAN ----------

    with tab_board:

        visible_stages = [s for s in stages if show_closed or not s["is_closed"]]
        board = build_board(filtered, stages)

        hidden = sum(len(board[s["name"]]) for s in stages if s not in visible_stages)

        st.caption(
            f"{len(filtered)} prospect(s)"
            + (f" · {hidden} in closed stages (hidden)" if hidden else "")
        )

        MAX_CARDS = 50

        for column, stage in zip(st.columns(len(visible_stages)), visible_stages):

            cards = board[stage["name"]]

            with column:
                st.markdown(f"**{stage['name']}**")
                st.caption(f"{len(cards)} prospect(s)" + (" · closed" if stage["is_closed"] else ""))

                for prospect in cards[:MAX_CARDS]:
                    pipeline_card(prospect, summaries.get(prospect["id"], {}), stale_days)

                if len(cards) > MAX_CARDS:
                    st.caption(f"+ {len(cards) - MAX_CARDS} more — narrow the filters.")

    # ---------- VUE PRIORISEE ----------

    with tab_priorities:

        st.caption(
            "Urgency rules: overdue follow-up +3, follow-up due today +2, "
            "never contacted +1, inactive +1. Closed stages are excluded. "
            "Ties go to the highest score, then to the most advanced stage."
        )

        ranked = prioritize(
            filtered, stages, summaries, stale_days,
            scores={pid: result["global"] for pid, result in scores.items()}
        )

        if ranked:
            st.dataframe(
                pd.DataFrame([
                    {
                        "Priority": item["points"],
                        "Score": scores[item["prospect"]["id"]]["global"],
                        "Temperature": scores[item["prospect"]["id"]]["temperature"],
                        "Prospect": f"{item['prospect']['first_name']} {item['prospect']['last_name']}",
                        "Company": item["prospect"]["company_name"],
                        "Stage": item["prospect"]["status"],
                        "Why": " · ".join(item["reasons"]),
                        "Next follow-up": item["summary"].get("next_task_due"),
                        "Last activity": item["summary"].get("last_interaction_at"),
                    }
                    for item in ranked
                ]),
                width="stretch",
                hide_index=True
            )
        else:
            st.success("Nothing urgent: no overdue follow-up and no inactive prospect.")

    # ---------- GESTION DES ETAPES ----------

    with tab_stages:

        st.caption(
            "Renaming a stage also updates every prospect in it. "
            "A closed stage means the prospect is no longer worked "
            "(hidden from the board by default, excluded from priorities)."
        )

        counts = {s["name"]: 0 for s in stages}
        for p in prospects:
            counts[p["status"]] = counts.get(p["status"], 0) + 1

        for index, stage in enumerate(stages):

            with st.container(border=True):

                c_name, c_count, c_closed, c_up, c_down, c_actions = st.columns(
                    [3, 1.2, 1, 0.6, 0.6, 1.4], vertical_alignment="center"
                )

                new_name = c_name.text_input(
                    "Stage name", value=stage["name"],
                    key=f"stage_name_{stage['id']}", label_visibility="collapsed"
                )

                c_count.caption(f"{counts.get(stage['name'], 0)} prospect(s)")

                closed = c_closed.checkbox(
                    "Closed", value=stage["is_closed"], key=f"stage_closed_{stage['id']}"
                )

                if closed != stage["is_closed"]:
                    set_stage_closed(stage["id"], closed)
                    st.rerun()

                if c_up.button("▲", key=f"stage_up_{stage['id']}", disabled=index == 0):
                    move_stage(stage["id"], -1)
                    st.rerun()

                if c_down.button("▼", key=f"stage_down_{stage['id']}", disabled=index == len(stages) - 1):
                    move_stage(stage["id"], 1)
                    st.rerun()

                if new_name.strip() != stage["name"]:
                    if c_actions.button("Rename", key=f"stage_rename_{stage['id']}", type="primary"):
                        ok, message = rename_stage(stage["id"], new_name)

                        if ok:
                            st.session_state["flash"] = message
                            st.rerun()
                        else:
                            st.error(message)

                with c_actions.popover("Delete"):

                    others = [s["name"] for s in stages if s["id"] != stage["id"]]
                    target = None

                    if counts.get(stage["name"]):
                        target = st.selectbox(
                            f"Move its {counts[stage['name']]} prospect(s) to",
                            others, key=f"stage_target_{stage['id']}"
                        )

                    if st.button("Delete stage", key=f"stage_delete_{stage['id']}", type="primary"):
                        ok, message = delete_stage(stage["id"], move_to=target)

                        if ok:
                            st.session_state["flash"] = message
                            st.rerun()
                        else:
                            st.error(message)

        with st.form("add_stage_form", clear_on_submit=True):

            col_name, col_closed, col_button = st.columns([3, 1, 1], vertical_alignment="bottom")

            stage_name = col_name.text_input("New stage")
            stage_closed = col_closed.checkbox("Closed stage")

            if col_button.form_submit_button("Add stage", width="stretch"):
                ok, message = add_stage(stage_name, stage_closed)

                if ok:
                    st.session_state["flash"] = message
                    st.rerun()
                else:
                    st.error(message)

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

# ==========================================
# 8. SETTINGS
# ==========================================

elif page == "Settings":

    st.title("Settings")
    st.caption("Scoring configuration. All values are provisional and should be calibrated.")

    show_flash_message()

    config = load_config()

    with st.form("scoring_settings_form"):

        st.subheader("Target profile (Fit score)")
        st.caption(
            "Leave a criterion empty to ignore it. With no criterion, Fit is not evaluated "
            "and the global score uses Engagement and Intent only."
        )

        col1, col2 = st.columns(2)

        target_verticals = col1.multiselect(
            "Target verticals",
            sorted(set(get_verticals()) | set(config["icp"]["verticals"])),
            default=config["icp"]["verticals"],
            accept_new_options=True
        )
        title_keywords = col2.text_input(
            "Target job title keywords (comma separated)",
            value=", ".join(config["icp"]["title_keywords"]),
            placeholder="Example: sales, ceo, head, vp"
        )

        st.subheader("Weights (%)")

        col1, col2, col3 = st.columns(3)

        weight_fit = col1.number_input("Fit", 0, 100, round(config["weights"]["fit"] * 100))
        weight_engagement = col2.number_input(
            "Engagement", 0, 100, round(config["weights"]["engagement"] * 100)
        )
        weight_intent = col3.number_input("Intent", 0, 100, round(config["weights"]["intent"] * 100))

        st.subheader("Thresholds and freshness")

        col1, col2, col3 = st.columns(3)

        hot = col1.number_input("Hot from", 1, 100, config["thresholds"]["hot"])
        warm = col2.number_input("Warm from", 1, 100, config["thresholds"]["warm"])
        half_life = col3.number_input(
            "Signal half-life (days)", 1, 365, config["half_life_days"],
            help="A signal this old counts for half its points; twice as old, a quarter."
        )

        col_save, col_reset = st.columns(2)

        submitted = col_save.form_submit_button("Save and recompute", type="primary", width="stretch")
        reset = col_reset.form_submit_button("Restore defaults", width="stretch")

    if submitted or reset:

        if reset:
            new_config = DEFAULT_CONFIG
        else:
            new_config = {
                "icp": {
                    "verticals": target_verticals,
                    "title_keywords": [k.strip() for k in title_keywords.split(",") if k.strip()],
                },
                "weights": {
                    "fit": weight_fit / 100,
                    "engagement": weight_engagement / 100,
                    "intent": weight_intent / 100,
                },
                "thresholds": {"hot": hot, "warm": warm},
                "half_life_days": half_life,
            }

        ok, message = save_config(new_config)

        if ok:
            st.session_state["flash"] = message
            st.rerun()
        else:
            st.error(message)

    st.divider()

    st.subheader("Calibration")
    st.caption(
        "Average score per pipeline stage. Advanced stages (meetings…) should score higher "
        "than early ones; if not, adjust the target profile or the weights. "
        "Reliable calibration needs real conversions over time."
    )

    st.dataframe(
        pd.DataFrame(calibration_by_stage(prospects, scores, get_stages())),
        width="stretch",
        hide_index=True
    )

    with st.expander("Scoring rules (points)"):
        st.markdown(
            "- **Engagement** (observed, decayed by freshness, capped per type): "
            "email reply 20 (max 40), inbound call 25 (max 50), LinkedIn reply 15 (max 30), "
            "phone conversation 15 (max 45), positive response +20 (max 40). "
            "Outbound attempts without reaction: 0 by design.\n"
            "- **Intent**: need identified 25, decision maker 15, budget confirmed 30, "
            "demo requested 30 (confirmed by you), meeting booked 35 (observed, decayed). "
            "Closed stage: 0.\n"
            "- **Fit**: target vertical 50, target job title 50 (only configured criteria count)."
        )

    # ---------- INTEGRATIONS ----------

    st.divider()
    st.subheader("Integrations")
    st.caption(
        "Nothing is connected by default. Use TEST accounts only, and set the access tokens "
        "in the .env file (never in the code). Buttons stay disabled until a token is detected. "
        "See docs/INTEGRATIONS.md."
    )

    integration_states = get_integrations()

    for provider, label, secret, connector_class in [
        ("hubspot", "HubSpot", "HUBSPOT_ACCESS_TOKEN", HubSpotConnector),
        ("gmail", "Gmail", "GMAIL_ACCESS_TOKEN", GmailConnector),
    ]:
        state = integration_states.get(provider, {})
        has_token = get_secret(secret) is not None

        with st.container(border=True):

            col_name, col_state, col_actions = st.columns([1.5, 2.5, 2], vertical_alignment="center")

            col_name.markdown(f"**{label}**")
            col_name.caption(state.get("status") or "Not connected")

            col_state.caption(f"Token ({secret}): {'detected' if has_token else 'not set'}")
            col_state.caption(f"Last sync: {state.get('last_sync_at') or 'never'}")

            if state.get("last_error"):
                col_state.caption(f":red[{state['last_error']}]")

            if col_actions.button(
                "Sync now", key=f"sync_{provider}", disabled=not has_token, width="stretch"
            ):
                result = run_sync(connector_class())
                st.session_state["flash"] = (
                    f"{label}: {result['status']} — {result['created']} created, "
                    f"{result['duplicates']} duplicate(s), {result['unmatched']} unmatched"
                    + (f" — {result['message']}" if result.get("message") else "")
                )
                st.rerun()

            if provider == "hubspot" and col_actions.button(
                "Import contacts", key="import_hubspot", disabled=not has_token, width="stretch"
            ):
                try:
                    report = import_hubspot_contacts(HubSpotConnector())
                    st.session_state["flash"] = (
                        f"HubSpot contacts: {report['created']} created, {report['linked']} linked, "
                        f"{report['already_linked']} already linked, {len(report['errors'])} rejected"
                    )
                except Exception as error:  # message affiché, jamais de plantage de la page
                    st.session_state["flash"] = f"HubSpot import failed: {error}"
                st.rerun()

    logs = get_sync_logs()

    if logs:
        with st.expander(f"Sync log ({len(logs)})"):
            st.dataframe(
                pd.DataFrame([
                    {
                        "Date": log["started_at_local"],
                        "Provider": log["provider"],
                        "Status": log["status"],
                        "Fetched": log["fetched"],
                        "Created": log["created"],
                        "Duplicates": log["duplicates"],
                        "Unmatched": log["unmatched"],
                        "Errors": log["errors"],
                        "Message": log["message"],
                    }
                    for log in logs
                ]),
                width="stretch",
                hide_index=True
            )
