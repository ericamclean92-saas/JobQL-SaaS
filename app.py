import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
import io
import numpy as np
import re
import json
import smtplib
import random
import string
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from postgrest import SyncPostgrestClient
from fpdf import FPDF

# ==========================================
# 1. 초기 설정 (페이지 & 스타일)
# ==========================================
st.set_page_config(page_title="JobQL SaaS", layout="wide", page_icon="🛡️")

def apply_enterprise_style():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
        
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
            color: #172B4D;
            background-color: #F4F5F7;
        }

        /* 사이드바 스타일 */
        section[data-testid="stSidebar"] {
            background-color: #1A1A1A;
            border-right: 1px solid #333;
        }
        section[data-testid="stSidebar"] * {
            color: #E0E0E0 !important;
        }
        div[role="radiogroup"] > label > div:first-child { display: none !important; }
        div[role="radiogroup"] > label {
            padding: 12px 16px !important;
            border-radius: 6px !important;
            margin-bottom: 4px !important;
            transition: all 0.2s;
            border: 1px solid transparent;
            background: transparent;
        }
        div[role="radiogroup"] > label:hover {
            background-color: #333333 !important;
            color: white !important;
        }
        div[role="radiogroup"] > label[data-checked="true"] {
            background-color: #800020 !important;
            color: white !important;
            font-weight: 600 !important;
            border: 1px solid #900025;
            box-shadow: 0 4px 6px rgba(0,0,0,0.3);
        }

        /* 메인 컨테이너 */
        [data-testid="stVerticalBlock"] > [style*="flex-direction: column;"] > [data-testid="stVerticalBlock"] {
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #E2E8F0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
        }

        /* 입력창 & 버튼 */
        .stTextInput input, .stSelectbox div[data-baseweb="select"] > div, .stNumberInput input {
            background-color: white;
            border: 1px solid #CBD5E1;
            border-radius: 4px;
        }
        button[kind="primary"] {
            background-color: #800020;
            color: white;
            border-radius: 4px;
            border: none;
            font-weight: 600;
            padding: 0.5rem 1rem;
        }
        button[kind="primary"]:hover { background-color: #5C0015; }
        
        /* 탭 스타일 */
        .stTabs [data-baseweb="tab-list"] { gap: 8px; }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            white-space: pre-wrap;
            background-color: white;
            border-radius: 4px 4px 0px 0px;
            gap: 1px;
            padding-top: 10px;
            padding-bottom: 10px;
        }
        .stTabs [aria-selected="true"] {
            background-color: white;
            border-bottom: 2px solid #800020;
            color: #800020;
            font-weight: bold;
        }
        </style>
    """, unsafe_allow_html=True)

apply_enterprise_style()

# ==========================================
# 2. 백엔드 연결 & 헬퍼 함수
# ==========================================
@st.cache_resource
def init_connection():
    if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
        st.error("🚨 Secrets Missing!")
        return None
    try:
        return SyncPostgrestClient(
            f"{st.secrets['SUPABASE_URL']}/rest/v1", 
            headers={"apikey": st.secrets['SUPABASE_KEY'], "Authorization": f"Bearer {st.secrets['SUPABASE_KEY']}"}
        )
    except Exception as e:
        st.error(f"🚨 DB Error: {str(e)}")
        return None

supabase = init_connection()
if not supabase: st.stop()

def sanitize_org_name(org_name): return re.sub(r'[^a-z0-9]', '', org_name.lower())

def send_email(to, subj, body, attachment=None, filename="attach.pdf"):
    try:
        if "EMAIL_SENDER" not in st.secrets: return False
        s_email = st.secrets["EMAIL_SENDER"]; s_pw = st.secrets["EMAIL_PASSWORD"]
        msg = MIMEMultipart(); msg['From'] = s_email; msg['To'] = to; msg['Subject'] = subj
        msg.attach(MIMEText(body, 'plain'))
        if attachment:
            part = MIMEApplication(attachment, Name=filename)
            part['Content-Disposition'] = f'attachment; filename="{filename}"'
            msg.attach(part)
        server = smtplib.SMTP('smtp.gmail.com', 587); server.starttls(); server.login(s_email, s_pw)
        server.sendmail(s_email, to, msg.as_string()); server.quit()
        return True
    except: return False

def generate_temp_password(length=8): return ''.join(random.choice(string.ascii_letters + string.digits) for i in range(length))

# --- PDF 생성 ---
def create_lem_pdf_bytes(df_data, org):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, f"{org} - LEM Report", 0, 1, 'C'); pdf.ln(10)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 10, f"Date: {datetime.now().strftime('%Y-%m-%d')}", 0, 1); pdf.ln(10)
    
    pdf.set_fill_color(220, 220, 220)
    pdf.set_font("Arial", 'B', 9)
    headers = ["Date", "Job #", "Crew", "Reg", "OT", "Travel"]
    widths = [25, 25, 50, 15, 15, 15]
    for i, h in enumerate(headers): pdf.cell(widths[i], 8, h, 1, 0, 'C', 1)
    pdf.ln()
    
    pdf.set_font("Arial", '', 9)
    for _, row in df_data.iterrows():
        try:
            pdf.cell(widths[0], 8, str(row.get('date', '')), 1)
            pdf.cell(widths[1], 8, str(row.get('job_number', '')), 1)
            pdf.cell(widths[2], 8, str(row.get('name_or_unit', '')), 1)
            pdf.cell(widths[3], 8, str(row.get('hours_regular', 0)), 1)
            pdf.cell(widths[4], 8, str(row.get('hours_travel', 0)), 1)
            pdf.cell(widths[5], 8, str(row.get('hours_travel', 0)), 1) # Travel
            pdf.ln()
        except: pass
    return pdf.output(dest='S').encode('latin-1')

# --- 엑셀 업로드 ---
def handle_bulk_import(uploaded_file, table_name):
    if uploaded_file:
        try:
            df_excel = pd.read_excel(uploaded_file)
            records = df_excel.to_dict(orient='records')
            for r in records:
                r['organization_id'] = CURRENT_ORG
                r['status'] = 'Active'
                r['created_at'] = str(datetime.now())
            supabase.table(table_name).insert(records).execute()
            st.success(f"✅ Imported {len(records)} items!")
            return True
        except Exception as e: st.error(f"Import Failed: {e}"); return False
    return False

# ==========================================
# 3. 인증(Auth) 및 로그인
# ==========================================
def load_permissions(org_id, role):
    if role == 'SuperAdmin': st.session_state['perms'] = {'can_view_all': True}
    else: st.session_state['perms'] = {'can_approve': role in ['Admin', 'Supervisor']}

@st.dialog("🔑 Reset Password")
def forgot_password_dialog():
    st.write("Enter email address."); email = st.text_input("Email")
    if st.button("Send Link", type="primary"):
        res = supabase.table("jobql_users").select("*").eq("email", email).execute()
        if res.data:
            new_pw = generate_temp_password()
            supabase.table("jobql_users").update({"password": new_pw}).eq("id", res.data[0]['id']).execute()
            if send_email(email, "Password Reset", f"Temp PW: {new_pw}"): st.success("Sent!")
        else: st.error("Not found.")

def check_password():
    if "password_correct" not in st.session_state:
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            st.markdown("<br><br><div style='text-align:center;'><h2>🛡️ JobQL SaaS</h2></div>", unsafe_allow_html=True)
            with st.container(border=True):
                with st.form("login_form"):
                    st.text_input("Username", key="u_in", placeholder="admin@jobql")
                    st.text_input("Password", type="password", key="p_in")
                    st.write("")
                    submit = st.form_submit_button("Sign In", type="primary", use_container_width=True)
                if st.button("Forgot Password?", use_container_width=True): forgot_password_dialog()
            
            if submit:
                try:
                    res = supabase.table("jobql_users").select("*").eq("username", st.session_state["u_in"]).execute()
                    if res.data and res.data[0]['password'] == st.session_state["p_in"]:
                        user = res.data[0]
                        st.session_state.update({"password_correct": True, "current_user": user['username'], "user_org": user['organization_id'], "user_role": user['role']})
                        load_permissions(user['organization_id'], user['role'])
                        st.rerun()
                    else: st.error("Invalid credentials")
                except Exception as e: st.error(f"Login Logic Error: {e}")
        return False
    return True

if not check_password(): st.stop()

CURRENT_USER = st.session_state.get("current_user")
CURRENT_ORG = st.session_state.get("user_org")
CURRENT_ROLE = st.session_state.get("user_role")
CURRENT_NAME = CURRENT_USER.split('@')[0].capitalize() if CURRENT_USER else ""

# ==========================================
# 4. 데이터 핸들링 (CRUD)
# ==========================================
def load_data(table, supervisor_only=False):
    try:
        q = supabase.table(table).select("*").eq("organization_id", CURRENT_ORG)
        if supervisor_only and table == 'field_tickets':
            try: q = q.eq("assigned_supervisor", CURRENT_USER)
            except: pass
        if CURRENT_ROLE == 'Crew' and table == 'field_tickets':
            q = q.eq("submitted_by", CURRENT_USER)
        return pd.DataFrame(q.execute().data)
    except: return pd.DataFrame()

def crud(action, table, data=None, uid=None):
    try:
        if action == "insert":
            data.update({"organization_id": CURRENT_ORG, "status": "Pending", "created_at": str(datetime.now())})
            supabase.table(table).insert(data).execute()
        elif action == "update": supabase.table(table).update(data).eq("id", uid).execute()
        elif action == "delete": supabase.table(table).delete().eq("id", uid).execute()
        return True
    except Exception as e: st.error(str(e)); return False

def get_options(table, col):
    df = load_data(table); return df[col].unique().tolist() if not df.empty else []

def get_supervisors():
    try:
        res = supabase.table("jobql_users").select("username").eq("organization_id", CURRENT_ORG).in_("role", ["Supervisor", "Admin", "SuperAdmin"]).execute()
        return [r['username'] for r in res.data]
    except: return []

# ==========================================
# 5. 메인 네비게이션 (요청하신 순서)
# ==========================================
with st.sidebar:
    st.markdown(f"### 🛡️ JobQL")
    st.caption(f"{CURRENT_ORG} | {CURRENT_ROLE}")
    st.write("")
    
    # [ORDER] Dashboard -> Crew -> Sup -> Tickets -> Invoices -> Fuel -> Master -> Admin
    if CURRENT_ROLE == 'SuperAdmin':
        menu_opts = ["Dashboard", "Crew Time Submission", "Supervisor Approval", "Time Tickets", "Invoices", "Fuel", "Master Data", "Platform Admin"]
    elif CURRENT_ROLE == 'Admin':
        menu_opts = ["Dashboard", "Crew Time Submission", "Supervisor Approval", "Time Tickets", "Invoices", "Fuel", "Master Data"]
    elif CURRENT_ROLE == 'Supervisor':
        menu_opts = ["Dashboard", "Crew Time Submission", "Supervisor Approval", "Time Tickets"]
    else: # Crew
        menu_opts = ["Dashboard", "Crew Time Submission"]
    
    sel = st.radio("MENU", menu_opts, label_visibility="collapsed")
    st.markdown("---")
    if st.button("Sign Out", use_container_width=True): st.session_state.clear(); st.rerun()

# ==========================================
# 6. 페이지별 기능 구현
# ==========================================

# --- 📊 Dashboard ---
if sel == "Dashboard":
    st.title("Operations Overview")
    df = load_data("field_tickets")
    c1, c2, c3, c4 = st.columns(4)
    if not df.empty:
        c1.metric("Total Tickets", len(df))
        c2.metric("Pending", len(df[df['status']=='Pending']))
        c3.metric("Approved", len(df[df['status']=='Approved']))
        c4.metric("Rejected", len(df[df['status']=='Rejected']))
    else: c1.metric("No Data", 0)

# --- 📱 Crew Time Submission (Fields Updated) ---
elif sel == "Crew Time Submission":
    st.title("Crew Time Submission")
    with st.container():
        st.info("Daily LEM Submission")
        with st.form("crew_form"):
            c_date, c_job = st.columns(2)
            w_date = c_date.date_input("Date Worked", datetime.now())
            job = c_job.selectbox("Project / Job #", ["Select..."] + get_options("master_project", "job_number"))
            
            c_sup, c_empty = st.columns(2)
            sup = c_sup.selectbox("Supervisor", ["Select..."] + get_supervisors())
            
            st.markdown("---")
            c1, c2, c3 = st.columns(3)
            reg = c1.number_input("Regular Hours", 0.0, 24.0, 10.0, 0.5)
            ot = c2.number_input("Overtime Hours", 0.0, 24.0, 0.0, 0.5)
            trav = c3.number_input("Travel Hours", 0.0, 24.0, 0.0, 0.5)
            
            sub_check = st.checkbox("Subsistence")
            desc = st.text_area("Work Description")
            
            if st.form_submit_button("🚀 Submit Ticket", type="primary"):
                if job == "Select..." or sup == "Select...": st.error("Select Job & Supervisor")
                else:
                    data = {
                        "date": str(w_date), "job_number": job, "assigned_supervisor": sup, 
                        "submitted_by": CURRENT_USER, "entry_type": "Crew", "name_or_unit": CURRENT_USER,
                        "hours_regular": reg, "hours_travel": ot, "hours_travel": trav,
                        "item_description": desc + (" [Subsistence]" if sub_check else "")
                    }
                    if crud("insert", "field_tickets", data): st.balloons(); st.success("Submitted!")

# --- 👮‍♂️ Supervisor Approval (Buttons on Top, Multi-Select) ---
elif sel == "Supervisor Approval":
    st.title("Supervisor Approval")
    with st.container():
        df = load_data("field_tickets", supervisor_only=True)
        pending = df[df['status'] == 'Pending'] if not df.empty else pd.DataFrame()
        
        if pending.empty: 
            st.success("🎉 No pending tickets.")
        else:
            # Action Buttons on Top
            c1, c2, c3 = st.columns([1, 1, 6])
            do_approve = c1.button("✅ Approve", type="primary")
            do_reject = c2.button("❌ Reject")
            
            # Table with Selection
            pending.insert(0, "Select", False)
            edited = st.data_editor(pending, hide_index=True, use_container_width=True, key="sup_grid")
            
            # Selection Logic
            sel_rows = edited[edited["Select"]]
            if not sel_rows.empty:
                # Detail View (Expandable)
                with st.expander("🔍 View Selected Ticket Details", expanded=True):
                    st.dataframe(sel_rows)
                
                if do_approve:
                    for i in sel_rows['id']: crud("update", "field_tickets", {"status": "Approved"}, i)
                    st.success("Approved!"); st.rerun()
                if do_reject:
                    for i in sel_rows['id']: crud("update", "field_tickets", {"status": "Rejected"}, i)
                    st.rerun()

# --- 🎫 Time Tickets (Ticket Management) ---
elif sel == "Time Tickets":
    st.title("Time Tickets")
    
    with st.container():
        # Toolbar: Create | Void | Bulk Edit | Search
        c_act1, c_act2, c_act3, c_search = st.columns([1, 1, 2, 3])
        
        # Create Ticket Popup
        @st.dialog("Create Ticket")
        def create_ticket_pop():
            with st.form("new_t"):
                job = st.selectbox("Job #", get_options("master_project", "job_number"))
                desc = st.text_input("Desc")
                if st.form_submit_button("Create"):
                    # Auto Ticket # Logic: Job#-Random
                    t_ref = f"{job}-{random.randint(100,999)}"
                    crud("insert", "field_tickets", {"ticket_reference": t_ref, "job_number": job, "item_description": desc, "submitted_by": CURRENT_USER})
                    st.success(f"Ticket {t_ref} Created!"); st.rerun()

        if c_act1.button("➕ Create"): create_ticket_pop()
        
        # Status Filter & Search
        search = c_search.text_input("Search Tickets", placeholder="Ticket #, Job...", label_visibility="collapsed")
        
        df = load_data("field_tickets")
        if not df.empty:
            if search: df = df[df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
            
            df.insert(0, "Select", False)
            edited = st.data_editor(df, hide_index=True, use_container_width=True, key="tt_grid")
            
            sel_rows = edited[edited["Select"]]
            
            # Bulk Actions
            if not sel_rows.empty:
                st.write("---")
                c_b1, c_b2 = st.columns([2, 5])
                new_status = c_b1.selectbox("Change Status To:", ["Pending", "Approved", "Void"])
                if c_b1.button("Update Status"):
                    for i in sel_rows['id']: crud("update", "field_tickets", {"status": new_status}, i)
                    st.success("Updated!"); st.rerun()

# --- 💰 Invoices (CSV Export) ---
elif sel == "Invoices":
    st.title("Invoices")
    with st.container():
        st.info("Export approved tickets to accounting software.")
        
        df = load_data("field_tickets")
        if not df.empty:
            approved = df[df['status'] == 'Approved']
            st.dataframe(approved, use_container_width=True)
            
            c1, c2, c3 = st.columns(3)
            # CSV Download Helpers
            csv = approved.to_csv(index=False).encode('utf-8')
            c1.download_button("📥 Export for QuickBooks", csv, "qb_import.csv", "text/csv")
            c2.download_button("📥 Export for Sage", csv, "sage_import.csv", "text/csv")
            c3.download_button("📥 Export for ADP", csv, "adp_import.csv", "text/csv")
        else:
            st.warning("No approved tickets found.")

# --- ⛽ Fuel (Table + Popup) ---
elif sel == "Fuel":
    st.title("Fuel Management")
    
    # Add Popup (Top Right Logic simulation via Column)
    c1, c2 = st.columns([5, 1])
    
    @st.dialog("Add Fuel Record")
    def add_fuel_pop():
        with st.form("fuel_add"):
            d = st.date_input("Date")
            c = st.selectbox("Crew Name", get_options("master_crew", "crew_name"))
            a = st.number_input("Amount ($)")
            if st.form_submit_button("Save"):
                crud("insert", "fuel_logs", {"date": str(d), "crew_name": c, "amount": a})
                st.success("Saved!"); st.rerun()

    if c2.button("➕ Add Fuel"): add_fuel_pop()
    
    df = load_data("fuel_logs")
    st.data_editor(df, use_container_width=True, hide_index=True)

# --- ⚙️ Master Data (All Tabs Restored) ---
elif sel == "Master Data":
    st.title("Master Data")
    
    def render_tab(table, cols):
        c1, c2, c3 = st.columns([5, 3, 2])
        c1.subheader(f"{table.replace('master_', '')} List")
        search = c2.text_input("Search", key=f"s_{table}", label_visibility="collapsed")
        
        # Create
        @st.dialog(f"Add New")
        def create_pop():
            with st.form(f"new_{table}"):
                inputs = {}
                for k, v in cols.items(): inputs[k] = st.text_input(v)
                if st.form_submit_button("Save"):
                    if crud("insert", table, inputs): st.success("Saved!"); st.rerun()
        if c3.button("➕ Create", key=f"b_{table}", use_container_width=True): create_pop()
        
        # Import
        with st.expander("📥 Bulk Import (Excel)"):
            up = st.file_uploader("Upload", type=['xlsx'], key=f"up_{table}")
            if up and st.button("Run Import", key=f"imp_{table}"): handle_bulk_import(up, table)

        # Grid
        df = load_data(table)
        if not df.empty:
            if search: df = df[df.astype(str).apply(lambda x: x.str.contains(search, case=False)).any(axis=1)]
            df.insert(0, "Select", False)
            edited = st.data_editor(df, key=f"ed_{table}", hide_index=True, use_container_width=True)
            sel_rows = edited[edited["Select"]]
            if not sel_rows.empty and st.button("🗑️ Delete Selected", key=f"del_{table}"):
                for i in sel_rows['id']: crud("delete", table, uid=i)
                st.success("Deleted!"); st.rerun()
        else: st.info("No records.")

    # All Tabs Restored
    tabs = st.tabs(["Projects", "Clients", "Reps", "Rates", "Crews", "Equipment", "Vendors"])
    with tabs[0]: render_tab("master_project", {"job_number": "Job #", "project_name": "Project Name"})
    with tabs[1]: render_tab("master_client", {"client_name": "Client Name", "email": "Email"})
    with tabs[2]: render_tab("master_client_rep", {"first_name": "First Name", "last_name": "Last Name"})
    with tabs[3]: render_tab("master_rate_list", {"rate_list_name": "Rate Name"})
    with tabs[4]: render_tab("master_crew", {"crew_name": "Name", "crew_type": "Type"})
    with tabs[5]: render_tab("master_equipment", {"unit_number": "Unit #", "equipment_name": "Model"})
    with tabs[6]: render_tab("master_vendor", {"vendor_name": "Vendor Name"})

# --- 👑 Platform Admin ---
elif sel == "Platform Admin":
    st.title("System Admin")
    df = pd.DataFrame(supabase.table("jobql_users").select("*").execute().data)
    st.dataframe(df, use_container_width=True)