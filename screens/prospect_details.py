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
from database import add_interaction, get_interaction, get_stage_changes

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
        ok, message = log_interaction(contact_id, data, created_by=current_user_id())

        if ok:
            reset_form(f"dialog_interaction_{contact_id}")
            st.session_state["flash"] = message
            st.rerun()
        else:
            st.error(message)


@st.dialog("Edit interaction", width="large")
def edit_interaction_dialog(interaction_id):
    """Corriger ou supprimer une interaction saisie à la main."""

    interaction = get_interaction(interaction_id)

    if not interaction:
        st.error("This interaction no longer exists.")
        return

    form_key = f"dialog_edit_interaction_{interaction_id}"
    submitted, _, data = interaction_form(form_key, defaults=interaction)

    if submitted:
        ok, message = edit_interaction(interaction_id, data)

        if ok:
            reset_form(form_key)
            st.session_state["flash"] = message
            st.rerun()
        else:
            st.error(message)

    with st.expander("Delete this interaction", icon=":material/delete:"):
        st.caption("Use this only for an interaction logged by mistake. Objections noted during it are kept.")
        sure = st.checkbox("I understand this cannot be undone", key=f"confirm_delete_interaction_{interaction_id}")

        if st.button("Delete interaction", disabled=not sure, key=f"delete_interaction_{interaction_id}"):
            ok, message = remove_interaction(interaction_id)
            st.session_state["flash"] = message if ok else f"Error: {message}"
            st.rerun()


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
            create_task(contact_id, title, description, due_date.isoformat(), created_by=current_user_id())
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

        # P2 : relier l'objection à l'échange où elle a été exprimée (facultatif)
        recent = get_interactions(contact_id)[:10]
        raised_during = st.selectbox(
            "Raised during (optional)", [i["id"] for i in recent], index=None,
            format_func=lambda i: next(
                interaction_label(x["channel"], x["subject"], x["occurred_at_local"]) for x in recent if x["id"] == i
            ),
            placeholder="Not linked to an interaction" if recent else "No interaction logged yet",
            disabled=not recent,
        )
        submitted = st.form_submit_button("Add objection", width="stretch")

    if submitted:
        ok, message = record_objection(contact_id, category, verbatim, interaction_id=raised_during,
                                       created_by=current_user_id())

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
        ok, message = update_prospect(contact_id, data, created_by=current_user_id())

        if ok:
            st.session_state["flash"] = message
            st.rerun()
        else:
            st.error(message)


@st.dialog("Edit company")
def edit_company_dialog(prospect):
    st.caption(f"Shared by every prospect at {prospect['company_name']}.")

    with st.form(f"dialog_company_{prospect['company_id']}"):
        website = st.text_input("Website", value=prospect.get("company_website") or "",
                                placeholder="nordvia.com")
        size = st.selectbox("Size (employees)", COMPANY_SIZES, index=(
            COMPANY_SIZES.index(prospect["company_size"]) if prospect.get("company_size") in COMPANY_SIZES else None
        ), placeholder="Not provided")
        country = st.text_input("Country", value=prospect.get("company_country") or "", placeholder="France")
        submitted = st.form_submit_button("Save company", width="stretch")

    if submitted:
        ok, message = save_company_details(prospect["company_id"], website, size, country)

        if ok:
            st.session_state["flash"] = message
            st.rerun()
        else:
            st.error(message)


def _change_stage(contact_id, widget_key, current_stage):
    """Callback du choix d'étape dans l'en-tête (confirmation si l'étape est fermée)."""

    if not request_stage_change(contact_id, st.session_state[widget_key]):
        # En attente de confirmation (ou refus) : le sélecteur reste sur l'étape actuelle
        st.session_state[widget_key] = current_stage


# ==========================================
# AI COPILOT (phase 10.1)
# ==========================================

AI_TASKS = {
    "call_brief": ("Prepare my call", ":material/support_agent:"),
    "email_draft": ("Draft a follow-up email", ":material/edit_note:"),
}


def _run_ai(task, contact_id, context):
    """Callback : génère le brief ou le brouillon (un clic = un appel à l'API)."""

    try:
        prompt = ai_build_prompt(task, context, style=ai_email_style(get_setting(AI_EMAIL_STYLE_SETTING)))
        data, usage = ai_generate(AI_SYSTEM_PROMPT, prompt, AI_SCHEMAS[task])
    except CopilotError as error:
        st.session_state[f"ai_{task}_{contact_id}"] = {"error": str(error)}
        return

    st.session_state[f"ai_{task}_{contact_id}"] = {
        "result": ai_validate_output(task, data, context), "usage": usage,
        "prices": ai_provider().PRICES,
    }


def _save_draft_as_note(contact_id, draft):
    note_id = add_interaction(contact_id, "Note", "Internal", "Other", f"Email draft: {draft['subject']}",
                              draft["body"], "", created_by=current_user_id())
    record_event("ai_draft_kept", current_user_id(), object_id=note_id, contact_id=contact_id)
    st.session_state["flash"] = "Email draft saved as a note in the timeline."


def _find_objections(contact_id, interactions, objections):
    """Callback : l'IA cherche les objections dans les notes (suggestions à confirmer)."""

    key = f"ai_objections_{contact_id}"
    context = ai_build_objection_context(interactions, objections, objection_categories(get_objections()))

    if not context["interactions"]:
        st.session_state[key] = {"empty": True}
        return

    try:
        data, usage = ai_generate(AI_OBJECTION_SYSTEM_PROMPT, ai_build_objection_prompt(context),
                                  AI_OBJECTION_SCHEMA)
    except CopilotError as error:
        st.session_state[key] = {"error": str(error)}
        return

    st.session_state[key] = {**ai_validate_objections(data, context), "scanned": len(context["interactions"]),
                             "usage": usage, "prices": ai_provider().PRICES}


def _answer_suggestion(contact_id, index, accept):
    """Callback : « Add » enregistre l'objection (source "ai"), « Dismiss » l'écarte."""

    suggestion = st.session_state[f"ai_objections_{contact_id}"]["suggestions"][index]

    # Journal (phase 13) : catégorie proposée, catégorie retenue et passage cité
    details = {"suggested_category": suggestion["category"], "wording": suggestion["wording"]}

    if not accept:
        suggestion["status"] = "dismissed"
        record_event("ai_objection_dismissed", current_user_id(), contact_id=contact_id, details=details)
        return

    # Le commercial peut corriger la catégorie avant d'ajouter
    category = st.session_state.get(f"ai_objection_category_{contact_id}_{index}") or suggestion["category"]
    ok, message = record_objection(contact_id, category, suggestion["wording"],
                                   interaction_id=suggestion["interaction_id"], source="ai",
                                   created_by=current_user_id())
    if ok:
        suggestion["status"] = "added"
        record_event("ai_objection_accepted", current_user_id(), contact_id=contact_id,
                     details={**details, "category": category})
    st.session_state["flash"] = message


def _usage_caption(outcome, prefix="Generated by"):
    prices = outcome.get("prices")
    cost = ai_estimate_cost(outcome["usage"], *prices) if prices else None
    st.caption(f"{prefix} {outcome['usage']['model']} · "
               f"{outcome['usage']['input_tokens']} tokens in, {outcome['usage']['output_tokens']} out"
               + (f" · ≈ ${cost}" if cost is not None else " · free tier"))


def _show_objection_suggestions(contact_id):
    outcome = st.session_state.get(f"ai_objections_{contact_id}")

    if not outcome:
        return

    st.markdown("**Objections found in notes**")

    if outcome.get("empty"):
        st.caption("No interaction with notes to analyse yet. Log a call or email with notes first.")
        return

    if "error" in outcome:
        st.error(outcome["error"])
        return

    st.caption("Suggestions only — nothing is saved until you click *Add*. Each wording is quoted "
               "from your notes.")
    pending = [(i, s) for i, s in enumerate(outcome["suggestions"]) if not s.get("status")]

    if not outcome["suggestions"]:
        st.caption(f"No objection found in the last {outcome['scanned']} interaction(s) with notes.")
    elif not pending:
        st.caption("All suggestions reviewed.")

    categories = objection_categories(get_objections())

    for index, suggestion in pending:
        with st.container(border=True):
            st.markdown(f"“{suggestion['wording']}”")
            st.caption(f"{suggestion['label']}" + (f" · {suggestion['why']}" if suggestion["why"] else ""))
            options = categories if suggestion["category"] in categories else categories + [suggestion["category"]]
            st.selectbox("Category", options, index=options.index(suggestion["category"]),
                         accept_new_options=True, key=f"ai_objection_category_{contact_id}_{index}")
            with st.container(horizontal=True):
                st.button("Add", icon=":material/add:", type="primary",
                          key=f"ai_objection_add_{contact_id}_{index}",
                          on_click=_answer_suggestion, args=(contact_id, index, True))
                st.button("Dismiss", type="tertiary", key=f"ai_objection_dismiss_{contact_id}_{index}",
                          on_click=_answer_suggestion, args=(contact_id, index, False))

    if outcome["dropped"]:
        st.caption(f":orange[{outcome['dropped']} suggestion(s) removed: not quoted from your notes "
                   "or already recorded.]")

    _usage_caption(outcome, prefix="Found by")


def _show_sourced(items, context):
    for item in items:
        st.markdown(f"- {item['text']}")
        if item["sources"]:
            st.caption("Source: " + " · ".join(ai_source_labels(item["sources"], context)))


def ai_copilot_panel(prospect, interactions, objections):
    """Panneau AI Copilot de la fiche : désactivé tant que non configuré."""

    contact_id = prospect["id"]

    # Clé + on_change : Streamlit mémorise l'état ouvert, le panneau reste ouvert après un clic (Add, Dismiss…)
    with st.expander("AI Copilot", icon=":material/auto_awesome:", key=f"ai_panel_{contact_id}",
                     on_change="rerun"):

        if not (get_setting(AI_SETTING, False) and ai_is_configured()):
            st.caption(
                "Off. To use it, add an API key to the .env file, then turn on "
                "« Enable AI features » in Settings."
            )
            st.button("Open Settings", type="tertiary", icon=":material/settings:",
                      key=f"ai_open_settings_{contact_id}", on_click=go_to, args=("Settings",))
            return

        context = ai_build_context(prospect, interactions, objections, get_objection_responses())
        provider = ai_provider()
        st.caption(f"Sends this prospect's last {len(context['interactions'])} interaction(s) and "
                   f"{len(context['objections'])} objection(s) to {provider.LABEL}. "
                   "No email, phone or LinkedIn URL.")
        if provider.FREE_TIER_NOTE:
            st.caption(f":orange[{provider.FREE_TIER_NOTE}]")

        with st.container(horizontal=True):
            for task, (label, icon) in AI_TASKS.items():
                st.button(label, icon=icon, key=f"ai_{task}_btn_{contact_id}",
                          on_click=_run_ai, args=(task, contact_id, context))
            st.button("Find objections in notes", icon=":material/forum:", key=f"ai_objections_btn_{contact_id}",
                      on_click=_find_objections, args=(contact_id, interactions, objections))

        for task, (label, _) in AI_TASKS.items():
            outcome = st.session_state.get(f"ai_{task}_{contact_id}")

            if not outcome:
                continue

            st.markdown(f"**{label}**")

            if "error" in outcome:
                st.error(outcome["error"])
                continue

            result = outcome["result"]

            if task == "call_brief":
                st.markdown("*Facts (from your records)*")
                _show_sourced(result["facts"], context)
                if result["hypotheses"]:
                    st.markdown("*Hypotheses — to verify on the call*")
                    _show_sourced(result["hypotheses"], context)
                if result["questions"]:
                    st.markdown("*Questions to ask*")
                    st.markdown("\n".join(f"- {q}" for q in result["questions"]))
                if result["next_step"]:
                    st.markdown(f"*Next step to propose:* {result['next_step']}")
            else:
                st.caption("Draft only — review it before sending from your mailbox. REVORA never sends it.")
                st.code(f"Subject: {result['subject']}\n\n{result['body']}", language=None, wrap_lines=True)
                if result["facts_used"]:
                    st.caption("Based on:")
                    _show_sourced(result["facts_used"], context)
                st.button("Save draft as a note", key=f"ai_save_draft_{contact_id}",
                          on_click=_save_draft_as_note, args=(contact_id, result))

            if result["dropped"]:
                st.caption(f":orange[{result['dropped']} item(s) removed: they cited no real record.]")

            _usage_caption(outcome)

        _show_objection_suggestions(contact_id)


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
        empty_state(
            "No prospect yet",
            "Add or import prospects to open their 360° file.",
            [ADD_PROSPECT, IMPORT_CSV], icon=":material/person:", key="details_empty",
        )
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
        empty_state(
            "This prospect no longer exists",
            "It may have been deleted. Go back to choose another prospect.",
            [{"label": f"Back to {origin}", "icon": ":material/arrow_back:", "on_click": close_prospect}],
            icon=":material/person_off:", key="details_missing",
        )
        return

    show_flash_message()
    stage_change_confirmation()

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
            on_change=_change_stage, args=(contact_id, stage_key, prospect["status"]),
            help=next((s["definition"] for s in get_stages()
                       if s["name"] == prospect["status"] and s.get("definition")), None),
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
                complete_follow_up(task["id"], current_user_id(), contact_id)
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
                if event.get("editable") and event.get("interaction_id"):
                    col_title, col_edit = st.columns([6, 1], vertical_alignment="center")
                    col_title.markdown(f"{icon} **{event['title']}**")
                    if col_edit.button("", icon=":material/edit:", type="tertiary",
                                       key=f"edit_interaction_{event['interaction_id']}",
                                       help="Edit or delete this interaction"):
                        edit_interaction_dialog(event["interaction_id"])
                else:
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

        ai_copilot_panel(prospect, interactions, prospect_objections)

        with st.expander("Contact", expanded=True, icon=":material/contact_page:"):
            st.markdown(
                f"**Email:** {prospect['email'] or 'Not provided'}  \n"
                f"**Phone:** {prospect['phone'] or 'Not provided'}  \n"
                f"**LinkedIn:** "
                + (f"[Open profile]({prospect['linkedin_url']})" if prospect.get("linkedin_url") else "Not provided")
            )

        if prospect.get("company_id"):
            with st.expander("Company", icon=":material/domain:"):
                website = prospect.get("company_website")
                # Lien affiché sans « https:// » : [nordvia.com](https://nordvia.com)
                website_link = f"[{website.split('://', 1)[-1]}]({website})" if website else "Not provided"
                st.markdown(
                    f"**{prospect['company_name']}**" + (f" · {prospect['vertical']}" if prospect.get("vertical") else "")
                    + "  \n"
                    f"**Website:** {website_link}  \n"
                    f"**Size:** {prospect.get('company_size') or 'Not provided'}  \n"
                    f"**Country:** {prospect.get('company_country') or 'Not provided'}"
                )
                if st.button("Edit company", icon=":material/edit:", type="tertiary",
                             key=f"edit_company_{contact_id}"):
                    edit_company_dialog(prospect)

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
