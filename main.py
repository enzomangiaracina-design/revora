
from datetime import date, datetime, timedelta

import streamlit as st
import pandas as pd

from ui import theme

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
    prioritize,
    SORT_OPTIONS,
    CREATED_FILTERS,
    ACTIVITY_FILTERS,
    FOLLOW_UP_FILTERS,
    filter_quick,
    sort_prospects,
    build_card
)

from ui.kanban import pipeline_board, event_value

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

from database import (
    get_objections,
    set_objection_status,
    delete_objection,
    get_objection_responses,
    set_objection_response
)
from core.objection_service import (
    STATUSES as OBJECTION_STATUSES,
    PLAYBOOK_PLACEHOLDER,
    categories as objection_categories,
    record_objection,
    count_by,
    filter_period,
    weekly_trend,
    resolution_by_category,
    anonymized_examples,
    call_preparation,
    format_day
)

from core.performance_service import (
    PERIODS as PERFORMANCE_PERIODS,
    period_range,
    previous_range,
    compute_kpis,
    delta,
    daily_activity,
    by_vertical
)

from database import get_recent_score_changes
from core.overview_service import (
    greeting,
    long_date,
    focus_rows,
    build_feed,
    format_when
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
    page_title="REVORA | Sales Execution Platform",
    page_icon=str(theme.FAVICON),
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

# Couleurs, police et rayons : .streamlit/config.toml
# Logo, cartes KPI et navigation : ui/theme.py
theme.apply_theme()

# ==========================================
# 3. NAVIGATION
# ==========================================

page = st.sidebar.radio(
    "Navigation",
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
    ],
    format_func=theme.nav_label,
    label_visibility="collapsed",
    key="nav_page"
)

st.sidebar.divider()
st.sidebar.caption("VERSION 0.14.0")


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


def reset_form(form_key):
    """Vide un formulaire prospect APRES une creation reussie.

    Concept : Streamlit garde les valeurs d'un formulaire tant que son nom
    (key) ne change pas. En ajoutant un numero de version au nom, on obtient
    un formulaire neuf et vide. En cas d'erreur, on ne l'appelle pas : les
    valeurs saisies restent la pour etre corrigees.
    """

    version_key = f"_form_version_{form_key}"
    st.session_state[version_key] = st.session_state.get(version_key, 0) + 1


def prospect_form(form_key, verticals, submit_label, defaults=None):
    """Formulaire prospect, vide (creation) ou pre-rempli (modification).

    Les champs sont poses ligne par ligne (une paire de colonnes par ligne)
    pour que la touche Tab suive l'ordre de lecture : Prenom -> Nom ->
    Entreprise -> Verticale...

    Retourne (bouton_clique, donnees_saisies).
    """

    defaults = defaults or {}

    vertical_options = list(verticals)
    if defaults.get("vertical") and defaults["vertical"] not in vertical_options:
        vertical_options.append(defaults["vertical"])

    status_options = list(stage_names)
    if defaults.get("status") and defaults["status"] not in status_options:
        status_options.append(defaults["status"])

    version = st.session_state.get(f"_form_version_{form_key}", 0)

    # clear_on_submit=False : une erreur de validation ne doit pas effacer la saisie
    with st.form(f"{form_key}_{version}", clear_on_submit=False):

        col1, col2 = st.columns(2)

        first_name = col1.text_input("First name *", value=defaults.get("first_name") or "")
        last_name = col2.text_input("Last name *", value=defaults.get("last_name") or "")

        col1, col2 = st.columns(2)

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

        col1, col2 = st.columns(2)

        job_title = col1.text_input("Job title", value=defaults.get("job_title") or "")
        status = col2.selectbox(
            "Status",
            status_options,
            index=status_options.index(defaults.get("status") or status_options[0])
        )

        col1, col2 = st.columns(2)

        email = col1.text_input("Email", value=defaults.get("email") or "")
        phone = col2.text_input("Phone", value=defaults.get("phone") or "")

        col1, col2 = st.columns(2)

        source = col1.text_input(
            "Source", value=defaults.get("source") or "",
            placeholder="Example: HubSpot list, trade show, referral"
        )
        owner = col2.text_input("Sales owner", value=defaults.get("owner") or "")

        linkedin_url = st.text_input(
            "LinkedIn profile URL", value=defaults.get("linkedin_url") or "",
            placeholder="https://www.linkedin.com/in/…  (copied by you — REVORA never visits LinkedIn)"
        )

        submitted = st.form_submit_button(submit_label, width="stretch")

    data = {
        "linkedin_url": linkedin_url,
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
        event_type = col3.selectbox(
            "Result", RESULTS,
            help="LinkedIn actions (connection request, accepted, InMail) require the LinkedIn type; "
                 "their direction is set automatically.",
        )

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

        col1, col2 = st.columns(2)

        objection_category = col1.selectbox(
            "Objection raised (optional)",
            objection_categories(get_objections()),
            index=None,
            accept_new_options=True,
            placeholder="None — only if the prospect actually said it",
        )
        objection_verbatim = col2.text_input(
            "Objection wording (optional)",
            placeholder="What the prospect said, in their words",
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
        "objection_category": objection_category,
        "objection_verbatim": objection_verbatim,
    }

    contact_id = prospect_options[contact_label] if prospect_options else None

    return submitted, contact_id, data


BOARD_KEY = "pipeline_board"


def prospect_label(prospect):
    """Libelle d'un prospect dans les listes de choix (doit rester identique partout)."""

    return f"{prospect['first_name']} {prospect['last_name']} — {prospect['company_name']}"


def open_prospect(contact_id):
    """Ouvre la fiche d'un prospect (a appeler depuis un callback).

    Concept : un "callback" s'execute AVANT que la page soit redessinee.
    C'est le seul moment ou l'on peut changer la valeur d'un widget deja
    affiche (ici la navigation et le choix du prospect).
    """

    prospect = get_prospect_by_id(contact_id)

    if prospect:
        st.session_state["nav_page"] = "Prospect Details"
        st.session_state["details_prospect"] = prospect_label(prospect)


def _on_board_move():
    """Glisser-deposer d'une carte : enregistre la nouvelle etape."""

    move = event_value(BOARD_KEY, "move")

    if move:
        ok, message = set_prospect_stage(int(move["id"]), move["stage"])
        st.session_state["flash"] = message if ok else f"Error: {message}"


def _on_board_open():
    """Clic sur une carte : ouvre la fiche du prospect."""

    target = event_value(BOARD_KEY, "open")

    if target:
        open_prospect(int(target["id"]))


def go_to(page_name, **state):
    """Change de page depuis un bouton (callback), en reglant d'autres widgets si besoin."""

    st.session_state["nav_page"] = page_name

    for key, value in state.items():
        st.session_state[key] = value


@st.dialog("Add prospect", width="large")
def add_prospect_dialog():
    """Fenetre d'ajout rapide : reutilise le formulaire et les controles existants."""

    submitted, data = prospect_form("overview_create_form", get_verticals(), "Create prospect")

    if submitted:
        ok, message = create_prospect(data)

        if ok:
            reset_form("overview_create_form")
            st.session_state["flash"] = message
            st.rerun()
        else:
            st.error(message)


PRIORITY_BADGES = {"High": ":red-badge[High]", "Medium": ":orange-badge[Medium]", "Low": ":gray-badge[Low]"}

FEED_ICONS = {
    "Call": ":material/call:",
    "Email": ":material/mail:",
    "LinkedIn": ":material/work:",
    "Note": ":material/sticky_note_2:",
    "Objection": ":material/forum:",
    "Prospect": ":material/person_add:",
    "Score": ":material/trending_up:",
}


TEMPERATURE_COLORS = {"Hot": "red", "Warm": "orange", "Cold": "blue"}


def score_label(result):
    """Libelle colore du score, ex. ":red[72 · Hot]" (syntaxe de couleur Streamlit)."""

    if not result:
        return "No score"

    color = TEMPERATURE_COLORS[result["temperature"]]

    return f":{color}[{result['global']} · {result['temperature']}]"


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

    today = date.today()
    stages = get_stages()
    summaries = get_activity_summary()
    all_interactions = get_all_interactions()
    all_objections = get_objections()

    # ---------- 1. EN-TETE : ou suis-je ? ----------

    col_hello, col_search, col_add = st.columns([2, 3, 1.2], vertical_alignment="center")

    col_hello.markdown(f"### {greeting()}")
    col_hello.caption(long_date(today))

    search = col_search.text_input(
        "Search", placeholder="Search a prospect: name, company, email or phone",
        key="overview_search", label_visibility="collapsed",
    )

    if col_add.button("Add prospect", type="primary", icon=":material/person_add:", width="stretch"):
        add_prospect_dialog()

    show_flash_message()

    if search.strip():
        results = filter_prospects(prospects, search)[:5]

        with st.container(border=True):
            if not results:
                st.caption("No prospect matches this search.")

            for p in results:
                col_name, col_meta, col_open = st.columns([3, 4, 1], vertical_alignment="center")
                col_name.markdown(f"**{p['first_name']} {p['last_name']}**")
                col_meta.caption(f"{p['company_name']} · {p['status']} · {p['email'] or 'no email'}")
                col_open.button("Open", key=f"search_open_{p['id']}", on_click=open_prospect,
                                args=(p["id"],), width="stretch")

    if not prospects:
        st.info("Your prospect database is empty. Add a first prospect or import a CSV file.")
        st.button("Import a CSV file", icon=":material/upload_file:",
                  on_click=go_to, args=("Prospects",), kwargs={"prospects_tabs": "Import CSV"})

    # ---------- 2. INDICATEURS DU JOUR ----------

    today_kpis = compute_kpis(all_interactions, all_objections, today, today)
    yesterday = today - timedelta(days=1)
    yesterday_kpis = compute_kpis(all_interactions, all_objections, yesterday, yesterday)

    task_groups = group_tasks(get_all_tasks(), today)
    stale_days = st.session_state.get("stale_days", DEFAULT_STALE_DAYS)
    ranked = prioritize(
        prospects, stages, summaries, stale_days,
        scores={pid: result["global"] for pid, result in scores.items()},
    )

    def vs_yesterday(key):
        change = delta(today_kpis[key], yesterday_kpis[key])
        return f"{change:+g} vs yesterday" if change else None

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Calls today", today_kpis["calls"], delta=vs_yesterday("calls"))
    col2.metric("Emails sent today", today_kpis["emails_sent"], delta=vs_yesterday("emails_sent"))
    overdue_count = len(task_groups["overdue"])

    col3.metric(
        "Follow-ups due",
        len(task_groups["today"]) + overdue_count,
        delta=f"{overdue_count} overdue" if overdue_count else None,
        delta_color="inverse",   # du retard s'affiche en rouge
        delta_arrow="off",
        help="Follow-ups due today plus overdue ones.",
    )
    col4.metric(
        "Priority prospects", len(ranked),
        help="Prospects in open stages with an overdue or due follow-up, never contacted, "
             f"or without activity for {stale_days} days.",
    )

    col_main, col_side = st.columns([2, 1], gap="large")

    # ---------- 3. TODAY'S FOCUS : qui, quoi, pourquoi ----------

    with col_main:

        theme.section_title("Today's focus")

        rows = focus_rows(ranked, scores, limit=8, today=today)

        if not rows:
            with st.container(border=True):
                st.markdown("**Nothing urgent today.**")
                st.caption("No overdue follow-up, no prospect left without contact. "
                           "Use the pipeline to move prospects forward.")
                st.button("Open the pipeline", on_click=go_to, args=("Prospecting Pipeline",))

        for row in rows:
            with st.container(border=True):

                col_who, col_last, col_action, col_open = st.columns(
                    [3, 1.3, 3.4, 0.5], vertical_alignment="center"
                )

                col_who.markdown(f"{PRIORITY_BADGES[row['priority']]} **{row['prospect']}**")
                col_who.caption(
                    f"{row['company']} · {row['stage']}"
                    + (f" · score {row['score']}" if row["score"] is not None else "")
                )

                col_last.caption("Last touch")
                col_last.markdown(row["last_interaction"])

                col_action.markdown(f"**{row['next_action']}**")
                col_action.caption(f"Why: {row['reason']}")

                col_open.button(
                    "", icon=":material/open_in_new:", key=f"focus_open_{row['id']}",
                    on_click=open_prospect, args=(row["id"],),
                    help=f"Open {row['prospect']}'s prospect file",
                )

        if len(ranked) > len(rows):
            st.button(
                f"See all {len(ranked)} priorities in the pipeline", type="tertiary",
                icon=":material/arrow_forward:", on_click=go_to,
                args=("Prospecting Pipeline",), kwargs={"pipeline_view": "Priorities"},
            )

    # ---------- 4. RECENT ACTIVITY ----------

    with col_side:

        theme.section_title("Recent activity")

        feed = build_feed(
            all_interactions, all_objections, prospects, get_recent_score_changes(), limit=8
        )

        with st.container(border=True):

            if not feed:
                st.caption("No activity recorded yet.")
                st.button("Log a first call or email", on_click=go_to,
                          args=("Activity",), kwargs={"activity_tabs": "Log activity"})

            for index, event in enumerate(feed):
                # Une ligne compacte : icone, evenement et heure ; le prospect en lien dessous
                st.markdown(
                    f"{FEED_ICONS.get(event['kind'], ':material/history:')} "
                    f"**{event['title']}** · :gray[{format_when(event['at'], today) or ''}]"
                )
                st.button(
                    f"{event['prospect']}" + (f" · {event['company']}" if event["company"] else ""),
                    key=f"feed_open_{index}_{event['contact_id']}", type="tertiary",
                    on_click=open_prospect, args=(event["contact_id"],),
                )

        # ---------- 5. PERFORMANCE SNAPSHOT ----------

        theme.section_title("Last 7 days")

        week_start, week_end = period_range(7, today)
        previous_start, previous_end = previous_range(week_start, week_end)
        week = compute_kpis(all_interactions, all_objections, week_start, week_end)
        previous_week = compute_kpis(all_interactions, all_objections, previous_start, previous_end)

        def snapshot_line(label, key, unit=""):
            """Une ligne compacte : valeur, libellé, écart avec les 7 jours précédents."""

            value = week[key]
            change = delta(value, previous_week[key])
            shown = "—" if value is None else f"{value}{unit}"
            suffix = " pts" if unit else ""

            if change:
                color = "green" if change > 0 else "red"
                trend_text = f" · :{color}[{change:+g}{suffix}]"
            else:
                trend_text = ""

            return f"**{shown}** {label}{trend_text}"

        with st.container(border=True):
            st.markdown(
                "  \n".join([
                    snapshot_line("connection rate", "connection_rate", " %"),
                    snapshot_line("reply rate", "reply_rate", " %"),
                    snapshot_line("meetings booked", "meetings"),
                ])
            )
            st.caption("Compared with the previous 7 days.")

        trend = daily_activity(all_interactions, today - timedelta(days=13), today)

        if any(day["Calls"] or day["Emails sent"] for day in trend):
            st.caption("Calls + emails sent per day (14 days)")
            st.line_chart(
                pd.DataFrame(
                    [{"Day": d["Day"][5:], "Touches": d["Calls"] + d["Emails sent"]} for d in trend]
                ).set_index("Day"),
                height=140,
            )

        st.button("Full performance", type="tertiary", icon=":material/arrow_forward:",
                  on_click=go_to, args=("Performance",))

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
    # on_change="rerun" : permet aussi d'ouvrir un onglet depuis une autre page
    # (ex. bouton « Import a CSV file » de l'Overview) via st.session_state.
    tab_list, tab_new, tab_import = st.tabs(
        ["Database", "New prospect", "Import CSV"],
        key="prospects_tabs",
        on_change="rerun"
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
                        "Last activity", "Next follow-up", "source", "owner", "linkedin_url"
                    ]].rename(columns={
                        "company_name": "Company",
                        "vertical": "Vertical",
                        "job_title": "Job title",
                        "email": "Email",
                        "phone": "Phone",
                        "status": "Status",
                        "source": "Source",
                        "owner": "Owner",
                        "linkedin_url": "LinkedIn"
                    }),
                    column_config={
                        "LinkedIn": st.column_config.LinkColumn("LinkedIn", display_text="Profile"),
                    },
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
                    f"follow-up(s), {counts['objections']} objection(s) and "
                    f"{counts['scores']} score record(s). "
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
                reset_form("create_form")
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

        prospect_options = {prospect_label(p): p["id"] for p in prospects}

        # Prospect choisi depuis le pipeline mais supprime entre-temps : on l'oublie
        if st.session_state.get("details_prospect") not in prospect_options:
            st.session_state.pop("details_prospect", None)

        selected_name = st.selectbox(
            "Select a prospect",
            list(prospect_options.keys()),
            key="details_prospect"
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

            col1, col2, col3, col4 = st.columns(4)

            col1.write("**Email**")
            col1.write(prospect["email"] or "Not provided")

            col2.write("**Phone**")
            col2.write(prospect["phone"] or "Not provided")

            col3.write("**LinkedIn**")
            if prospect.get("linkedin_url"):
                # Lien ouvert par VOUS dans votre navigateur : REVORA ne consulte pas LinkedIn
                col3.markdown(f"[Open profile]({prospect['linkedin_url']})")
            else:
                col3.write("Not provided")

            col4.write("**Status**")
            col4.write(prospect["status"])

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

            # PREPARATION DU PROCHAIN APPEL (objections deja exprimees)

            preparation = call_preparation(contact_id)

            with st.expander(
                f"Prepare the next call — {len(preparation)} objection type(s) already raised",
                expanded=any(item["open"] for item in preparation),
            ):
                if not preparation:
                    st.caption("No objection recorded for this prospect yet.")

                for item in preparation:
                    st.markdown(
                        f"**{item['category']}** · raised {item['count']} time(s), "
                        f"last on {format_day(item['last_seen'])}"
                        + (f" · :orange[{item['open']} still open]" if item["open"] else "")
                    )

                    for verbatim in item["verbatims"]:
                        st.caption(f"“{verbatim}”")

                    if item["response"]:
                        st.info(item["response"])
                    else:
                        st.caption("No recommended response yet — add one in Objections › Playbook.")

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

            # OBJECTIONS DU PROSPECT

            st.subheader("Objections")

            prospect_objections = get_objections(contact_id)

            for objection in prospect_objections:
                with st.container(border=True):

                    col_text, col_status, col_delete = st.columns([5, 2, 1], vertical_alignment="center")

                    col_text.markdown(f"**{objection['category']}**")
                    col_text.caption(
                        f"{objection['occurred_at_local']} · stage: {objection['stage'] or '—'}"
                        f" · {objection['source']}"
                    )

                    if objection["verbatim"]:
                        col_text.write(f"“{objection['verbatim']}”")

                    new_status = col_status.selectbox(
                        "Status", OBJECTION_STATUSES,
                        index=OBJECTION_STATUSES.index(objection["status"])
                        if objection["status"] in OBJECTION_STATUSES else 0,
                        key=f"objection_status_{objection['id']}",
                        label_visibility="collapsed",
                    )

                    if new_status != objection["status"]:
                        set_objection_status(objection["id"], new_status)
                        st.session_state["flash"] = f"Objection marked as {new_status}."
                        st.rerun()

                    if col_delete.button(
                        "", icon=":material/delete:", key=f"objection_delete_{objection['id']}",
                        help="Delete this objection (entered by mistake)",
                    ):
                        delete_objection(objection["id"])
                        st.session_state["flash"] = "Objection deleted."
                        st.rerun()

            with st.form(f"objection_form_{contact_id}", clear_on_submit=True):

                st.caption(
                    "Record only what the prospect actually said. "
                    "Objections can also be noted when recording an interaction."
                )

                col1, col2 = st.columns([1, 2])

                category = col1.selectbox(
                    "Category", objection_categories(get_objections()),
                    index=None, accept_new_options=True, placeholder="Choose or type",
                )
                verbatim = col2.text_input("Wording (optional)")

                if st.form_submit_button("Add objection", width="stretch"):
                    ok, message = record_objection(contact_id, category, verbatim)

                    if ok:
                        st.session_state["flash"] = message
                        st.rerun()
                    else:
                        st.error(message)

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

    # ---------- EN-TETE : titre et choix de la vue (comme HubSpot) ----------

    col_title, col_view = st.columns([3, 2], vertical_alignment="bottom")

    col_title.title("Prospecting Pipeline")
    view = col_view.segmented_control(
        "View",
        ["Board", "Table", "Priorities", "Stages"],
        default="Board",
        key="pipeline_view",
        label_visibility="collapsed",
    ) or "Board"

    show_flash_message()

    stages = get_stages()
    summaries = get_activity_summary()

    if view != "Stages":

        # ---------- BARRE D'OUTILS : recherche, filtres, tri ----------

        col_search, col_filter, col_sort = st.columns([3, 1, 2], vertical_alignment="bottom")

        query = col_search.text_input(
            "Search", placeholder="Search name, company, email or phone",
            key="pipeline_search", label_visibility="collapsed"
        )

        with col_filter.popover("Filter", icon=":material/filter_list:", width="stretch"):
            selected_verticals = st.multiselect("Vertical", get_verticals(), key="pipeline_verticals")
            selected_temperatures = st.multiselect(
                "Temperature", ["Hot", "Warm", "Cold"], key="pipeline_temperatures"
            )
            min_score = st.slider("Minimum score", 0, 100, 0, key="pipeline_min_score")
            stale_days = st.number_input(
                "Inactive after (days)", min_value=1, value=DEFAULT_STALE_DAYS, key="stale_days"
            )
            show_closed = st.toggle("Show closed stages", key="pipeline_show_closed")

        sort_by = col_sort.selectbox(
            "Sort by", SORT_OPTIONS, key="pipeline_sort", label_visibility="collapsed"
        )

        # ---------- FILTRES RAPIDES (ligne sous la barre, comme HubSpot) ----------

        owners = sorted({p["owner"] for p in prospects if p["owner"]})

        def quick_label(name, key, default):
            value = st.session_state.get(key)
            if isinstance(value, list):
                value = ", ".join(value) if value else None
            return f"{name}: {value}" if value and value != default else name

        col_owner, col_created, col_activity, col_follow, _ = st.columns([1, 1, 1, 1, 1])

        with col_owner.popover(quick_label("Sales owner", "pipeline_owners", None), width="stretch"):
            selected_owners = st.multiselect("Sales owner", owners, key="pipeline_owners")

        with col_created.popover(quick_label("Create date", "qf_created", "Any time"), width="stretch"):
            created_filter = st.radio("Create date", CREATED_FILTERS, key="qf_created")

        with col_activity.popover(quick_label("Last activity", "qf_activity", "Any time"), width="stretch"):
            activity_filter = st.radio("Last activity", ACTIVITY_FILTERS, key="qf_activity")

        with col_follow.popover(quick_label("Next follow-up", "qf_follow_up", "Any"), width="stretch"):
            follow_up_filter = st.radio("Next follow-up", FOLLOW_UP_FILTERS, key="qf_follow_up")

        # ---------- APPLICATION DES FILTRES ET DU TRI ----------

        filtered = filter_prospects(prospects, query, selected_verticals, None, None, selected_owners)
        filtered = filter_quick(
            filtered, summaries, created_filter, activity_filter, follow_up_filter, stale_days
        )
        filtered = [
            p for p in filtered
            if scores[p["id"]]["global"] >= min_score
            and (not selected_temperatures or scores[p["id"]]["temperature"] in selected_temperatures)
        ]
        filtered = sort_prospects(filtered, sort_by, summaries, scores)

        visible_stages = [s for s in stages if show_closed or not s["is_closed"]]
        board = build_board(filtered, stages)
        hidden = sum(len(board[s["name"]]) for s in stages if s not in visible_stages)

        st.caption(
            f"{len(filtered)} of {len(prospects)} prospect(s)"
            + (f" · {hidden} in closed stages (hidden)" if hidden and view != "Priorities" else "")
        )

    # ---------- VUE KANBAN (glisser-deposer) ----------

    if view == "Board":

        pipeline_board(
            [
                {
                    "name": stage["name"],
                    "closed": stage["is_closed"],
                    "cards": [
                        build_card(p, summaries.get(p["id"]), scores.get(p["id"]), stale_days)
                        for p in board[stage["name"]]
                    ],
                }
                for stage in visible_stages
            ],
            key=BOARD_KEY,
            on_move=_on_board_move,
            on_open=_on_board_open,
        )

        st.caption("Drag a card to another column to change its stage. Click a company to open the prospect file.")

    # ---------- VUE TABLE ----------

    if view == "Table":

        rows = [
            {
                "Company": card["title"],
                "Contact": card["contact"],
                "Stage": p["status"],
                "Score": card["score"],
                "Temperature": card["temperature"],
                "Created": card["created"],
                "Last activity": card["last_activity"],
                "Next follow-up": card["next_follow_up"],
                "Owner": card["owner"],
            }
            for p in filtered
            if p["status"] in {s["name"] for s in visible_stages}
            for card in [build_card(p, summaries.get(p["id"]), scores.get(p["id"]), stale_days)]
        ]

        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            st.info("No prospect matches these filters.")

    # ---------- VUE PRIORISEE ----------

    if view == "Priorities":

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

    if view == "Stages":

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
        key="activity_tabs",
        on_change="rerun"
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
    st.caption(
        "Every objection your prospects actually expressed — and how to answer it next time. "
        "Nothing here is guessed: only recorded objections are counted."
    )

    show_flash_message()

    all_objections = get_objections()

    # ---------- FILTRES ----------

    col_period, col_vertical, _ = st.columns([1, 2, 2])

    period = col_period.selectbox(
        "Period", ["Last 30 days", "Last 90 days", "All time"], index=2, key="objections_period"
    )
    verticals_used = sorted({o["vertical"] for o in all_objections if o["vertical"]})
    selected_verticals = col_vertical.multiselect("Vertical", verticals_used, key="objections_verticals")

    objections = filter_period(
        all_objections, {"Last 30 days": 30, "Last 90 days": 90}.get(period)
    )

    if selected_verticals:
        objections = [o for o in objections if o["vertical"] in selected_verticals]

    # ---------- INDICATEURS ----------

    by_category = count_by(objections, "category")
    handled = sum(1 for o in objections if o["status"] == "Handled")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Objections", len(objections))
    col2.metric("Open", sum(1 for o in objections if o["status"] == "Open"))
    col3.metric("Handled rate", f"{round(handled / len(objections) * 100)} %" if objections else "—")
    col4.metric("Most frequent", by_category[0][0] if by_category else "—")

    tab_insights, tab_playbook, tab_log = st.tabs(
        ["Insights", "Playbook", "Log"], key="objections_tabs"
    )

    # ---------- ANALYSE ----------

    with tab_insights:

        if not objections:
            st.info(
                "No objection recorded for this period. Note objections when recording a call "
                "or an email, or from a prospect file."
            )

        else:
            col_left, col_right = st.columns(2)

            with col_left:
                st.markdown("**Most frequent objections**")
                st.bar_chart(
                    pd.DataFrame(by_category, columns=["Category", "Objections"]).set_index("Category"),
                    horizontal=True,
                    sort=False,  # garde l'ordre des données : la plus fréquente en premier
                )

            with col_right:
                st.markdown("**Evolution per week**")
                trend = weekly_trend(objections)
                st.bar_chart(
                    pd.DataFrame.from_dict(trend, orient="index").fillna(0).astype(int),
                    stack=True,
                )

            def pivot(field, label):
                frame = pd.DataFrame(objections)
                frame[field] = frame[field].fillna("Unknown")
                table = pd.crosstab(frame[field], frame["category"])
                table["Total"] = table.sum(axis=1)
                return table.sort_values("Total", ascending=False).rename_axis(label)

            col_left, col_right = st.columns(2)

            with col_left:
                st.markdown("**By vertical**")
                st.dataframe(pivot("vertical", "Vertical"), width="stretch")

            with col_right:
                st.markdown("**By pipeline stage** (stage when the objection was raised)")
                st.dataframe(pivot("stage", "Stage"), width="stretch")

            st.markdown("**By company** (top 10)")
            st.dataframe(pivot("company_name", "Company").head(10), width="stretch")

            st.markdown("**How well each objection is handled**")
            st.dataframe(pd.DataFrame(resolution_by_category(objections)), width="stretch", hide_index=True)

    # ---------- PLAYBOOK : reponses recommandees ----------

    with tab_playbook:

        st.caption(
            "Write your recommended answer for each objection. It appears in the prospect file "
            "(“Prepare the next call”) whenever this objection was raised. "
            "Examples are anonymized: names, companies, emails and phone numbers are removed."
        )

        responses = get_objection_responses()
        counts = dict(count_by(all_objections, "category"))
        ordered = sorted(
            objection_categories(all_objections),
            key=lambda c: (-counts.get(c, 0), objection_categories(all_objections).index(c)),
        )

        for category in ordered:
            with st.container(border=True):

                st.markdown(f"**{category}** · {counts.get(category, 0)} time(s)")

                for example in anonymized_examples(all_objections, category, limit=3):
                    st.caption(f"“{example}”")

                with st.form(f"playbook_{category}"):

                    response = st.text_area(
                        "Recommended response",
                        value=responses.get(category, ""),
                        placeholder=PLAYBOOK_PLACEHOLDER,
                        height=110,
                        label_visibility="collapsed",
                    )

                    if st.form_submit_button("Save response"):
                        set_objection_response(category, response)
                        st.session_state["flash"] = f"Response saved for “{category}”."
                        st.rerun()

    # ---------- JOURNAL ----------

    with tab_log:

        if not objections:
            st.info("No objection for these filters.")

        else:
            log = pd.DataFrame([
                {
                    "id": o["id"],
                    "Date": o["occurred_at_local"],
                    "Prospect": f"{o['first_name']} {o['last_name']}",
                    "Company": o["company_name"],
                    "Vertical": o["vertical"],
                    "Stage": o["stage"],
                    "Category": o["category"],
                    "Wording": o["verbatim"],
                    "Status": o["status"],
                    "Source": o["source"],
                }
                for o in objections
            ])

            edited = st.data_editor(
                log,
                column_config={
                    "id": None,
                    "Status": st.column_config.SelectboxColumn("Status", options=OBJECTION_STATUSES, required=True),
                },
                disabled=[c for c in log.columns if c != "Status"],
                hide_index=True,
                width="stretch",
                key="objections_log_editor",
            )

            changes = [
                (int(row["id"]), row["Status"])
                for (_, row), (_, before) in zip(edited.iterrows(), log.iterrows())
                if row["Status"] != before["Status"]
            ]

            if changes:
                for objection_id, status in changes:
                    set_objection_status(objection_id, status)
                st.session_state.pop("objections_log_editor", None)
                st.session_state["flash"] = f"{len(changes)} objection status(es) updated."
                st.rerun()

elif page == "AI Copilot":
    st.title("AI Sales Copilot")
    st.info("Your AI assistant is coming next.")

elif page == "Performance":

    col_title, col_period = st.columns([3, 2], vertical_alignment="bottom")

    col_title.title("Performance")
    period_label = col_period.segmented_control(
        "Period", list(PERFORMANCE_PERIODS), default="Last 30 days",
        key="performance_period", label_visibility="collapsed",
    ) or "Last 30 days"

    start, end = period_range(PERFORMANCE_PERIODS[period_label])
    previous_start, previous_end = previous_range(start, end)

    st.caption(
        f"{start.strftime('%d/%m/%Y')} – {end.strftime('%d/%m/%Y')} · "
        f"compared with the previous {PERFORMANCE_PERIODS[period_label]} days · "
        "based only on recorded interactions"
    )

    all_interactions = get_all_interactions()
    all_objections = get_objections()

    current = compute_kpis(all_interactions, all_objections, start, end)
    previous = compute_kpis(all_interactions, all_objections, previous_start, previous_end)

    def kpi(column, label, key, unit="", inverse=False, help_text=None):
        """Carte KPI : un chiffre, un libellé, la comparaison avec la période précédente."""

        value = current[key]
        change = delta(value, previous[key])

        column.metric(
            label,
            "—" if value is None else f"{value}{unit}",
            delta=None if not change else f"{change:+g}{' pts' if unit == ' %' else ''}",
            delta_color="inverse" if inverse else "normal",
            help=help_text,
        )

    st.markdown("**Activity**")
    col1, col2, col3, col4, col5 = st.columns(5)
    kpi(col1, "Calls made", "calls")
    kpi(col2, "Calls / working day", "calls_per_day")
    kpi(col3, "Connection rate", "connection_rate", " %",
        help_text="Outbound calls that reached a conversation / outbound calls.")
    kpi(col4, "Emails sent", "emails_sent")
    kpi(col5, "Emails / working day", "emails_per_day")

    st.markdown("**Results**")
    col1, col2, col3, col4, col5 = st.columns(5)
    kpi(col1, "Reply rate", "reply_rate", " %",
        help_text="Contacted prospects who replied (inbound email, call or LinkedIn) / contacted prospects.")
    kpi(col2, "Meetings booked", "meetings")
    kpi(col3, "Conversion rate", "conversion_rate", " %",
        help_text="Contacted prospects who booked a meeting / contacted prospects.")
    kpi(col4, "Objections", "objections", inverse=True)
    kpi(col5, "Days between follow-ups", "follow_up_delay", inverse=True,
        help_text="Average days between two successive outbound touches on the same prospect.")

    st.markdown("**LinkedIn** (recorded manually)")
    col1, col2, col3, _, _ = st.columns(5)
    kpi(col1, "Connection requests", "linkedin_requests")
    kpi(col2, "Acceptance rate", "linkedin_acceptance_rate", " %",
        help_text="Prospects invited in the period who then accepted / prospects invited.")
    kpi(col3, "LinkedIn messages sent", "linkedin_messages")

    st.caption(
        f"{current['contacted']} prospect(s) contacted · {current['replied']} replied · "
        f"{current['emails_received']} email(s) received · {current['working_days']} working day(s)"
    )

    st.divider()

    st.markdown("**Daily activity**")
    activity_rows = daily_activity(all_interactions, start, end)

    if any(row["Calls"] or row["Emails sent"] or row["Replies"] for row in activity_rows):
        st.bar_chart(pd.DataFrame(activity_rows).set_index("Day"), stack=False)
    else:
        st.info("No interaction recorded in this period.")

    st.markdown("**By vertical**")
    vertical_rows = by_vertical(all_interactions, all_objections, prospects, start, end)

    if vertical_rows:
        st.dataframe(pd.DataFrame(vertical_rows), width="stretch", hide_index=True)
    else:
        st.info("No prospect contacted in this period.")

    with st.expander("How are these indicators calculated?"):
        st.markdown(
            "- **Calls made**: outbound calls. **Per working day**: divided by Monday–Friday days.\n"
            "- **Connection rate**: outbound calls with result *Completed, Positive response, Objection, "
            "Meeting booked* or *Information shared*, divided by outbound calls.\n"
            "- **Reply rate**: prospects contacted outbound in the period who then sent an inbound "
            "email, call or LinkedIn message, divided by prospects contacted.\n"
            "- **Meetings booked**: interactions whose result is *Meeting booked*.\n"
            "- **Conversion rate**: contacted prospects who booked a meeting in the period.\n"
            "- **Days between follow-ups**: average gap between two successive outbound touches "
            "on the same prospect.\n"
            "- A rate shows **—** when there is nothing to divide (never a misleading 0 %).\n"
            "- **Performance by sequence** is not available yet: REVORA has no sequences "
            "(planned with the HubSpot connection)."
        )

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
            "LinkedIn connection accepted 10 (max 10), "
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
