import streamlit as st
import json
from datetime import datetime
from data_utils import (
    get_tushare_pro,
    validate_stock_code, 
    get_stock_name_by_code, 
    search_stocks, 
    get_clean_market_data, 
    get_clean_fundamental_data, 
    get_market_environment_data
)
from core_logic import call_deepseek_api, generate_analysis_prompt

def main():
    st.set_page_config(page_title="DeepSeek 股票分析", page_icon="📈", layout="wide")
    
    # === 检查配置 ===
    if not get_tushare_pro():
        st.error("🚨 未配置 Tushare Token，请在 Secrets 中配置 `TUSHARE_TOKEN`。")
        st.stop()
        
    st.title("📈 DeepSeek + Tushare 智能分析")
    st.info("💡 提示：A股数据通常免费；港股数据(.HK)需要 Tushare 2000+ 积分权限。")
    
    # Session State
    if 'target_code' not in st.session_state: st.session_state.target_code = ""
    if 'stock_name' not in st.session_state: st.session_state.stock_name = ""

    # === 侧边栏 ===
    st.sidebar.header("🔍 查询")
    search_mode = st.sidebar.radio("模式", ["输入代码", "名称搜索"])
    
    stock_code, stock_name = "", ""
    
    if search_mode == "输入代码":
        code_input = st.sidebar.text_input("代码 (支持A股/港股)", value=st.session_state.target_code, placeholder="例: 600519 或 00700")
        if code_input:
            is_valid, result = validate_stock_code(code_input)
            if is_valid:
                stock_code = result
                st.session_state.target_code = code_input
                with st.spinner("验证中..."):
                    stock_name = get_stock_name_by_code(stock_code)
                    st.session_state.stock_name = stock_name
                st.sidebar.success(f"✅ {stock_name} ({stock_code})")
            else:
                st.sidebar.error(result)
    else:
        keyword = st.sidebar.text_input("输入名称")
        if keyword:
            res = search_stocks(keyword)
            if res:
                opts = {f"{r['名称']} ({r['代码']}) - {r['类型']}": r['代码'] for r in res}
                sel = st.sidebar.selectbox("选择股票", list(opts.keys()))
                if sel:
                    stock_code = opts[sel]
                    stock_name = sel.split(' (')[0]
                    st.session_state.target_code = stock_code
                    st.session_state.stock_name = stock_name
            else:
                st.sidebar.warning("未找到结果")

    predict_cycle = st.sidebar.selectbox("周期", ["次日", "本周", "月度"])
    start_btn = st.sidebar.button("🚀 开始分析", type="primary", disabled=not stock_code)

    # === 主界面 ===
    if start_btn and stock_code:
        st.divider()
        st.header(f"{stock_name} ({stock_code})")
        
        with st.status("正在拉取数据...", expanded=True) as status:
            st.write("📥 获取行情...")
            daily_data = get_clean_market_data(stock_code)
            
            if "错误" in daily_data:
                status.update(label="❌ 数据获取失败", state="error")
                st.error(daily_data["错误"])
                if ".HK" in stock_code:
                    st.warning("⚠️ 提示：港股数据失败通常是因为 Tushare 积分不足 2000。")
                return

            st.write("📥 获取基本面...")
            fund_data = get_clean_fundamental_data(stock_code, daily_data)
            
            st.write("📥 获取市场环境...")
            mkt_data = get_market_environment_data(stock_code)
            
            status.update(label="✅ 数据就绪", state="complete")
        
        # 数据展示
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("收盘价", daily_data.get('收盘价'), daily_data.get('涨跌幅'))
            st.write(f"MACD: {daily_data.get('MACD')}")
        with c2:
            st.metric("PE(TTM)", fund_data.get('PE(TTM)'))
            st.write(f"RSI: {daily_data.get('RSI')}")
        with c3:
            st.metric("市场情绪", mkt_data.get('市场情绪'))
            st.write(f"指数涨跌: {mkt_data.get('市场指数涨跌幅')}")

        # AI 分析
        st.subheader("🤖 DeepSeek 分析")
        with st.spinner("AI 思考中..."):
            prompt = generate_analysis_prompt(stock_code, stock_name, predict_cycle, daily_data, fund_data, mkt_data)
            res = call_deepseek_api(prompt)
        
        if res.startswith("❌"): st.error(res)
        else: st.markdown(res)

if __name__ == "__main__":
    main()