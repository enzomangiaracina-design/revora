"""Imports partagés par toutes les pages (copie du bloc d'imports de main.py).

Chaque page fait `from screens.common import *` : toutes les fonctions de la
base, des services et du thème sont disponibles, comme avant le découpage.
"""

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
