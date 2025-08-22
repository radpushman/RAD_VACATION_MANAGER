import streamlit as st
import pandas as pd
import requests
import base64
import json
from datetime import datetime, timedelta
import google.generativeai as genai

# --- GitHub 설정 ---
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
GITHUB_OWNER = st.secrets["GITHUB_OWNER"]
GITHUB_REPO = st.secrets["GITHUB_REPO"]
EMPLOYEES_FILE_PATH = "data/employees.csv"
VACATIONS_FILE_PATH = "data/vacations.csv"
CONFIG_FILE_PATH = "data/config.json"
CONSTRAINTS_FILE_PATH = "data/constraints.csv"

# --- Gemini API 설정 ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-pro-latest')
except Exception:
    model = None

# --- GitHub API 함수 ---
def get_github_file_content(file_path):
    """GitHub에서 파일 내용을 가져옵니다."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{file_path}"
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        content = base64.b64decode(res.json()['content']).decode('utf-8')
        sha = res.json()['sha']
        return content, sha
    # 404 Not Found는 파일이 없는 경우이므로 정상 처리
    if res.status_code == 404:
        return None, None
    st.error(f"Error getting file {file_path}: {res.status_code} {res.text}")
    return None, None

def update_github_file(file_path, content, sha, message="Update file"):
    """GitHub 파일 내용을 업데이트합니다."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{file_path}"
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    data = {
        "message": f"{message} via Streamlit app",
        "content": encoded_content,
        "sha": sha
    }
    res = requests.put(url, headers=headers, data=json.dumps(data))
    return res.status_code == 200

def create_github_file(file_path, content, message="Create file"):
    """GitHub에 새 파일을 생성합니다."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{file_path}"
    headers = {'Authorization': f'token {GITHUB_TOKEN}'}
    encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    data = {
        "message": f"{message} via Streamlit app",
        "content": encoded_content
    }
    res = requests.put(url, headers=headers, data=json.dumps(data))
    return res.status_code == 201

# --- 데이터 로드 ---
@st.cache_data(ttl=300) # 5분마다 데이터 새로고침
def load_data():
    from io import StringIO
    employees_content, _ = get_github_file_content(EMPLOYEES_FILE_PATH)
    vacations_content, _ = get_github_file_content(VACATIONS_FILE_PATH)
    config_content, _ = get_github_file_content(CONFIG_FILE_PATH)
    constraints_content, _ = get_github_file_content(CONSTRAINTS_FILE_PATH)

    employees_df = pd.read_csv(StringIO(employees_content)) if employees_content else pd.DataFrame(columns=['employee_name', 'total_leave_days'])
    
    if vacations_content:
        vacations_df = pd.read_csv(StringIO(vacations_content))
        vacations_df['start_date'] = pd.to_datetime(vacations_df['start_date'])
        vacations_df['end_date'] = pd.to_datetime(vacations_df['end_date'])
        if 'request_date' in vacations_df.columns:
            vacations_df['request_date'] = pd.to_datetime(vacations_df['request_date'])
    else:
        vacations_df = pd.DataFrame(columns=['employee_name', 'start_date', 'end_date', 'leave_type', 'status', 'request_date'])

    config = json.loads(config_content) if config_content else {"daily_limit": 5}
    constraints_df = pd.read_csv(StringIO(constraints_content)) if constraints_content else pd.DataFrame(columns=['employee_name_1', 'employee_name_2'])
    
    return employees_df, vacations_df, config, constraints_df

# --- 인증 ---
def check_password():
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if not st.session_state.password_correct:
        password = st.text_input("비밀번호를 입력하세요", type="password")
        if st.button("로그인"):
            if password == st.secrets["APP_PASSWORD"]:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
        return False
    return True

st.set_page_config(page_title="휴가 관리 시스템", layout="wide")

if not check_password():
    st.stop()

st.title("🌴 휴가 관리 시스템")

employees_df, vacations_df, config, constraints_df = load_data()

# --- 관리자 모드 ---
is_admin = st.sidebar.checkbox("관리자 모드")
if is_admin:
    admin_password = st.sidebar.text_input("관리자 비밀번호", type="password")
    if admin_password != st.secrets["ADMIN_PASSWORD"]:
        st.sidebar.warning("관리자 비밀번호가 일치하지 않습니다.")
        is_admin = False
    else:
        st.sidebar.success("관리자 모드 활성화")

# --- 사이드바 ---
st.sidebar.header("메뉴")
# 직원이 없는 경우를 대비한 예외 처리
employee_list = employees_df['employee_name'].tolist() if not employees_df.empty else []
selected_employee = st.sidebar.selectbox("직원 선택", options=employee_list)

# --- 남은 연차 계산 ---
if not employees_df.empty and selected_employee:
    total_leave = employees_df[employees_df['employee_name'] == selected_employee]['total_leave_days'].iloc[0]
    used_leave_df = vacations_df[
        (vacations_df['employee_name'] == selected_employee) & 
        (vacations_df['status'] == '승인') &
        (vacations_df['leave_type'] == '연차')
    ]
    used_days = (used_leave_df['end_date'] - used_leave_df['start_date']).dt.days.sum() + len(used_leave_df)
    remaining_days = total_leave - used_days
    
    st.sidebar.metric(label="남은 연차", value=f"{remaining_days}일")

# --- 메인 화면 ---
tabs = ["휴가 신청", "나의 휴가 내역", "전체 휴가 현황", "AI 휴가 비서"]
if is_admin:
    tabs.extend(["휴가 승인 관리", "직원 및 정책 관리"])

tab_list = st.tabs(tabs)

with tab_list[0]: # 휴가 신청
    st.header(f"📝 {selected_employee}님, 휴가 신청")
    with st.form("vacation_request_form"):
        leave_type = st.selectbox("휴가 종류", ["연차", "반차", "병가", "기타"])
        start_date = st.date_input("시작일")
        end_date = st.date_input("종료일")
        submitted = st.form_submit_button("신청하기")

        if submitted:
            if not selected_employee:
                st.error("직원을 먼저 선택해주세요.")
            elif start_date > end_date:
                st.error("시작일은 종료일보다 늦을 수 없습니다.")
            else:
                # 1. 일일 최대 인원 초과 확인
                date_range = pd.date_range(start_date, end_date)
                limit_exceeded = False
                for date in date_range:
                    approved_on_date = vacations_df[
                        (vacations_df['start_date'] <= date) &
                        (vacations_df['end_date'] >= date) &
                        (vacations_df['status'] == '승인')
                    ]
                    if len(approved_on_date) >= config.get("daily_limit", 5):
                        st.error(f"{date.strftime('%Y-%m-%d')}의 휴가 인원이 마감되었습니다. (최대 {config.get('daily_limit', 5)}명)")
                        limit_exceeded = True
                        break
                if limit_exceeded:
                    st.stop()

                # 2. 동시 휴가 불가 인원 확인
                conflict_found = False
                for date in date_range:
                    approved_on_date_names = vacations_df[
                        (vacations_df['start_date'] <= date) &
                        (vacations_df['end_date'] >= date) &
                        (vacations_df['status'] == '승인')
                    ]['employee_name'].tolist()

                    user_constraints = constraints_df[
                        (constraints_df['employee_name_1'] == selected_employee) |
                        (constraints_df['employee_name_2'] == selected_employee)
                    ]
                    for _, row in user_constraints.iterrows():
                        constrained_partner = row['employee_name_2'] if row['employee_name_1'] == selected_employee else row['employee_name_1']
                        if constrained_partner in approved_on_date_names:
                            st.error(f"{constrained_partner}님과 {date.strftime('%Y-%m-%d')}에 동시 휴가를 사용할 수 없습니다.")
                            conflict_found = True
                            break
                    if conflict_found:
                        break
                if conflict_found:
                    st.stop()

                # 모든 검증 통과 후 신청 진행
                new_request = pd.DataFrame([{
                    "employee_name": selected_employee,
                    "start_date": pd.to_datetime(start_date),
                    "end_date": pd.to_datetime(end_date),
                    "leave_type": leave_type,
                    "status": "대기",
                    "request_date": datetime.now().strftime('%Y-%m-%d')
                }])
                
                vacations_content, sha = get_github_file_content(VACATIONS_FILE_PATH)
                if vacations_content is not None:
                    updated_df = pd.concat([vacations_df, new_request], ignore_index=True)
                    updated_csv = updated_df.to_csv(index=False, date_format='%Y-%m-%d')
                    
                    if update_github_file(VACATIONS_FILE_PATH, updated_csv, sha, f"Vacation request by {selected_employee}"):
                        st.success("휴가 신청이 완료되었습니다.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("휴가 신청에 실패했습니다. 관리자에게 문의하세요.")
                else: # 파일이 없는 경우 새로 생성
                    updated_csv = new_request.to_csv(index=False, date_format='%Y-%m-%d')
                    if create_github_file(VACATIONS_FILE_PATH, updated_csv, f"Vacation request by {selected_employee}"):
                        st.success("휴가 신청이 완료되었습니다.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("데이터 파일 생성에 실패했습니다.")

with tab_list[1]: # 나의 휴가 내역
    st.header(f"🗓️ {selected_employee}님의 휴가 내역")
    user_vacations = vacations_df[vacations_df['employee_name'] == selected_employee].sort_values(by="start_date", ascending=False)
    st.dataframe(user_vacations.style.format({"start_date": "{:%Y-%m-%d}", "end_date": "{:%Y-%m-%d}", "request_date": "{:%Y-%m-%d}"}), use_container_width=True)

with tab_list[2]: # 전체 휴가 현황
    st.header("📅 전체 휴가 현황")
    approved_vacations = vacations_df[vacations_df['status'] == '승인']
    
    # 간단한 캘린더 뷰 (개선 가능)
    st.write("승인된 휴가 목록입니다.")
    st.dataframe(approved_vacations.sort_values(by="start_date").style.format({"start_date": "{:%Y-%m-%d}", "end_date": "{:%Y-%m-%d}", "request_date": "{:%Y-%m-%d}"}), use_container_width=True)

    # 향후 Chart 등으로 시각화 개선 가능
    # 예: st.bar_chart(...)

with tab_list[3]: # AI 휴가 비서
    st.header("🤖 AI 휴가 비서")
    st.info("휴가 규정이나 개인 휴가 현황에 대해 자유롭게 질문하세요.")

    if model is None:
        st.warning("AI 비서 기능이 현재 비활성화 상태입니다. API 키 설정을 확인하세요.")
    else:
        # 세션 상태에 메시지 기록 초기화
        if "messages" not in st.session_state:
            st.session_state.messages = []

        # 이전 대화 내용 표시
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

        # 사용자 입력
        if prompt := st.chat_input("무엇이 궁금하신가요?"):
            if not selected_employee:
                st.warning("먼저 사이드바에서 직원을 선택해주세요.")
                st.stop()
            # 사용자 메시지 저장 및 표시
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"):
                st.markdown(prompt)

            # AI 응답 생성
            with st.chat_message("assistant"):
                with st.spinner("답변을 생각하고 있어요..."):
                    # AI에 컨텍스트 정보 제공
                    user_vacations = vacations_df[vacations_df['employee_name'] == selected_employee]
                    user_context = f"""
                    - 현재 사용자: {selected_employee}
                    - 남은 연차: {remaining_days}일
                    - 사용자의 휴가 내역: {user_vacations.to_string()}
                    - 회사 휴가 규정: 연차는 자유롭게 사용 가능. 병가 신청 시에는 진단서 등 증빙 서류가 필요할 수 있음. 반차 2회는 연차 1일로 계산됨. 일일 최대 휴가 인원은 {config.get('daily_limit', 5)}명으로 제한됨.
                    - 동시 휴가 불가 정책: {constraints_df.to_string()}
                    """
                    
                    full_prompt = f"""
                    당신은 우리 회사의 친절하고 유능한 휴가 담당 챗봇입니다.
                    아래 '사용자 정보 및 규정'을 바탕으로 사용자의 질문에 대해 명확하고 간결하게 답변해주세요.
                    휴가 신청을 도와달라고 하면, 필요한 정보를 확인하고 신청 절차를 안내해주세요.

                    ---
                    [사용자 정보 및 규정]
                    {user_context}
                    ---

                    [사용자 질문]
                    {prompt}
                    """
                    
                    try:
                        response = model.generate_content(full_prompt)
                        response_text = response.text
                    except Exception as e:
                        response_text = f"AI 응답 생성 중 오류가 발생했습니다: {e}"
                    
                    st.markdown(response_text)
            
            # AI 응답 저장
            st.session_state.messages.append({"role": "assistant", "content": response_text})

if is_admin:
    admin_tab_index = 4
    with tab_list[admin_tab_index]: # 휴가 승인 관리
        st.header("🛠️ 휴가 승인 관리")
        pending_requests = vacations_df[vacations_df['status'] == '대기'].copy()
        
        if pending_requests.empty:
            st.info("승인 대기 중인 휴가 신청이 없습니다.")
        else:
            # 각 요청에 대한 승인/반려 버튼 생성
            for index, row in pending_requests.iterrows():
                st.subheader(f"신청자: {row['employee_name']}")
                st.write(f"기간: {row['start_date'].strftime('%Y-%m-%d')} ~ {row['end_date'].strftime('%Y-%m-%d')}")
                st.write(f"종류: {row['leave_type']}")
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("승인", key=f"approve_{index}"):
                        vacations_df.loc[index, 'status'] = '승인'
                        vacations_content, sha = get_github_file_content(VACATIONS_FILE_PATH)
                        updated_csv = vacations_df.to_csv(index=False, date_format='%Y-%m-%d')
                        if update_github_file(VACATIONS_FILE_PATH, updated_csv, sha, f"Approved request for {row['employee_name']}"):
                            st.success(f"{row['employee_name']}님의 휴가를 승인했습니다.")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("처리 중 오류가 발생했습니다.")
                
                with col2:
                    if st.button("반려", key=f"reject_{index}"):
                        vacations_df.loc[index, 'status'] = '반려'
                        vacations_content, sha = get_github_file_content(VACATIONS_FILE_PATH)
                        updated_csv = vacations_df.to_csv(index=False, date_format='%Y-%m-%d')
                        if update_github_file(VACATIONS_FILE_PATH, updated_csv, sha, f"Rejected request for {row['employee_name']}"):
                            st.warning(f"{row['employee_name']}님의 휴가를 반려했습니다.")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("처리 중 오류가 발생했습니다.")
                st.divider()

    with tab_list[admin_tab_index + 1]: # 직원 및 정책 관리
        st.header("⚙️ 직원 및 정책 관리")

        # 직원 관리
        st.subheader("직원 관리")
        st.dataframe(employees_df)
        with st.expander("직원 추가/삭제"):
            # 직원 추가
            with st.form("add_employee_form"):
                new_name = st.text_input("이름")
                new_days = st.number_input("총 연차일수", min_value=0, value=15)
                add_submitted = st.form_submit_button("추가")
                if add_submitted and new_name:
                    if new_name in employees_df['employee_name'].tolist():
                        st.error("이미 존재하는 직원입니다.")
                    else:
                        new_employee = pd.DataFrame([{'employee_name': new_name, 'total_leave_days': new_days}])
                        updated_df = pd.concat([employees_df, new_employee], ignore_index=True)
                        _, sha = get_github_file_content(EMPLOYEES_FILE_PATH)
                        if update_github_file(EMPLOYEES_FILE_PATH, updated_df.to_csv(index=False), sha, f"Add employee {new_name}"):
                            st.success(f"{new_name}님을 추가했습니다.")
                            st.cache_data.clear()
                            st.rerun()

            # 직원 삭제
            delete_name = st.selectbox("삭제할 직원 선택", options=[""] + employee_list)
            if st.button("삭제") and delete_name:
                updated_df = employees_df[employees_df['employee_name'] != delete_name]
                _, sha = get_github_file_content(EMPLOYEES_FILE_PATH)
                if update_github_file(EMPLOYEES_FILE_PATH, updated_df.to_csv(index=False), sha, f"Remove employee {delete_name}"):
                    st.success(f"{delete_name}님을 삭제했습니다.")
                    st.cache_data.clear()
                    st.rerun()

        st.divider()
        # 정책 관리
        st.subheader("정책 관리")
        # 일일 최대 인원
        new_limit = st.number_input("일일 최대 휴가 인원", min_value=1, value=config.get("daily_limit", 5))
        if st.button("최대 인원 설정 저장"):
            config['daily_limit'] = new_limit
            config_content, sha = get_github_file_content(CONFIG_FILE_PATH)
            if sha:
                update_github_file(CONFIG_FILE_PATH, json.dumps(config, indent=2), sha, "Update daily limit")
            else: # 파일이 없는 경우
                create_github_file(CONFIG_FILE_PATH, json.dumps(config, indent=2), "Create config file")
            st.success("설정이 저장되었습니다.")
            st.cache_data.clear()
            st.rerun()

        # 동시 휴가 불가
        st.subheader("동시 휴가 불가 인원 관리")
        st.dataframe(constraints_df)
        with st.expander("제약 조건 추가/삭제"):
            col1, col2 = st.columns(2)
            with col1:
                emp1 = st.selectbox("직원 1", options=employee_list, key="c1")
            with col2:
                emp2 = st.selectbox("직원 2", options=employee_list, key="c2")
            if st.button("제약 조건 추가") and emp1 != emp2:
                new_constraint = pd.DataFrame([{'employee_name_1': emp1, 'employee_name_2': emp2}])
                updated_df = pd.concat([constraints_df, new_constraint], ignore_index=True).drop_duplicates()
                _, sha = get_github_file_content(CONSTRAINTS_FILE_PATH)
                if sha:
                    update_github_file(CONSTRAINTS_FILE_PATH, updated_df.to_csv(index=False), sha, f"Add constraint between {emp1} and {emp2}")
                else:
                    create_github_file(CONSTRAINTS_FILE_PATH, updated_df.to_csv(index=False), f"Add constraint between {emp1} and {emp2}")
                st.success("제약 조건이 추가되었습니다.")
                st.cache_data.clear()
                st.rerun()

st.sidebar.info("비용 없는 운영을 위해 Streamlit Community Cloud에 배포하고, 비밀번호로 접근을 제어합니다.")
