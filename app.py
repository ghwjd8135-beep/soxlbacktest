import streamlit as st
import pandas as pd
import numpy as np
from datetime import time

st.set_page_config(page_title="Hojay의 변동성돌파매매 과거추적", layout="wide")

st.title("📈 SOXL 변동성 돌파 매매 백테스트 (복리 + MDD + 매매로그)")

st.sidebar.header("⚙️ 전략 파라미터")
breakout_pct = st.sidebar.slider("돌파율 (%)", 0.5, 10.0, 2.0, 0.1) / 100
stoploss_pct = st.sidebar.slider("손절율 (%)", 0.5, 10.0, 3.0, 0.1) / 100
fee_pct = st.sidebar.number_input("편도 수수료+슬리피지 (%)", value=0.05, step=0.01) / 100
initial_capital = st.sidebar.number_input("초기 자본금 ($)", value=10000, step=1000)

uploaded = st.file_uploader("1분봉 CSV 업로드 (헤더 없음)", type="csv")

COLS = ["datetime", "open", "high", "low", "close", "volume"]
MARKET_OPEN = time(9, 30)
MARKET_CLOSE = time(16, 0)

if uploaded is not None:
    df = pd.read_csv(uploaded, header=None, names=COLS)
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime').reset_index(drop=True)
    df['date'] = df['datetime'].dt.date
    df['time'] = df['datetime'].dt.time
    df = df[(df['time'] >= MARKET_OPEN) & (df['time'] <= MARKET_CLOSE)]

    dates = sorted(df['date'].unique())

    capital = initial_capital
    trade_log = []
    equity_curve = []  # (날짜, 자본금)
    pending_entry = None  # {'entry_date','entry_time','entry_price'}

    for d in dates:
        day_data = df[df['date'] == d].reset_index(drop=True)
        if day_data.empty:
            continue

        day_open = day_data.iloc[0]['open']

        # 1) 전날 매수 후 손절 안 나가고 넘어온 포지션 -> 오늘 시가에 청산
        if pending_entry is not None:
            exit_price = day_open
            exit_time = day_data.iloc[0]['datetime']

            buy_eff = pending_entry['entry_price'] * (1 + fee_pct)
            sell_eff = exit_price * (1 - fee_pct)
            ret = sell_eff / buy_eff - 1
            capital = capital * (1 + ret)

            trade_log.append({
                "진입일": pending_entry['entry_date'],
                "진입시각": pending_entry['entry_time'],
                "진입가": round(pending_entry['entry_price'], 4),
                "청산일": d,
                "청산시각": exit_time,
                "청산가": round(exit_price, 4),
                "청산유형": "익일시가",
                "수익률(%)": round(ret * 100, 2),
                "자본금": round(capital, 2),
            })
            equity_curve.append((exit_time, capital))
            pending_entry = None

        # 2) 오늘 당일 신규 진입 체크
        breakout_price = day_open * (1 + breakout_pct)
        entry_price = None
        entry_time = None
        stop_price = None
        exited_today = False

        for _, row in day_data.iterrows():
            if entry_price is None:
                if row['high'] >= breakout_price:
                    entry_price = breakout_price
                    entry_time = row['datetime']
                    stop_price = entry_price * (1 - stoploss_pct)
                    # 매수 체결된 바로 그 봉에서도 손절 체크 (버그 수정 유지)
                    if row['low'] <= stop_price:
                        exit_price = stop_price
                        exit_time = row['datetime']
                        exited_today = True
                        break
            else:
                if row['low'] <= stop_price:
                    exit_price = stop_price
                    exit_time = row['datetime']
                    exited_today = True
                    break

        if entry_price is not None and exited_today:
            buy_eff = entry_price * (1 + fee_pct)
            sell_eff = exit_price * (1 - fee_pct)
            ret = sell_eff / buy_eff - 1
            capital = capital * (1 + ret)

            trade_log.append({
                "진입일": d,
                "진입시각": entry_time,
                "진입가": round(entry_price, 4),
                "청산일": d,
                "청산시각": exit_time,
                "청산가": round(exit_price, 4),
                "청산유형": "손절",
                "수익률(%)": round(ret * 100, 2),
                "자본금": round(capital, 2),
            })
            equity_curve.append((exit_time, capital))

        elif entry_price is not None and not exited_today:
            pending_entry = {
                "entry_date": d,
                "entry_time": entry_time,
                "entry_price": entry_price,
            }
        # entry_price is None -> 오늘 매매 없음

    # 백테스트 종료 시점에 미청산 포지션이 남아있으면 안내만
    if pending_entry is not None:
        st.warning(
            f"⚠️ 마지막 포지션이 청산되지 않았습니다 "
            f"(진입일: {pending_entry['entry_date']}, 진입가: {pending_entry['entry_price']:.4f}). "
            f"통계 계산에서는 제외했습니다."
        )

    if len(trade_log) == 0:
        st.info("조건에 맞는 매매가 없습니다.")
    else:
        log_df = pd.DataFrame(trade_log)
        equity_df = pd.DataFrame(equity_curve, columns=["일시", "자본금"])

        # MDD 계산
        equity_df["누적최고"] = equity_df["자본금"].cummax()
        equity_df["drawdown"] = (equity_df["자본금"] - equity_df["누적최고"]) / equity_df["누적최고"]
        mdd = equity_df["drawdown"].min()

        total_return = (capital / initial_capital - 1) * 100
        win_trades = (log_df["수익률(%)"] > 0).sum()
        win_rate = win_trades / len(log_df) * 100
        stoploss_count = (log_df["청산유형"] == "손절").sum()
        overnight_count = (log_df["청산유형"] == "익일시가").sum()

        st.subheader("📊 백테스트 요약")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("최종 자본금", f"${capital:,.0f}")
        c2.metric("총 수익률", f"{total_return:.2f}%")
        c3.metric("MDD", f"{mdd*100:.2f}%")
        c4.metric("승률", f"{win_rate:.1f}%")
        c5.metric("총 매매횟수", f"{len(log_df)} (손절 {stoploss_count} / 익일 {overnight_count})")

        st.subheader("📉 자본금 곡선 & Drawdown")
        st.line_chart(equity_df.set_index("일시")[["자본금"]])
        st.line_chart(equity_df.set_index("일시")[["drawdown"]])

        st.subheader("📋 전체 매매 로그")
        st.dataframe(log_df, use_container_width=True)

        csv = log_df.to_csv(index=False).encode("utf-8-sig")
        st.download_button("매매 로그 CSV 다운로드", csv, "trade_log.csv", "text/csv")
