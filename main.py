import random
import uuid

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
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


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


def get_supabase():
    """비밀 금고에서 Supabase 접속 정보를 읽는다."""
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]

    return create_client(url, key)


def save_duel(left_menu, right_menu, winner, round_name):
    """대결 결과를 저장하고 서버가 반환한 값을 확인한다."""

    if left_menu == right_menu:
        raise ValueError(
            "서로 다른 반찬끼리만 대결할 수 있습니다."
        )

    if winner not in (left_menu, right_menu):
        raise ValueError(
            "승자는 대결한 두 반찬 중 하나여야 합니다."
        )

    client = get_supabase()

    row = {
        "game_id": st.session_state.game_id,
        "round": round_name,
        "left_menu": left_menu,
        "right_menu": right_menu,
        "winner": winner,
    }

    # 기존 menu_duels 테이블에 한 행을 저장한다.
    # 저장된 행의 내용을 반환받아 실제 결과를 확인한다.
    response = (
        client.table("menu_duels")
        .insert(row)
        .select("game_id,round,left_menu,right_menu,winner")
        .execute()
    )

    data = getattr(response, "data", None)

    # 저장 결과를 확인할 수 없으면 성공으로 처리하지 않는다.
    if not isinstance(data, list) or len(data) != 1:
        raise RuntimeError(
            "저장 결과를 확인할 수 없습니다. "
            "대결을 계속하지 않습니다."
        )

    saved = data[0]

    expected = (
        "game_id",
        "round",
        "left_menu",
        "right_menu",
        "winner",
    )

    # 서버가 반환한 값이 실제 선택 내용과 일치하는지 확인한다.
    if any(saved.get(column) != row[column] for column in expected):
        raise RuntimeError(
            "서버의 저장 결과가 선택 내용과 일치하지 않습니다. "
            "확인이 필요합니다."
        )

    return True


def advance_round(winner):
    """저장이 확인된 승자만 다음 라운드로 올린다."""

    current_round = st.session_state.round_index

    # 결승에서 이기면 우승 확정
    if current_round == 2:
        st.session_state.champion = winner
        return

    winners = st.session_state.get("round_winners", [])
    winners.append(winner)
    st.session_state.round_winners = winners

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


def choose_winner(winner):
    """승자를 저장하고, 저장 확인 후에만 다음 대결로 이동한다."""

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

    # 저장이 확인되기 전에는 다음 대결로 진행하지 않는다.
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
            "저장 결과를 확인하지 못했습니다. "
            "안전하게 대결 진행과 재선택을 잠갔습니다. "
            "교사가 Supabase의 menu_duels 기록과 "
            "접속 설정을 확인해야 합니다. "
            "중복 저장 방지를 위해 이 판을 자동으로 "
            "재시도하지 않습니다. 자세한 오류: "
            + str(exc)
        )

        return

    # 저장 결과가 확인된 경우에만 진행
    st.session_state.saved_count += 1
    advance_round(winner)


# ==========================================
# 앱 실행
# ==========================================
init_state()

st.title("🏆 급식 반찬 월드컵")

st.write(
    "8개의 반찬 중 가장 먹고 싶은 반찬을 골라 "
    "우승 반찬을 정해 보세요."
)

st.caption(
    "개인정보를 입력하지 않습니다. "
    "선택한 대결 결과만 저장됩니다."
)


# ==========================================
# 시작 화면
# ==========================================
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


# ==========================================
# 저장 오류 화면
# ==========================================
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


# ==========================================
# 우승 결과 화면
# ==========================================
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


# ==========================================
# 토너먼트 대결 화면
# ==========================================
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
