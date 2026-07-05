import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="SOXL 변동성 돌파 백테스트", layout="wide")
st.title("SOXL 변동성 돌파 매매 백테스트")

st.sidebar.header("전략 파라미터")
breakout_pct = st.sidebar.slider("돌파율 (%)", 0.5, 10.0, 2.0, 0.1) / 100
stoploss_pct = st.sidebar.slider("손절율 (%)", 0.5, 10.0, 3.0, 0.1) / 100
fee_pct = st.sidebar.number_input("편도 수수료+슬리피지 (%)", value=0.05, step=0.01) / 100
initial_capital = st.sidebar.number_input("초기 자본", value=10000000, step=1000000)
compare_mode = st.sidebar.checkbox("복리 vs 단리 비교", value=True)

uploaded = st.file_uploader("CSV 파일 업로드 (datetime, open, high, low, close, volume)", type="csv")

COLS = ["datetime", "open", "high", "low", "close", "volume"]

if uploaded is not None:
    raw_df = pd.read_csv(uploaded, header=None, names=COLS, skiprows=1)
    raw_df["datetime"] = pd.to_datetime(raw_df["datetime"])
    raw_df = raw_df.sort_values("datetime").reset_index(drop=True)
    raw_df["date"] = raw_df["datetime"].dt.date

    st.subheader("데이터 미리보기")
    st.dataframe(raw_df.head())

    dates = sorted(raw_df["date"].unique())

    trades = []

    for i in range(len(dates) - 1):
        today = dates[i]
        next_day = dates[i + 1]

        day_df = raw_df[raw_df["date"] == today].reset_index(drop=True)
        next_df = raw_df[raw_df["date"] == next_day].reset_index(drop=True)

        if len(day_df) == 0 or len(next_df) == 0:
            continue

        day_open = day_df.iloc[0]["open"]
        breakout_price = day_open * (1 + breakout_pct)

        buy_price = None
        buy_time = None
        stop_price = None
        sell_price = None
        sell_time = None
        exit_type = None

        for idx, row in day_df.iterrows():
            if buy_price is None:
                if row["high"] >= breakout_price:
                    buy_price = breakout_price
                    buy_time = row["datetime"]
                    stop_price = buy_price * (1 - stoploss_pct)
            else:
                if row["low"] <= stop_price:
                    sell_price = stop_price
                    sell_time = row["datetime"]
                    exit_type = "손절"
                    break

        if buy_price is None:
            continue

        if sell_price is None:
            sell_price = next_df.iloc[0]["open"]
            sell_time = next_df.iloc[0]["datetime"]
            exit_type = "익일시가청산"

        buy_price_fee = buy_price * (1 + fee_pct)
        sell_price_fee = sell_price * (1 - fee_pct)
        ret_pct = (sell_price_fee - buy_price_fee) / buy_price_fee

        trades.append({
            "매수일": today,
            "매수시간": buy_time,
            "매수가": buy_price,
            "매도시간": sell_time,
            "매도가": sell_price,
            "청산유형": exit_type,
            "수익률(%)": ret_pct * 100
        })

    if len(trades) == 0:
        st.warning("조건에 맞는 매매가 없습니다.")
    else:
        trade_df = pd.DataFrame(trades)

        capital_compound = initial_capital
        capital_simple = initial_capital
        equity_compound = [initial_capital]
        equity_simple = [initial_capital]

        for r in trade_df["수익률(%)"]:
            r_ratio = r / 100
            capital_compound = capital_compound * (1 + r_ratio)
            equity_compound.append(capital_compound)

            profit_simple = initial_capital * r_ratio
            capital_simple = capital_simple + profit_simple
            equity_simple.append(capital_simple)

        trade_df["복리자산"] = equity_compound[1:]
        trade_df["단리자산"] = equity_simple[1:]

        st.subheader("매매 내역")
        st.dataframe(trade_df)

        st.subheader("성과 요약")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("총 매매 횟수", len(trade_df))
        col2.metric("승률", f"{(trade_df['수익률(%)'] > 0).mean() * 100:.2f}%")
        col3.metric("복리 최종자산", f"{capital_compound:,.0f}")
        col4.metric("단리 최종자산", f"{capital_simple:,.0f}")

        st.subheader("자산 곡선")
        if compare_mode:
            chart_df = pd.DataFrame({
                "복리": equity_compound,
                "단리": equity_simple
            })
            st.line_chart(chart_df)
        else:
            st.line_chart(pd.DataFrame({"복리": equity_compound}))

        st.subheader("청산 유형별 통계")
        st.write(trade_df["청산유형"].value_counts())
else:
    st.info("CSV 파일을 업로드해주세요.")
