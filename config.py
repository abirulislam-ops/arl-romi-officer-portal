"""
Officer Portal — configuration (NO secrets; safe to commit).

Credentials come from Streamlit Cloud secrets (st.secrets) or environment
variables. This file only declares the variable names and table names.
"""

import os

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

TABLE_SBU = "romi_sbu"
TABLE_CAMPAIGN = "romi_campaign"
