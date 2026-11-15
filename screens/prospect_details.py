"""Fiche prospect 360° (blueprint §5.3).

Organisation :
  - en-tête : identité, étape, propriétaire, score, actions principales ;
  - prochaine action, toujours visible ;
  - à gauche : timeline unifiée (interactions, relances, objections, étapes, score) ;
  - à droite : panneaux repliables (coordonnées, activité, score, qualification,
    préparation d'appel, objections, relances).

Les actions s'ouvrent dans des fenêtres qui réutilisent les formulaires existants.
"""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403

from core.timeline_service import KINDS as TIMELINE_KINDS, build_timeline, filter_timeline
from database import get_stage_changes

TIMELINE_ICONS = {
    "Call": ":material/call:", "Email": ":material/mail:", "LinkedIn": ":material/work:",
    "Note": ":material/sticky_note_2:", "Follow-up": ":material/event:",
    "Objection": ":material/forum:", "Stage": ":material/view_kanban:",
    "Score": ":material/trending_up:", "Prospect": ":material/person_add:",
}

QUALIFICATION_LABELS = {
    "need_identified": "Need identified",
    "is_decision_maker": "Decision maker",
    "budget_confirmed": "Budget confirmed",
    "demo_requested": "Demo requested",
}


# ==========================================
# FENETRES D'ACTION (formulaires existants)
# ==========================================

@st.dialog("Log an interaction", width="large")
def log_interaction_dialog(contact_id):
    submitted, _, data = interaction_form(f"dialog_interaction_{contact_id}")

    if submitted:
        ok, message = log_interaction(contact_id, data)

        if ok:
            st.session_state["flash"] = message
            st.rerun()
        else:
            st.error(message)


@st.dialog("Schedule a follow-up")
def follow_up_dialog(contact_id):
    with st.form(f"dialog_task_{contact_id}"):
        title = st.text_input("Action", placeholder="Example: Call back after the demo")
        description = st.text_area("Description")
        due_date = st.date_input("Due date")
        submitted = st.form_submit_button("Schedule follow-up", width="stretch")

    if submitted:
        if not title.strip():
            st.error("Enter an action title.")
        else:
            create_task(contact_id, title, description, due_date.isoformat())
            st.session_state["flash"] = "Follow-up scheduled."
            st.rerun()


@st.dialog("Record an objection")
def objection_dialog(contact_id):
    st.caption("Record only what the prospect actually said.")

    with st.form(f"dialog_objection_{contact_id}"):
        category = st.selectbox(
            "Category", objection_categories(get_objections()),
            index=None, accept_new_options=True, placeholder="Choose or type",
        )
        verbatim = st.text_input("Wording (optional)")
        submitted = st.form_submit_button("Add objection", width="stretch")

    if submitted:
        ok, message = record_objection(contact_id, category, verbatim)

        if ok:
            st.session_state["flash"] = message
            st.rerun()
        else:
            st.error(message)


@st.dialog("Edit prospect", width="large")
def edit_prospect_dialog(contact_id):
    prospect = get_prospect_by_id(contact_id)
    submitted, data = prospect_form(
        f"dialog_edit_{contact_id}", get_verticals(), "Save changes", defaults=prospect
    )

    if submitted:
        ok, message = update_prospect(contact_id, data)

        if ok:
            st.session_state["flash"] = message
            st.rerun()
        else:
            st.error(message)


def _change_stage(contact_id, widget_key):
    """Callback du choix d'étape dans l'en-tête."""

    ok, message = set_prospect_stage(contact_id, st.session_state[widget_key])
    st.session_state["flash"] = message if ok else f"Error: {message}"


# ==========================================
# PAGE
# ==========================================

def render(ctx):
    """Affiche la fiche prospect 360°."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores

    origin = theme.NAV_DISPLAY.get(st.session_state.get("nav_page"), st.session_state.get("nav_page") or "Overview")

    col_back, col_switch = st.columns([1, 2], vertical_alignment="center")

    col_back.button(
        f"Back to {origin}", icon=":material/arrow_back:", type="tertiary",
        on_click=close_prospect, key="prospect_back",
    )

    if not prospects:
        st.info("Add a prospect before opening a prospect file.")
        return

    prospect_options = {prospect_label(p): p["id"] for p in prospects}

    # Prospect choisi depuis une autre page mais supprime entre-temps : on l'oublie
    if st.session_state.get("details_prospect") not in prospect_options:
        st.session_state.pop("details_prospect", None)

    selected_name = col_switch.selectbox(
        "Prospect", list(prospect_options.keys()), key="details_prospect",
        label_visibility="collapsed",
    )

    contact_id = prospect_options[selected_name]
    prospect = get_prospect_by_id(contact_id)

    if not prospect:
        st.info("This prospect no longer exists.")
        return

    show_flash_message()

    interactions = get_interactions(contact_id)
    tasks = get_tasks(contact_id)
    prospect_objections = get_objections(contact_id)
    summary = get_activity_summary().get(contact_id, {})
    result = scores.get(contact_id)

    # ---------- EN-TETE ----------

    col_identity, col_actions = st.columns([3, 2], vertical_alignment="top")

    with col_identity:
        st.title(f"{prospect['first_name']} {prospect['last_name']}")
        st.caption(
            f"{prospect['job_title'] or 'Position not specified'} · "
            f"{prospect['company_name']} · {prospect['vertical'] or 'No vertical'}"
        )

        facts = [
            f"Owner: **{prospect['owner'] or 'Unassigned'}**",
            f"Score: {score_label(result)}" if result else None,
            f"Source: {prospect['source']}" if prospect.get("source") else None,
            f"[LinkedIn profile]({prospect['linkedin_url']})" if prospect.get("linkedin_url") else None,
        ]
        st.markdown(" · ".join(fact for fact in facts if fact))

    with col_actions:
        stage_key = f"stage_select_{contact_id}"
        options = list(stage_names)
        if prospect["status"] not in options:
            options.append(prospect["status"])

        st.selectbox(
            "Stage", options, index=options.index(prospect["status"]), key=stage_key,
            on_change=_change_stage, args=(contact_id, stage_key),
        )

        col_a, col_b = st.columns(2)

        if col_a.button("Log interaction", icon=":material/add_call:", type="primary",
                        width="stretch", key="action_log"):
            log_interaction_dialog(contact_id)

        if col_b.button("Follow-up", icon=":material/event:", width="stretch", key="action_follow_up"):
            follow_up_dialog(contact_id)

        if col_a.button("Objection", icon=":material/forum:", width="stretch", key="action_objection"):
            objection_dialog(contact_id)

        if col_b.button("Edit", icon=":material/edit:", width="stretch", key="action_edit"):
            edit_prospect_dialog(contact_id)

    # ---------- PROCHAINE ACTION (toujours visible) ----------

    groups = group_tasks(tasks)
    open_tasks = groups["overdue"] + groups["today"] + groups["upcoming"] + groups["no_date"]

    with st.container(border=True):
        if open_tasks:
            task = open_tasks[0]
            late = " · :red[overdue]" if task in groups["overdue"] else (
                " · :orange[today]" if task in groups["today"] else "")
            col_next, col_done = st.columns([5, 1], vertical_alignment="center")
            col_next.markdown(
                f":material/flag: **Next action:** {task['title']} · due {task['due_at'] or 'no date'}{late}"
            )
            if col_done.button("Done", key=f"next_done_{task['id']}", width="stretch"):
                complete_task(task["id"])
                st.session_state["flash"] = f"Follow-up completed: {task['title']}"
                st.rerun()
        else:
            st.markdown(":material/flag: **No next action scheduled.** Use *Follow-up* to plan one.")

    col_main, col_side = st.columns([3, 2], gap="large")

    # ---------- TIMELINE UNIFIEE ----------

    with col_main:

        theme.section_title("Timeline")

        events = build_timeline(
            prospect, interactions, tasks, prospect_objections,
            get_score_history(contact_id), get_stage_changes(contact_id),
            format_duration=format_duration,
        )

        kinds = st.pills(
            "Show", TIMELINE_KINDS, selection_mode="multi", default=TIMELINE_KINDS,
            key=f"timeline_kinds_{contact_id}", label_visibility="collapsed",
        )

        shown = filter_timeline(events, kinds or [])

        if not shown:
            st.caption("Nothing recorded for these types yet.")

        for event in shown:
            icon = TIMELINE_ICONS.get(event.get("channel") or event["kind"], ":material/history:")

            with st.container(border=True):
                st.markdown(f"{icon} **{event['title']}**")
                st.caption(" · ".join(part for part in (
                    event["at"], event["meta"],
                    event["source"] if event["source"] not in ("Manual", "REVORA") else "",
                ) if part))

                if event["detail"]:
                    st.write(event["detail"])

    # ---------- PANNEAUX DE CONTEXTE ----------

    with col_side:

        theme.section_title("Context")

        with st.expander("Contact", expanded=True, icon=":material/contact_page:"):
            st.markdown(
                f"**Email:** {prospect['email'] or 'Not provided'}  \n"
                f"**Phone:** {prospect['phone'] or 'Not provided'}  \n"
                f"**LinkedIn:** "
                + (f"[Open profile]({prospect['linkedin_url']})" if prospect.get("linkedin_url") else "Not provided")
            )

        counts = count_by_channel(interactions)

        with st.expander("Activity", expanded=True, icon=":material/bolt:"):
            # Ligne compacte : la colonne est trop étroite pour 4 cartes KPI lisibles
            st.markdown(
                f"**{counts['Call']}** calls · **{counts['Email']}** emails · "
                f"**{counts['LinkedIn']}** LinkedIn · **{counts['Note']}** notes"
            )
            st.caption(f"Last interaction: {summary.get('last_interaction_at') or 'none yet'}")

        if result:
            with st.expander(f"Score · {result['global']} {result['temperature']}", icon=":material/speed:"):
                st.markdown(
                    f"Fit **{result['fit'] if result['fit'] is not None else 'n/a'}** · "
                    f"Engagement **{result['engagement']}** · Intent **{result['intent']}**"
                )

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
                    hide_index=True,
                )

                history = score_changes(get_score_history(contact_id))

                if len(history) > 1:
                    st.caption("Score history")
                    st.line_chart(
                        pd.DataFrame([
                            {
                                "Date": row["calculated_at_local"],
                                "Global": row["global_score"],
                                "Engagement": row["engagement_score"],
                                "Intent": row["intent_score"],
                            }
                            for row in history
                        ]).set_index("Date"),
                        height=180,
                    )

        confirmed = sum(1 for field in QUALIFICATION_FIELDS if prospect.get(field))

        with st.expander(f"Qualification · {confirmed}/{len(QUALIFICATION_FIELDS)} confirmed",
                         icon=":material/fact_check:"):
            with st.form(f"qualification_form_{contact_id}"):
                st.caption("Tick only what the prospect has explicitly confirmed. These facts feed the Intent score.")

                values = {
                    field: st.checkbox(QUALIFICATION_LABELS[field], value=bool(prospect.get(field)))
                    for field in QUALIFICATION_FIELDS
                }

                if st.form_submit_button("Save qualification", width="stretch"):
                    update_qualification(contact_id, values)
                    st.session_state["flash"] = "Qualification saved. Score updated."
                    st.rerun()

        preparation = call_preparation(contact_id)

        with st.expander(
            f"Prepare the next call · {len(preparation)} objection type(s)",
            expanded=any(item["open"] for item in preparation),
            icon=":material/assignment:",
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

        with st.expander(f"Objections · {len(prospect_objections)}", icon=":material/forum:"):
            if not prospect_objections:
                st.caption("No objection recorded. Use *Objection* above to add one.")

            for objection in prospect_objections:
                col_text, col_status, col_delete = st.columns([4, 3, 1], vertical_alignment="center")

                col_text.markdown(f"**{objection['category']}**")
                col_text.caption(f"{objection['occurred_at_local']} · stage: {objection['stage'] or '—'}")

                if objection["verbatim"]:
                    col_text.caption(f"“{objection['verbatim']}”")

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

        with st.expander(f"Follow-ups · {len(open_tasks)} open", icon=":material/event:"):
            if groups["overdue"]:
                st.warning(f"{len(groups['overdue'])} overdue follow-up(s).")

            for task in open_tasks:
                follow_up_card(task, show_prospect=False)

            if not open_tasks:
                st.caption("No open follow-ups. Use *Follow-up* above to plan one.")

            for task in groups["done"]:
                st.caption(f"✓ {task['title']} · due {task['due_at'] or 'no date'}")
