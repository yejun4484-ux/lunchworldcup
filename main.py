import random
import uuid

import pandas as pd
import plotly.express as px
import streamlit as st
from supabase import create_client


# ==========================================
# 페이지 설정
# ==========================================
st.set_page_config(
    page_title="급식 반찬 월드컵",
    page_icon="🏆",
    layout="wide",
)

MENUS = [
    "제육볶음",
    "간장찜닭",
    "가자미순살튀김",
    "돈육불백",
    "미트볼데리야끼볶음",
    "수육",
    "진미채고추장볶음",
    "치즈떡닭갈비",
]

ROUND_NAMES = {
    0: "8강",
    1: "4강",
    2: "결승",
}


# ==========================================
# 세션 상태 초기화
# ==========================================
def init_state():
    defaults = {
        "game_id": None,
        "round_index": 0,
        "matches": [],
        "match_index": 0,
        "champion": None,
        "locked": False,
        "lock_message": "",
        "saved_count": 0,
        "round_winners": [],
        "analysis_refresh": 0,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


# ==========================================
# Supabase 연결
# ==========================================
def get_supabase():
    """비밀 금고에서 Supabase 접속 정보를 읽는다."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]

    return create_client(url, key)


# ==========================================
# 월드컵 시작
# ==========================================
def start_game():
    shuffled = MENUS.copy()
    random.shuffle(shuffled)

    st.session_state.game_id = str(uuid.uuid4())
    st.session_state.round_index = 0

    st.session_state.matches = [
        (shuffled[i], shuffled[i + 1])
        for i in range(0, 8, 2)
    ]

    st.session_state.match_index = 0
    st.session_state.champion = None
    st.session_state.locked = False
    st.session_state.lock_message = ""
    st.session_state.saved_count = 0
    st.session_state.round_winners = []


# ==========================================
# 대결 기록 저장
# ==========================================
def save_duel(left_menu, right_menu, winner, round_name):
    """대결 한 건을 저장하고 서버가 반환한 결과까지 확인한다."""

    if left_menu == right_menu:
        raise ValueError(
            "서로 다른 반찬끼리만 대결할 수 있습니다."
        )

    if winner not in (left_menu, right_menu):
        raise ValueError(
            "승자는 대결한 두 반찬 중 하나여야 합니다."
        )

    row = {
        "game_id": st.session_state.game_id,
        "round": round_name,
        "left_menu": left_menu,
        "right_menu": right_menu,
        "winner": winner,
    }

    # 기존 menu_duels 테이블에만 삽입한다.
    # 테이블 생성, 수정, 삭제는 하지 않는다.
    response = (
        get_supabase()
        .table("menu_duels")
        .insert(row)
        .select("game_id,round,left_menu,right_menu,winner")
        .execute()
    )

    data = getattr(response, "data", None)

    if not isinstance(data, list) or len(data) != 1:
        raise RuntimeError(
            "저장 결과를 확인할 수 없습니다. "
            "대결을 계속하지 않습니다."
        )

    saved = data[0]

    if any(saved.get(column) != row[column] for column in row):
        raise RuntimeError(
            "서버의 저장 결과가 선택 내용과 일치하지 않습니다. "
            "확인이 필요합니다."
        )

    return True


# ==========================================
# 다음 라운드 진행
# ==========================================
def advance_round(winner):
    """저장이 확인된 승자만 다음 라운드로 올린다."""

    current_round = st.session_state.round_index

    # 결승에서 이기면 우승 확정
    if current_round == 2:
        st.session_state.champion = winner
        return

    winners = st.session_state.round_winners
    winners.append(winner)

    # 현재 라운드의 대결이 모두 끝났는지 확인
    if (
        st.session_state.match_index + 1
        >= len(st.session_state.matches)
    ):
        st.session_state.round_index += 1

        # 해당 라운드에서 이긴 반찬끼리 다음 라운드 구성
        st.session_state.matches = [
            (winners[i], winners[i + 1])
            for i in range(0, len(winners), 2)
        ]

        st.session_state.match_index = 0
        st.session_state.round_winners = []

    else:
        st.session_state.match_index += 1


# ==========================================
# 승자 선택 및 저장 확인
# ==========================================
def choose_winner(winner):
    """저장 확인에 성공한 경우에만 다음 대결로 진행한다."""

    if (
        st.session_state.locked
        or st.session_state.champion is not None
    ):
        return

    left_menu, right_menu = st.session_state.matches[
        st.session_state.match_index
    ]

    round_name = ROUND_NAMES[
        st.session_state.round_index
    ]

    try:
        save_duel(
            left_menu,
            right_menu,
            winner,
            round_name,
        )

    except Exception as exc:
        st.session_state.locked = True

        st.session_state.lock_message = (
            "저장 결과를 확인하지 못했습니다. 안전을 위해 대결 진행과 "
            "재선택을 잠갔습니다. 교사가 Supabase의 menu_duels 기록과 "
            "접속 설정을 확인해야 합니다. 중복 저장 방지를 위해 이 판을 "
            "자동으로 재시도하지 않습니다. 자세한 오류: "
            + str(exc)
        )

        return

    # 저장 결과가 확인된 경우에만 진행
    st.session_state.saved_count += 1
    advance_round(winner)


# ==========================================
# 전체 대결 기록 불러오기
# ==========================================
def load_duel_records():
    """menu_duels의 지정된 여섯 열만 읽는다."""

    response = (
        get_supabase()
        .table("menu_duels")
        .select("id,game_id,round,left_menu,right_menu,winner")
        .execute()
    )

    data = getattr(response, "data", None)

    if not isinstance(data, list):
        raise RuntimeError(
            "Supabase 조회 결과를 읽을 수 없습니다."
        )

    return pd.DataFrame(
        data,
        columns=[
            "id",
            "game_id",
            "round",
            "left_menu",
            "right_menu",
            "winner",
        ],
    )


# ==========================================
# 반찬별 통계 계산
# ==========================================
def analyze_records(records):
    """후보별 대결 수, 승리 수, 승률, 우승 횟수를 계산한다."""

    # 기록이 없어도 모든 후보를 표시한다.
    stats = pd.DataFrame({"반찬": MENUS})

    stats["대결 수"] = 0
    stats["승리 수"] = 0
    stats["승률(%)"] = float("nan")
    stats["우승 횟수"] = 0

    if records.empty:
        return stats

    duel_counts = {}
    win_counts = {}
    champion_counts = {}

    for menu in MENUS:

        # 왼쪽과 오른쪽에 나온 횟수를 모두 계산
        duel_counts[menu] = int(
            (records["left_menu"] == menu).sum()
            + (records["right_menu"] == menu).sum()
        )

        # winner에 기록된 횟수
        win_counts[menu] = int(
            (records["winner"] == menu).sum()
        )

        # 결승전에서 이긴 횟수만 우승으로 계산
        champion_counts[menu] = int(
            (
                (records["round"] == "결승")
                & (records["winner"] == menu)
            ).sum()
        )

    stats["대결 수"] = (
        stats["반찬"].map(duel_counts).astype(int)
    )

    stats["승리 수"] = (
        stats["반찬"].map(win_counts).astype(int)
    )

    stats["우승 횟수"] = (
        stats["반찬"].map(champion_counts).astype(int)
    )

    # 대결 기록이 있는 반찬만 승률 계산
    played = stats["대결 수"] > 0

    stats.loc[played, "승률(%)"] = (
        stats.loc[played, "승리 수"]
        / stats.loc[played, "대결 수"]
        * 100
    )

    # 승률이 높은 순서로 정렬한다.
    # 기록이 없는 후보는 표 아래쪽에 표시한다.
    stats = stats.sort_values(
        by=["승률(%)", "승리 수", "대결 수"],
        ascending=[False, False, False],
        na_position="last",
        kind="stable",
    ).reset_index(drop=True)

    return stats


# ==========================================
# 학급 전체 기록 분석 화면
# ==========================================
def render_analysis():
    st.title("📊 학급 전체 반찬 대결 기록 분석")

    st.write(
        "월드컵 진행 중 남긴 대결을 포함해 menu_duels에 저장된 "
        "전체 대결 기록을 분석합니다."
    )

    if st.button(
        "🔄 분석 결과 다시 불러오기",
        type="primary",
    ):
        st.session_state.analysis_refresh += 1
        st.rerun()

    # 조회 실패와 기록 없음은 별도로 처리한다.
    try:
        records = load_duel_records()

    except Exception as exc:
        st.error(
            "대결 기록을 조회하지 못했습니다. Supabase 접속 정보, "
            "menu_duels 테이블 이름, SELECT 권한 및 RLS 정책을 확인해 주세요."
        )
        st.caption(f"오류 내용: {exc}")
        return

    # 조회는 성공했지만 기록이 없는 경우
    if records.empty:
        st.info(
            "아직 저장된 대결 기록이 없습니다. 월드컵에서 반찬을 선택하면 "
            "저장된 대결이 이 화면에 표시됩니다."
        )

        metric1, metric2 = st.columns(2)
        metric1.metric("집계에 사용한 대결 기록 수", 0)
        metric2.metric("집계에 사용한 판 수", 0)

        st.caption(
            "대결 기록 수와 참여 인원은 다릅니다. 진행 중에 남긴 대결도 "
            "집계 대상에 포함됩니다."
        )
        return

    # 전체 기록 수와 고유한 판 수
    record_count = len(records)
    game_count = (
        records["game_id"]
        .dropna()
        .astype(str)
        .nunique()
    )

    metric1, metric2 = st.columns(2)

    metric1.metric(
        "집계에 사용한 대결 기록 수",
        f"{record_count:,}건",
    )

    metric2.metric(
        "집계에 사용한 판 수",
        f"{game_count:,}판",
    )

    st.caption(
        "대결 기록 수와 참여 인원은 다릅니다. 한 판에서 남긴 여러 대결은 "
        "각각 기록으로 집계하며, 진행 중에 남긴 대결도 포함됩니다."
    )

    stats = analyze_records(records)

    # --------------------------------------
    # 통계 표
    # --------------------------------------
    st.subheader("반찬별 기록 비교")

    display_stats = stats.copy()

    display_stats["승률"] = display_stats["승률(%)"].map(
        lambda value: (
            "아직 알 수 없음"
            if pd.isna(value)
            else f"{value:.1f}%"
        )
    )

    display_stats = display_stats[
        [
            "반찬",
            "대결 수",
            "승리 수",
            "승률",
            "우승 횟수",
        ]
    ]

    st.dataframe(
        display_stats,
        hide_index=True,
        use_container_width=True,
    )

    # 대결 기록이 없는 반찬 안내
    no_games = stats.loc[
        stats["대결 수"] == 0,
        "반찬",
    ].tolist()

    if no_games:
        st.info(
            "대결 기록이 없는 반찬의 승률은 아직 알 수 없습니다: "
            + ", ".join(no_games)
        )

    # --------------------------------------
    # Plotly 가로 막대그래프
    # --------------------------------------
    st.subheader("반찬별 승률")

    chart_data = stats.dropna(
        subset=["승률(%)"]
    ).sort_values(
        "승률(%)",
        ascending=True,
    )

    if chart_data.empty:
        st.info(
            "승률을 계산할 수 있는 대결 기록이 아직 없습니다."
        )

    else:
        fig = px.bar(
            chart_data,
            x="승률(%)",
            y="반찬",
            orientation="h",
            text=chart_data["승률(%)"].map(
                lambda value: f"{value:.1f}%"
            ),
            hover_data={
                "대결 수": True,
                "승리 수": True,
                "우승 횟수": True,
                "승률(%)": ":.1f",
            },
            labels={
                "승률(%)": "승률 (%)",
                "반찬": "반찬",
                "대결 수": "대결 수",
                "승리 수": "승리 수",
                "우승 횟수": "우승 횟수",
            },
            title="대결 기록이 있는 반찬의 승률 비교",
        )

        fig.update_traces(
            textposition="outside",
            cliponaxis=False,
        )

        fig.update_layout(
            xaxis=dict(
                range=[0, 110],
                ticksuffix="%",
            ),
            yaxis_title="",
            margin=dict(
                l=10,
                r=30,
                t=60,
                b=20,
            ),
        )

        st.plotly_chart(
            fig,
            use_container_width=True,
        )

    st.caption(
        "대결 수는 left_menu와 right_menu에 등장한 횟수를 모두 합산합니다. "
        "승리 수는 winner에 기록된 횟수이며, 우승 횟수는 round가 '결승'인 "
        "행의 winner만 셉니다. 승률은 승리 수 ÷ 대결 수 × 100입니다."
    )


# ==========================================
# 화면 선택
# ==========================================
init_state()

page = st.sidebar.radio(
    "화면 선택",
    [
        "🏆 반찬 월드컵",
        "📊 학급 기록 분석",
    ],
)

# ==========================================
# 분석 화면
# ==========================================
if page == "📊 학급 기록 분석":

    render_analysis()

# ==========================================
# 월드컵 화면
# ==========================================
else:

    st.title("🏆 급식 반찬 월드컵")

    st.write(
        "8개의 반찬 중 가장 먹고 싶은 반찬을 골라 "
        "우승 반찬을 정해 보세요."
    )

    st.caption(
        "개인정보를 입력하지 않습니다. "
        "선택한 대결 결과만 저장됩니다."
    )

    # --------------------------------------
    # 시작 화면
    # --------------------------------------
    if not st.session_state.game_id:

        st.info(
            "새 판을 시작하면 후보 순서가 무작위로 섞입니다."
        )

        if st.button(
            "🎮 월드컵 시작하기",
            type="primary",
            use_container_width=True,
        ):
            start_game()
            st.rerun()

    # --------------------------------------
    # 저장 오류 화면
    # --------------------------------------
    elif st.session_state.locked:

        st.error(st.session_state.lock_message)

        st.warning(
            "이 판은 잠긴 상태입니다. 저장 여부를 확인하기 전에는 "
            "선택을 다시 누르거나 자동으로 이어서 진행할 수 없습니다."
        )

        if st.button(
            "새 판 시작",
            type="primary",
        ):
            start_game()
            st.rerun()

    # --------------------------------------
    # 우승 결과 화면
    # --------------------------------------
    elif st.session_state.champion:

        st.success("이번 급식 월드컵의 우승 반찬은…")

        st.markdown(
            f"""
            <div style="
                text-align: center;
                padding: 2rem;
                border-radius: 1rem;
                background: #fff3cd;
                color: #402d00;
                font-size: 2.2rem;
                font-weight: 800;
            ">
                🏆 {st.session_state.champion} 🏆
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.write(
            f"총 {st.session_state.saved_count}개의 "
            "대결 결과가 저장되었습니다."
        )

        if st.button(
            "🔄 다시 시작하기",
            type="primary",
            use_container_width=True,
        ):
            start_game()
            st.rerun()

    # --------------------------------------
    # 대결 화면
    # --------------------------------------
    else:

        round_index = st.session_state.round_index
        round_name = ROUND_NAMES[round_index]

        left_menu, right_menu = st.session_state.matches[
            st.session_state.match_index
        ]

        total_matches = (4, 2, 1)[round_index]
        match_number = st.session_state.match_index + 1

        st.subheader(
            f"{round_name} · "
            f"{match_number}/{total_matches}번째 대결"
        )

        st.progress(
            st.session_state.saved_count / 7
        )

        st.write(
            "둘 중 더 먹고 싶은 반찬 하나를 선택하세요."
        )

        col_left, col_vs, col_right = st.columns(
            [5, 1, 5],
            vertical_alignment="center",
        )

        # 왼쪽 반찬
        with col_left:

            st.markdown(
                f"""
                <div style="
                    border: 2px solid #e0e0e0;
                    border-radius: 18px;
                    padding: 28px 12px;
                    text-align: center;
                    min-height: 150px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                ">
                    <span style="
                        font-size: 1.5rem;
                        font-weight: 700;
                    ">
                        {left_menu}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(
                f"🍽️ {left_menu}",
                key=(
                    f"left_{st.session_state.game_id}_"
                    f"{round_index}_{match_number}"
                ),
                type="primary",
                use_container_width=True,
            ):
                choose_winner(left_menu)
                st.rerun()

        # VS 표시
        with col_vs:

            st.markdown(
                """
                <div style="
                    text-align: center;
                    font-size: 1.5rem;
                    font-weight: 800;
                ">
                    VS
                </div>
                """,
                unsafe_allow_html=True,
            )

        # 오른쪽 반찬
        with col_right:

            st.markdown(
                f"""
                <div style="
                    border: 2px solid #e0e0e0;
                    border-radius: 18px;
                    padding: 28px 12px;
                    text-align: center;
                    min-height: 150px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                ">
                    <span style="
                        font-size: 1.5rem;
                        font-weight: 700;
                    ">
                        {right_menu}
                    </span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(
                f"🍽️ {right_menu}",
                key=(
                    f"right_{st.session_state.game_id}_"
                    f"{round_index}_{match_number}"
                ),
                type="primary",
                use_container_width=True,
            ):
                choose_winner(right_menu)
                st.rerun()

        st.caption(
            "선택할 때마다 대결 결과가 Supabase에 저장된 뒤 "
            "다음 대결로 넘어갑니다."
        )
