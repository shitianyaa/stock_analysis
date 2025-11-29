import streamlit as st
import pandas as pd
from datetime import datetime
import time

# 引入原有逻辑
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

# ===================== 1. 页面基础配置 =====================
st.set_page_config(
    page_title="DeepSeek 智能投研",
    page_icon="📈", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ===================== 2. 密码验证模块 =====================
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    st.markdown("""
    <style>
        .stTextInput input { text-align: center; font-size: 1.2rem; }
        .login-container { max-width: 400px; margin: 100px auto; text-align: center; }
        .lock-icon { font-size: 5rem; margin-bottom: 20px; }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("<div style='text-align:center; margin-top:50px;'>", unsafe_allow_html=True)
        st.markdown("<div class='lock-icon'>🔒</div>", unsafe_allow_html=True)
        st.markdown("<h2>系统已锁定</h2>", unsafe_allow_html=True)
        
        password_input = st.text_input("Password", type="password", label_visibility="collapsed")
        
        if password_input:
            correct_password = st.secrets.get("APP_PASSWORD", "")
            if password_input == correct_password:
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("❌ 密码错误")
        st.markdown("</div>", unsafe_allow_html=True)
    return False

# ===================== 3. 主程序逻辑 =====================

def run_app():
    # === 初始化 Session State (用于存储历史记录) ===
    if 'history_data' not in st.session_state:
        st.session_state.history_data = []

    # === CSS 深度美化 ===
    st.markdown("""
    <style>
        /* 全局字体优化 */
        html, body, [class*="css"] {
            font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif;
        }
        
        /* 侧边栏样式 */
        [data-testid="stSidebar"] {
            background-color: #f8f9fa;
            border-right: 1px solid #eee;
        }
        [data-testid="stSidebar"] * {
            color: #333333 !important;
        }

        /* --- 首页 (Landing Page) --- */
        .landing-header {
            background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
            padding: 4rem 2rem;
            border-radius: 20px;
            color: white;
            text-align: center;
            margin-bottom: 3rem;
            box-shadow: 0 10px 30px rgba(30, 60, 114, 0.2);
        }
        .landing-header h1 {
            color: white !important;
            font-size: 3rem;
            font-weight: 800;
            letter-spacing: -1px;
            margin-bottom: 1rem;
        }
        .landing-header p {
            font-size: 1.2rem;
            opacity: 0.9;
            font-weight: 300;
            color: rgba(255,255,255,0.9) !important;
            max-width: 600px;
            margin: 0 auto;
        }
        
        /* 功能特性卡片 */
        .feature-card {
            background-color: white;
            padding: 2rem;
            border-radius: 15px;
            text-align: center;
            border: 1px solid #f0f0f0;
            box-shadow: 0 4px 6px rgba(0,0,0,0.02);
            transition: all 0.3s ease;
            height: 100%;
        }
        .feature-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.08);
            border-color: #e0e0e0;
        }
        .feature-icon {
            font-size: 2.5rem;
            margin-bottom: 1rem;
            display: inline-block;
            background: #f0f4f8;
            width: 80px;
            height: 80px;
            line-height: 80px;
            border-radius: 50%;
        }
        .feature-title {
            font-size: 1.1rem;
            font-weight: 700;
            color: #2c3e50;
            margin-bottom: 0.5rem;
        }
        .feature-desc {
            font-size: 0.9rem;
            color: #666;
            line-height: 1.6;
        }

        /* --- 仪表盘 (Dashboard) --- */
        .main-header {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            border: 1px solid #eee;
            margin-bottom: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        /* 数据卡片 */
        .data-card {
            background: white;
            padding: 1.5rem;
            border-radius: 12px;
            border: 1px solid #f0f0f0;
            box-shadow: 0 2px 8px rgba(0,0,0,0.04);
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }
        .card-title { color: #888; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
        .card-value { color: #2c3e50; font-size: 1.8rem; font-weight: 700; margin: 5px 0; }
        .up-text { color: #d93025; font-size: 0.9rem; font-weight: 500; }
        .down-text { color: #1e8e3e; font-size: 0.9rem; font-weight: 500; }
        
        /* 按钮样式修复 */
        div.stButton > button {
            background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
            color: #ffffff !important; 
            border: none;
            padding: 0.6rem 1.2rem;
            border-radius: 8px;
            font-weight: 600;
            width: 100%;
            transition: all 0.3s;
            box-shadow: 0 4px 6px rgba(30, 60, 114, 0.2);
        }
        div.stButton > button p {
            color: #ffffff !important; 
        }
        div.stButton > button:hover {
            background: linear-gradient(90deg, #2a5298 0%, #1e3c72 100%);
            box-shadow: 0 6px 12px rgba(30, 60, 114, 0.3);
            transform: translateY(-1px);
            color: #ffffff !important;
        }
        
        /* 技术指标行 */
        .tech-row {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px dashed #eee;
            font-size: 0.9rem;
        }
        .tech-label { color: #666; }
        .tech-val { font-weight: 600; color: #333; }
        
        /* AI 报告框 */
        .ai-box {
            background: #ffffff;
            border-radius: 16px;
            padding: 2.5rem;
            border: 1px solid #eef0f5;
            box-shadow: 0 10px 30px rgba(0,0,0,0.05);
            margin-top: 2rem;
            border-top: 4px solid #1e3c72;
        }
    </style>
    """, unsafe_allow_html=True)

    # ===================== 辅助函数 =====================

    def render_data_card(title_en, title_cn, value, sub_info=None, trend=None):
        """渲染带中文标注的宽敞卡片"""
        trend_html = ""
        if trend == "up":
            trend_html = f"<span class='up-text'>▲ {sub_info}</span>"
        elif trend == "down":
            trend_html = f"<span class='down-text'>▼ {sub_info}</span>"
        elif sub_info:
            trend_html = f"<span style='color:#999; font-size:0.9rem;'>{sub_info}</span>"
            
        st.markdown(f"""
        <div class="data-card">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="card-title">{title_en}</span>
                <span style="font-size:0.75rem; background:#f5f5f5; padding:2px 6px; border-radius:4px; color:#666;">{title_cn}</span>
            </div>
            <div class="card-value">{value}</div>
            <div>{trend_html}</div>
        </div>
        """, unsafe_allow_html=True)

    def show_landing_page():
        """显示高级感首页"""
        st.markdown("""
        <div class="landing-header">
            <h1>DeepSeek 智能投研系统</h1>
            <p>融合 Tushare 金融大数据与 DeepSeek V3 深度推理模型<br>为您提供机构级的量化分析视角</p>
        </div>
        """, unsafe_allow_html=True)

        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            st.markdown("""
            <div style="text-align: center; margin-bottom: 4rem; padding: 20px; background: #fff; border-radius: 12px; border: 1px dashed #ddd;">
                <h3 style="color: #333; margin-bottom: 10px;">🚀 开启分析之旅</h3>
                <p style="color: #666; margin-bottom: 0;">请点击左上角 <b>></b> 展开侧边栏，输入股票代码（如 600519）即可生成报告。</p>
            </div>
            """, unsafe_allow_html=True)

        f1, f2, f3, f4 = st.columns(4, gap="medium")
        with f1: st.markdown("""<div class="feature-card"><div class="feature-icon">📡</div><div class="feature-title">实时行情接入</div><div class="feature-desc">直连交易所数据源，毫秒级获取最新价格、成交量与盘口动态。</div></div>""", unsafe_allow_html=True)
        with f2: st.markdown("""<div class="feature-card"><div class="feature-icon">🧠</div><div class="feature-title">AI 深度推理</div><div class="feature-desc">基于 DeepSeek V3 大模型，模拟资深分析师逻辑进行多维度拆解。</div></div>""", unsafe_allow_html=True)
        with f3: st.markdown("""<div class="feature-card"><div class="feature-icon">📊</div><div class="feature-title">量化估值模型</div><div class="feature-desc">自动计算 PE/PB 分位、波动率及技术指标，辅助价值判断。</div></div>""", unsafe_allow_html=True)
        with f4: st.markdown("""<div class="feature-card"><div class="feature-icon">🌍</div><div class="feature-title">宏观情绪扫描</div><div class="feature-desc">结合大盘指数与资金流向，精准捕捉市场情绪与系统性风险。</div></div>""", unsafe_allow_html=True)

        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown("<div style='text-align:center; color:#ccc; font-size:0.8rem;'>Powered by DeepSeek & Tushare Pro</div>", unsafe_allow_html=True)

    # ===================== 业务逻辑 =====================

    if not get_tushare_pro():
        st.error("🚨 系统配置错误: 未找到 Tushare Token")
        st.stop()

    if 'target_code' not in st.session_state: st.session_state.target_code = ""
    if 'stock_name' not in st.session_state: st.session_state.stock_name = ""

    # --- 侧边栏 ---
    with st.sidebar:
        st.markdown("### 🔍 股票检索")
        search_mode = st.radio("查询模式", ["输入代码", "名称搜索"], horizontal=True)
        
        stock_code = ""
        stock_name = ""
        
        if search_mode == "输入代码":
            code_input = st.text_input("代码", value=st.session_state.target_code, placeholder="如: 600519")
            if code_input:
                is_valid, result = validate_stock_code(code_input)
                if is_valid:
                    stock_code = result
                    st.session_state.target_code = code_input
                    with st.spinner("验证中..."):
                        fetched_name = get_stock_name_by_code(stock_code)
                        st.session_state.stock_name = fetched_name
                        stock_name = fetched_name
                    st.success(f"已锁定: {stock_name}")
                else:
                    st.error(result)
        else:
            keyword = st.text_input("名称", placeholder="如: 腾讯控股")
            if keyword:
                res = search_stocks(keyword)
                if res:
                    opts = {f"{r['名称']} ({r['代码']})": r['代码'] for r in res}
                    sel = st.selectbox("结果", list(opts.keys()))
                    if sel:
                        stock_code = opts[sel]
                        stock_name = sel.split(' (')[0]
                        st.session_state.target_code = stock_code
                        st.session_state.stock_name = stock_name
        
        st.markdown("---")
        predict_cycle = st.selectbox("周期", ["次日波动", "本周趋势", "月度展望"])
        st.markdown("<br>", unsafe_allow_html=True)
        analyze_btn = st.button("🚀 生成投研报告", type="primary")

    # --- 主视图 ---
    if not analyze_btn or not stock_code:
        # 如果有历史数据，展示历史数据，否则展示首页
        if not st.session_state.history_data:
            show_landing_page()
    else:
        # 1. 顶部 Header
        st.markdown(f"""
        <div class="main-header">
            <div>
                <h1 style="margin:0; font-size:1.8rem; color:#1e3c72;">{stock_name}</h1>
                <div style="color:#888; font-size:0.9rem; margin-top:4px;">股票代码: {stock_code}</div>
            </div>
            <div style="text-align:right;">
                <div style="font-weight:bold; color:#333;">DeepSeek 量化分析</div>
                <div style="color:#999; font-size:0.8rem;">{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # 数据加载
        with st.status("🔄 正在构建多因子分析模型...", expanded=True) as status:
            daily_data = get_clean_market_data(stock_code)
            if "错误" in daily_data:
                status.update(label="❌ 失败", state="error")
                st.error(daily_data["错误"])
                return
            fund_data = get_clean_fundamental_data(stock_code, daily_data)
            mkt_data = get_market_environment_data(stock_code)
            status.update(label="✅ 数据获取完成", state="complete")
            time.sleep(0.5)

        # === 核心逻辑：保存历史记录 ===
        # 创建一条记录
        new_record = {
            "分析时间": datetime.now().strftime('%m-%d %H:%M'),
            "代码": stock_code,
            "名称": stock_name,
            "最新价": daily_data.get('收盘价'),
            "涨跌幅": daily_data.get('涨跌幅'),
            "换手率": daily_data.get('换手率'),
            "PE(TTM)": fund_data.get('PE(TTM)'),
            "市场情绪": mkt_data.get('市场情绪'),
            "AI预测周期": predict_cycle
        }
        
        # 避免重复添加（简单的去重逻辑：如果最后一条记录和当前一样，就不加）
        if not st.session_state.history_data or st.session_state.history_data[0]["代码"] != stock_code:
            st.session_state.history_data.insert(0, new_record) # 插入到最前面

        # 2. 核心指标区
        st.markdown("### 📈 核心概览")
        c1, c2, c3, c4 = st.columns(4, gap="large")
        
        pchg = daily_data.get('涨跌幅', '0%')
        trend = "neutral"
        if '-' in pchg: trend = "down"
        elif pchg != '0.00%': trend = "up"

        with c1: render_data_card("Close", "最新收盘", daily_data.get('收盘价'), pchg, trend)
        with c2: render_data_card("Volume", "成交量", daily_data.get('成交量'), f"换手率: {daily_data.get('换手率')}")
        with c3: render_data_card("PE (TTM)", "滚动市盈率", fund_data.get('PE(TTM)'), f"PB (市净率): {fund_data.get('PB')}")
        with c4: render_data_card("Volatility", "年化波动率", daily_data.get('波动率'), "20日标准差")

        st.markdown("<br>", unsafe_allow_html=True)

        # 3. 详细指标面板
        col_tech, col_market = st.columns([2, 1], gap="large")
        
        with col_tech:
            st.markdown("### 🛠 技术指标监控")
            st.markdown("""
            <div style="background:white; padding:20px; border-radius:12px; border:1px solid #f0f0f0; box-shadow:0 2px 8px rgba(0,0,0,0.02);">
                <div style="display:grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px;">
                    <div>
                        <div style="color:#1e3c72; font-weight:bold; margin-bottom:10px; border-bottom:2px solid #f0f0f0; padding-bottom:5px;">均线系统</div>
                        <div class="tech-row"><span class="tech-label">MA5 (短期)</span> <span class="tech-val">{0}</span></div>
                        <div class="tech-row"><span class="tech-label">MA10 (支撑)</span> <span class="tech-val">{1}</span></div>
                        <div class="tech-row"><span class="tech-label">MA20 (趋势)</span> <span class="tech-val">{2}</span></div>
                    </div>
                    <div>
                        <div style="color:#764ba2; font-weight:bold; margin-bottom:10px; border-bottom:2px solid #f0f0f0; padding-bottom:5px;">震荡指标</div>
                        <div class="tech-row"><span class="tech-label">MACD</span> <span class="tech-val">{3}</span></div>
                        <div class="tech-row"><span class="tech-label">RSI (强弱)</span> <span class="tech-val">{4}</span></div>
                        <div class="tech-row"><span class="tech-label">趋势信号</span> <span class="tech-val">{5}</span></div>
                    </div>
                    <div>
                        <div style="color:#d93025; font-weight:bold; margin-bottom:10px; border-bottom:2px solid #f0f0f0; padding-bottom:5px;">布林通道</div>
                        <div class="tech-row"><span class="tech-label">上轨 (压力)</span> <span class="tech-val">{6}</span></div>
                        <div class="tech-row"><span class="tech-label">中轨 (均价)</span> <span class="tech-val">{7}</span></div>
                        <div class="tech-row"><span class="tech-label">下轨 (支撑)</span> <span class="tech-val">{8}</span></div>
                    </div>
                </div>
            </div>
            """.format(
                daily_data.get('5日均线'), daily_data.get('10日均线'), daily_data.get('20日均线'),
                daily_data.get('MACD'), daily_data.get('RSI'), "多头" if trend=="up" else "空头",
                daily_data.get('布林上轨'), daily_data.get('布林中轨'), daily_data.get('布林下轨')
            ), unsafe_allow_html=True)

        with col_market:
            st.markdown("### 🌍 市场罗盘")
            sent = mkt_data.get('市场情绪')
            bg_color = "#f8f9fa"
            text_color = "#333"
            if sent == "乐观": 
                bg_color = "linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 100%)" 
                text_color = "#00695c"
            elif sent == "悲观": 
                bg_color = "linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%)" 
                text_color = "#c62828"
            
            st.markdown(f"""
            <div style="background:{bg_color}; padding:25px; border-radius:12px; text-align:center; color:{text_color}; border:1px solid rgba(0,0,0,0.05);">
                <div style="font-size:0.9rem; opacity:0.8;">当前市场情绪</div>
                <div style="font-size:2.2rem; font-weight:800; margin:5px 0;">{sent}</div>
                <div style="font-size:1rem; border-top:1px solid rgba(0,0,0,0.1); padding-top:10px; margin-top:10px;">
                    参考指数: <b>{mkt_data.get('市场指数涨跌幅')}</b>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown(f"""
            <div style="margin-top:15px; padding:15px; background:white; border-radius:12px; border:1px solid #eee; font-size:0.9rem;">
                <div style="display:flex; justify-content:space-between; margin-bottom:8px;">
                    <span style="color:#888;">所属行业</span>
                    <span style="font-weight:600;">{fund_data.get('所属行业')}</span>
                </div>
                <div style="display:flex; justify-content:space-between;">
                    <span style="color:#888;">总市值</span>
                    <span style="font-weight:600;">{fund_data.get('总市值')}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # 4. AI 报告
        st.markdown(f"""
        <div class="ai-box">
            <div style="display:flex; align-items:center; gap:15px; margin-bottom:2rem; padding-bottom:1.5rem; border-bottom:1px solid #eee;">
                <div style="background:#e3f2fd; padding:10px; border-radius:50%; font-size:1.5rem;">🤖</div>
                <div>
                    <h3 style="margin:0; color:#1e3c72;">DeepSeek 深度研报</h3>
                    <span style="font-size:0.9rem; color:#888;">基于 {predict_cycle} 的多因子量化推理模型</span>
                </div>
            </div>
        """, unsafe_allow_html=True)

        with st.spinner("🧠 DeepSeek 正在思考策略..."):
            prompt = generate_analysis_prompt(stock_code, stock_name, predict_cycle, daily_data, fund_data, mkt_data)
            res = call_deepseek_api(prompt)
        
        if res.startswith("❌"):
            st.error(res)
        else:
            st.markdown(res)
            st.markdown(f"""
            <div style="text-align:right; margin-top:30px; padding-top:20px; border-top:1px dashed #eee; color:#ccc; font-size:0.8rem;">
                生成 ID: {datetime.now().strftime('%Y%m%d%H%M%S')} | 数据来源: Tushare Pro | 模型: DeepSeek-V3
            </div>
            """, unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # ===================== 历史记录与对比区 (新增) =====================
    if st.session_state.history_data:
        st.markdown("<br><hr><br>", unsafe_allow_html=True)
        
        with st.expander("📜 历史分析记录与对比 (点击展开)", expanded=True):
            # 将列表转换为 DataFrame
            df_history = pd.DataFrame(st.session_state.history_data)
            
            # 显示数据表
            st.dataframe(
                df_history,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "涨跌幅": st.column_config.TextColumn("涨跌幅", help="当日涨跌幅"),
                    "PE(TTM)": st.column_config.TextColumn("PE", help="滚动市盈率"),
                }
            )
            
            # 操作区
            col_d1, col_d2 = st.columns([1, 5])
            with col_d1:
                # 转换 CSV
                csv = df_history.to_csv(index=False).encode('utf-8-sig') # 使用 utf-8-sig 解决 Excel 中文乱码
                st.download_button(
                    label="📥 下载数据 (CSV)",
                    data=csv,
                    file_name=f"deepseek_analysis_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv"
                )
            with col_d2:
                if st.button("🗑️ 清空记录"):
                    st.session_state.history_data = []
                    st.rerun()

# ===================== 4. 程序入口 =====================
if __name__ == "__main__":
    if check_password():
        run_app()