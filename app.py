import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="SOXL 변동성 돌파 백테스트", layout="wide")
st.title("📈 SOXL 변동성 돌파 매매 백테스트")

# ---------------------------
# 사이드바: 파라미터 입력
# ---------------------------
st.sidebar.header("⚙️ 전략 파라미터")
breakout_pct = st.sidebar.slider("돌파율 (%)", 0.5, 10.0, 2.0, 0.1) / 100
stoploss_pct = st.sidebar.slider("손절율 (%)", 0.5, 10.0, 3.0, 0.1) / 100
fee_pct = st.sidebar.number_input("편도 수수료+슬리피지 (%)", value=0.05, step=0.01) / 100
initial_capital = st.sidebar.number_input("초기 자본금 ($)", value=10000, step=1000)

uploaded = st.file_uploader("1분봉 CSV 업로드 (헤더 없음)", type="csv")

COLS = ["datetime", "open", "high", "low", "close", "volume"]

# ---------------------------
# 백테스트 함수
# ---------------------------
def run_backtest(df, breakout_pct, stoploss_pct, fee_pct):
    df = df.sort_values("datetime").reset_index(drop=True)
    df["date"] = df["datetime"].dt.date
    df["time"] = df["datetime"].dt.strftime("%H:%M")

    dates = sorted(df["date"].unique())
    trades = []

    for i, d in enumerate(dates):
        day_df = df[df["date"] == d].sort_values("datetime").reset_index(drop=True)
        if day_df.empty:
            continue

        # 9:30 시가 찾기 (없으면 그날 첫 봉의 시가로 대체)
        open_row = day_df[day_df["time"] == "09:30"]
        day_open = open_row.iloc[0]["open"] if not open_row.empty else day_df.iloc[0]["open"]

        breakout_price = day_open * (1 + breakout_pct)

        # 돌파 시점 찾기 (9:30 이후 봉들 중 high가 돌파가 이상인 첫 봉)
        entry_idx = None
        for idx, row in day_df.iterrows():
            if row["time"] < "09:30":
                continue
            if row["high"] >= breakout_price:
                entry_idx = idx
                break

        if entry_idx is None:
            continue  # 돌파 없음 → 그날은 거래 없음

        entry_price = breakout_price
        entry_time = day_df.loc[entry_idx, "datetime"]
        stoploss_price = entry_price * (1 - stoploss_pct)

        exit_price = None
        exit_time = None
        exit_reason = None

        # 같은 날, 진입 이후 봉들에서 손절 체크
        for idx in range(entry_idx, len(day_df)):
            row = day_df.loc[idx]
            if row["low"] <= stoploss_price:
                exit_price = stoploss_price
                exit_time = row["datetime"]
                exit_reason = "손절"
                break

        # 당일 손절 안 걸렸으면 다음날 확인
        if exit_price is None:
            if i + 1 < len(dates):
                next_day_df = df[df["date"] == dates[i + 1]].sort_values("datetime").reset_index(drop=True)
                if not next_day_df.empty:
                    first_bar = next_day_df.iloc[0]
                    if first_bar["low"] <= stoploss_price:
                        # 다음날 갭다운 등으로 손절가 이하 시작/터치
                        exit_price = stoploss_price
                        exit_time = first_bar["datetime"]
                        exit_reason = "손절(익일)"
                    else:
                        # 손절 안 걸리면 익일 시가 매도
                        exit_price = first_bar["open"]
                        exit_time = first_bar["datetime"]
                        exit_reason = "익일시가매도"
            else:
                # 마지막 날인데 손절도 안 걸리고 다음날 데이터 없음 → 제외
                continue

        trades.append({
            "진입일": entry_time.date(),
            "진입시각": entry_time,
            "매수가": entry_price,
            "청산일": exit_time.date(),
            "청산시각": exit_time,
            "매도가": exit_price,
            "결과": exit_reason,
        })

    trades_df = pd.DataFrame(trades)
    if trades_df.empty:
        return trades_df, pd.DataFrame()

    # 수수료 반영 수익률
    trades_df["매수가(수수료포함)"] = trades_df["매수가"] * (1 + fee_pct)
    trades_df["매도가(수수료포함)"] = trades_df["매도가"] * (1 - fee_pct)
    trades_df["수익률(%)"] = (
        (trades_df["매도가(수수료포함)"] / trades_df["매수가(수수료포함)"]) - 1
    ) * 100

    # 복리 자본 곡선
    capital = initial_capital
    equity_curve = []
    for r in trades_df["수익률(%)"]:
        capital *= (1 + r / 100)
        equity_curve.append(capital)
    trades_df["누적자본"] = equity_curve

    return trades_df, trades_df

# ---------------------------
# 메인 실행부
# ---------------------------
if uploaded is not None:
    raw_df = pd.read_csv(uploaded, header=None, names=COLS)
    raw_df["datetime"] = pd.to_datetime(raw_df["datetime"])

    trades_df, _ = run_backtest(raw_df, breakout_pct, stoploss_pct, fee_pct)

    if trades_df.empty:
        st.warning("조건에 맞는 거래가 없습니다. 파라미터를 조정해보세요.")
    else:
        total_trades = len(trades_df)
        win_trades = (trades_df["수익률(%)"] > 0).sum()
        win_rate = win_trades / total_trades * 100
        final_capital = trades_df["누적자본"].iloc[-1]
        total_return = (final_capital / initial_capital - 1) * 100

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("총 거래 수", f"{total_trades}회")
        col2.metric("승률", f"{win_rate:.1f}%")
        col3.metric("최종 자본", f"${final_capital:,.0f}")
        col4.metric("총 수익률", f"{total_return:.1f}%")

        st.subheader("📊 자본 곡선")
        st.line_chart(trades_df.set_index("청산시각")["누적자본"])

        st.subheader("📋 거래 내역")
        st.dataframe(trades_df, use_container_width=True)

        csv_out = trades_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("거래 내역 CSV 다운로드", csv_out, "trades.csv", "text/csv")
else:
    st.info("1분봉 CSV 파일을 업로드해주세요. (컬럼 없이 datetime, open, high, low, close, volume 순서)")
