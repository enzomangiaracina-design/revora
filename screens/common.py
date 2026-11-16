"""Imports partagés par toutes les pages (copie du bloc d'imports de main.py).

Chaque page fait `from screens.common import *` : toutes les fonctions de la
base, des services et du thème sont disponibles, comme avant le découpage.
"""

from datetime import date, datetime, timedelta

import streamlit as st
import pandas as pd

import database

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
    edit_interaction,
    remove_interaction,
    group_tasks,
    period_bounds,
    count_by_channel,
    format_duration,
    source_label,
    source_options,
    filter_by_source,
    sync_status
)

from database import (
    get_stages,
    get_stage_names,
    add_stage,
    rename_stage,
    move_stage,
    set_stage_closed,
    set_stage_definition,
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
    import_prospects,
    COMPANY_SIZES,
    save_company_details,
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
    SOURCE_LABELS as OBJECTION_SOURCE_LABELS,
    PLAYBOOK_PLACEHOLDER,
    categories as objection_categories,
    record_objection,
    change_category as change_objection_category,
    interaction_label,
    source_interaction,
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
    by_vertical,
    MIN_SAMPLE,
    low_volume_rates,
    owner_options,
    filter_by_owner,
    by_owner
)

from database import get_recent_score_changes, get_recent_stage_changes
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

# AI Copilot (phase 10.1)
from ai.claude_client import CopilotError
from ai.providers import (
    PROVIDERS as AI_PROVIDERS,
    SETTING_PROVIDER as AI_PROVIDER_SETTING,
    active as ai_provider,
    active_name as ai_provider_name,
    ai_generate,
    ai_is_configured,
)
from core.copilot_service import (
    SETTING_ENABLED as AI_SETTING,
    SCHEMAS as AI_SCHEMAS,
    SYSTEM_PROMPT as AI_SYSTEM_PROMPT,
    build_context as ai_build_context,
    build_prompt as ai_build_prompt,
    validate_output as ai_validate_output,
    source_labels as ai_source_labels,
    estimate_cost as ai_estimate_cost,
    SETTING_EMAIL_STYLE as AI_EMAIL_STYLE_SETTING,
    EMAIL_LANGUAGES as AI_EMAIL_LANGUAGES,
    EMAIL_TONES as AI_EMAIL_TONES,
    email_style as ai_email_style,
    OBJECTION_SCHEMA as AI_OBJECTION_SCHEMA,
    OBJECTION_SYSTEM_PROMPT as AI_OBJECTION_SYSTEM_PROMPT,
    build_objection_context as ai_build_objection_context,
    build_objection_prompt as ai_build_objection_prompt,
    validate_objections as ai_validate_objections,
)

from database import get_setting, set_setting

# Journal des erreurs (phase 12.3)
from core.error_log import record as record_error, recent_errors, log_path as error_log_path

# Sauvegardes automatiques (phase 12.3)
from core.backup_service import (
    KEEP as BACKUP_KEEP,
    backup_dir,
    backup_now,
    daily_backup,
    list_backups,
)

# Vraie connexion (phase 12.1)
from core.auth_service import (
    is_configured as auth_is_configured,
    missing_settings as auth_missing_settings,
    REQUIRED_AUTH_KEYS as AUTH_REQUIRED_KEYS,
    sign_in_required,
    resolve_user,
    can_manage_team,
)

# Équipe (phase 11)
from database import get_users
from core.user_service import (
    ROLES as USER_ROLES,
    UNASSIGNED_LABEL,
    create_user,
    set_role as set_user_role,
    set_email as set_user_email,
    set_active as set_user_active,
    missing_owners,
    import_owners,
    owner_choices,
    find_user,
    MINE,
    EVERYONE,
    default_scope,
    owned_by,
    for_prospects,
)
