"""Page « Settings »."""

from screens.common import *  # noqa: F401,F403
from screens.shared import *  # noqa: F401,F403


# ---------- Équipe (phase 11.1, emails et droits : phase 12.1) : callbacks ----------

def _flash(ok, message):
    st.session_state["flash"] = message if ok else f"Error: {message}"


def _protect_self(user_id, protected_id, key, saved_value):
    """Avec la vraie connexion, un manager ne peut pas se retirer ses propres droits (risque de blocage)."""

    if protected_id is not None and user_id == protected_id:
        st.session_state[key] = saved_value           # le contrôle réaffiche la valeur enregistrée
        _flash(False, "You cannot change your own role or deactivate yourself while signed in.")
        return True

    return False


def _change_role(user_id, protected_id, saved_role):
    key = f"team_role_{user_id}"
    if not _protect_self(user_id, protected_id, key, saved_role):
        _flash(*set_user_role(user_id, st.session_state[key]))


def _change_active(user_id, protected_id, saved_active):
    key = f"team_active_{user_id}"
    if not _protect_self(user_id, protected_id, key, saved_active):
        _flash(*set_user_active(user_id, st.session_state[key]))


def _change_email(user_id, saved_email):
    key = f"team_email_{user_id}"
    ok, message = set_user_email(user_id, st.session_state[key])
    if not ok:
        st.session_state[key] = saved_email or ""      # email refusé : le champ réaffiche l'ancien
    _flash(ok, message)


def _import_owners(prospects):
    _, message = import_owners(get_users(), prospects)
    st.session_state["flash"] = message


def _sign_in_status(ctx):
    """État de la vraie connexion, affiché en tête de la section Team."""

    if ctx.auth:
        st.caption(":green[:material/lock:] **Sign-in is on**: each person signs in with the account "
                   "whose email is listed below. Only managers can change the team.")
        return

    missing = auth_missing_settings(st.secrets)
    if len(missing) < len(AUTH_REQUIRED_KEYS):           # section [auth] commencée mais incomplète
        st.warning("Sign-in is configured but incomplete. Missing in .streamlit/secrets.toml › [auth]: "
                   + ", ".join(missing) + ".", icon=":material/lock_open:")
    else:
        st.caption(":material/lock_open: **Sign-in is off** (local prototype): anyone who opens REVORA can "
                   "pick a name in « Signed in as ». Add each person's work email now: it will be used "
                   "when sign-in is turned on (see README).")


def team_section(ctx, prospects):
    """Équipe : email de connexion, rôle, actif/inactif, ajout, import des propriétaires existants."""

    st.subheader("Team")
    st.caption("Sales reps and managers. Their names are proposed as sales owner.")
    _sign_in_status(ctx)

    users = get_users()
    can_edit = can_manage_team(ctx.user, ctx.auth)
    protected_id = ctx.user["id"] if ctx.auth and ctx.user else None
    missing = missing_owners(users, prospects)
    import_action = {
        "label": f"Add {len(missing)} sales owner(s) from your prospects", "icon": ":material/group_add:",
        "on_click": _import_owners, "args": (prospects,),
    }

    if not users:
        empty_state(
            "No team member yet",
            "Add yourself and your colleagues below"
            + (f", or import the sales owners already on your prospects ({', '.join(missing)})." if missing else "."),
            [import_action] if missing and can_edit else [], icon=":material/group:", key="team_empty",
        )
    else:
        with st.container(border=True):
            for user in users:
                # Nom et email l'un sous l'autre : la colonne principale est étroite
                col_name, col_role, col_active = st.columns([3.2, 1.8, 0.8], vertical_alignment="center")
                col_name.markdown(user["name"] if user["active"] else f":gray[{user['name']} · inactive]")
                col_name.text_input(
                    "Email", value=user.get("email") or "", key=f"team_email_{user['id']}",
                    placeholder="work email for sign-in", label_visibility="collapsed",
                    on_change=_change_email, args=(user["id"], user.get("email")), disabled=not can_edit,
                )
                col_role.selectbox(
                    "Role", USER_ROLES, index=USER_ROLES.index(user["role"]) if user["role"] in USER_ROLES else 0,
                    key=f"team_role_{user['id']}", label_visibility="collapsed",
                    on_change=_change_role, args=(user["id"], protected_id, user["role"]), disabled=not can_edit,
                )
                col_active.toggle(
                    "Active", value=bool(user["active"]), key=f"team_active_{user['id']}",
                    on_change=_change_active, args=(user["id"], protected_id, bool(user["active"])),
                    disabled=not can_edit,
                    label_visibility="collapsed",
                    help="Active. Inactive users stay in history but can no longer sign in or be chosen.",
                )

        if missing and can_edit:
            st.caption(f"Sales owners on your prospects but not in the team: {', '.join(missing)}.")
            st.button(import_action["label"], icon=import_action["icon"], key="team_import",
                      on_click=_import_owners, args=(prospects,))

    if not can_edit:
        st.caption("Only managers can change the team.")
        return

    with st.form("team_add_form", clear_on_submit=True):
        col_name, col_email = st.columns(2)
        name = col_name.text_input("Name", placeholder="Example: Léa Martin")
        email = col_email.text_input("Email (optional)", placeholder="lea.martin@company.com")
        col_role, col_submit = st.columns(2, vertical_alignment="bottom")
        role = col_role.selectbox("Role", USER_ROLES)
        submitted = col_submit.form_submit_button("Add to team", icon=":material/person_add:", width="stretch")

    if submitted:
        ok, message = create_user(name, role, email)

        if ok:
            st.session_state["flash"] = message
            st.rerun()
        else:
            st.error(message)


# ---------- Sauvegardes et erreurs (phase 12.3) ----------

def _backup_now():
    try:
        path = backup_now(database.DATABASE_PATH)
        st.session_state["flash"] = f"Backup saved: {path.name}."
    except Exception as error:
        log_error(error, "manual backup")
        st.session_state["flash"] = f"Error: backup failed ({error})."


def backups_section():
    """Dernière sauvegarde, sauvegarde immédiate, et dernières erreurs notées."""

    st.subheader("Backups and errors")
    backups = list_backups(database.DATABASE_PATH)
    folder = backup_dir(database.DATABASE_PATH)

    if backups:
        last = backups[0][0]
        st.caption(
            f":material/backup: Last automatic backup: **{last.strftime('%d/%m/%Y %H:%M')}** · "
            f"{len(backups)} kept (the {BACKUP_KEEP} most recent) in `backups/auto/{folder.name}`."
        )
    else:
        st.caption(":material/backup: No automatic backup yet. One is made each day when REVORA first opens.")

    st.caption("To restore a backup, use the command line (see README): REVORA first saves the current "
               "database, so nothing can be lost.")
    st.button("Back up now", icon=":material/save:", key="backup_now", on_click=_backup_now)

    errors = recent_errors(database.DATABASE_PATH, limit=5)
    if errors:
        with st.expander(f"Recent errors ({len(errors)})", icon=":material/error:"):
            for stamp, where, details in errors:
                st.markdown(f"**{stamp}** · {where}")
                st.code(details[-1500:], language="text")
    else:
        st.caption(":material/check_circle: No error recorded.")


def _choose_provider():
    name = st.session_state["ai_provider_choice"]
    set_setting(AI_PROVIDER_SETTING, name)
    st.session_state["flash"] = f"AI provider: {AI_PROVIDERS[name].LABEL}."


def _toggle_ai():
    enabled = st.session_state["ai_enabled_toggle"]
    set_setting(AI_SETTING, enabled)
    st.session_state["flash"] = "AI features enabled." if enabled else "AI features disabled."


def render(ctx):
    """Affiche la page « Settings »."""

    prospects, stage_names, scores = ctx.prospects, ctx.stage_names, ctx.scores


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

    # ---------- FONCTIONS IA (phase 10.1) ----------

    st.divider()
    st.subheader("AI features")
    st.caption(
        "Call preparation and follow-up email drafts in the prospect file, generated only when you "
        "click. Sent for one prospect: name, company, job title, stage, its last 10 interactions, its "
        "objections and your playbook answers. Never sent: email address, phone number, LinkedIn URL. "
        "Nothing is saved or sent to the prospect without your action. "
        "Use demo or test data only unless you are authorized."
    )

    names = list(AI_PROVIDERS)
    st.radio(
        "AI provider", names, index=names.index(ai_provider_name()), key="ai_provider_choice",
        format_func=lambda n: f"{AI_PROVIDERS[n].LABEL} ({AI_PROVIDERS[n].MODEL})",
        horizontal=True, on_change=_choose_provider,
    )

    provider = ai_provider()
    has_key = provider.is_configured()
    st.caption(f"API key ({provider.API_KEY_NAME} in .env): {'detected' if has_key else 'not set'}")

    if provider.FREE_TIER_NOTE:
        st.caption(f":orange[:material/warning:] {provider.FREE_TIER_NOTE} Demo data only.")

    st.toggle(
        "Enable AI features", value=bool(get_setting(AI_SETTING, False)), key="ai_enabled_toggle",
        disabled=not has_key, on_change=_toggle_ai,
        help="Off by default. Requires an API key for the selected provider in the .env file.",
    )

    # Style des brouillons d'email (utilisé par « Draft a follow-up email »)
    style = ai_email_style(get_setting(AI_EMAIL_STYLE_SETTING))

    with st.form("ai_email_style_form"):
        st.markdown("**Email drafts**")
        col_lang, col_tone, col_sign = st.columns([1, 1, 2])
        language = col_lang.selectbox("Language", AI_EMAIL_LANGUAGES,
                                      index=AI_EMAIL_LANGUAGES.index(style["language"]),
                                      help="Auto: the language of the latest exchanges with the prospect.")
        tone = col_tone.selectbox("Tone", AI_EMAIL_TONES, index=AI_EMAIL_TONES.index(style["tone"]),
                                  help="Formal always uses « vous » in French.")
        signature = col_sign.text_input("Signature", value=style["signature"],
                                        placeholder="Example: Léa Martin — SDR, Acme")

        if st.form_submit_button("Save email style"):
            set_setting(AI_EMAIL_STYLE_SETTING,
                        {"language": language, "tone": tone, "signature": signature.strip()})
            st.session_state["flash"] = "Email style saved."
            st.rerun()

    # ---------- EQUIPE (phase 11.1) ----------

    st.divider()
    team_section(ctx, prospects)

    # ---------- SAUVEGARDES ET ERREURS (phase 12.3) ----------

    st.divider()
    backups_section()

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
