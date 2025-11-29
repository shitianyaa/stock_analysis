import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import os
import re
import streamlit as st
import time

# ===================== 核心工具 =====================

def get_tushare_pro():
    """获取 Tushare Pro 接口客户端"""
    try:
        # 优先读取 Streamlit Secrets
        if hasattr(st, 'secrets') and 'TUSHARE_TOKEN' in st.secrets:
            token = st.secrets['TUSHARE_TOKEN']
        else:
            token = os.getenv("TUSHARE_TOKEN", "")
        
        if not token:
            print("❌ Token未配置")
            return None
            
        ts.set_token(token)
        return ts.pro_api()
    except Exception as e:
        print(f"❌ Token初始化失败: {e}")
        return None

def validate_stock_code(code):
    """验证并格式化代码"""
    clean_code = re.sub(r'[^\d]', '', str(code))
    if len(clean_code) == 5: return True, clean_code + ".HK"
    if len(clean_code) == 6:
        if clean_code.startswith('6'): suffix = ".SH"
        elif clean_code.startswith(('0', '3')): suffix = ".SZ"
        elif clean_code.startswith(('8', '4')): suffix = ".BJ"
        else: return False, "未知前缀"
        return True, clean_code + suffix
    return False, "代码格式错误"

def get_stock_name_by_code(ts_code):
    """获取名称 (带缓存思想的简化版)"""
    pro = get_tushare_pro()
    if not pro: return "未连接"
    try:
        if ts_code.endswith('.HK'):
            df = pro.hk_basic(ts_code=ts_code)
        else:
            df = pro.stock_basic(ts_code=ts_code)
        if not df.empty: return df.iloc[0]['name']
    except: pass
    return ts_code # 如果获取失败直接返回代码，不返回“未知”

def search_stocks(keyword):
    """搜索功能"""
    pro = get_tushare_pro()
    if not pro: return []
    results = []
    try:
        # A股
        df_a = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name')
        if not df_a.empty:
            mask = df_a["name"].str.contains(keyword, na=False) | df_a["ts_code"].str.contains(keyword, na=False)
            results.extend([{"代码": r['ts_code'], "名称": r['name'], "类型": "A股"} for _, r in df_a[mask].head(5).iterrows()])
        # 港股
        try:
            df_hk = pro.hk_basic(list_status='L', fields='ts_code,name')
            if not df_hk.empty:
                mask_hk = df_hk["name"].str.contains(keyword, na=False) | df_hk["ts_code"].str.contains(keyword, na=False)
                results.extend([{"代码": r['ts_code'], "名称": r['name'], "类型": "港股"} for _, r in df_hk[mask_hk].head(5).iterrows()])
        except: pass
        return results[:10]
    except: return []

# ===================== 技术指标计算 =====================

def get_enhanced_technical_indicators(df):
    try:
        if df.empty: return df
        df = df.sort_values('trade_date').reset_index(drop=True)
        close = df['close']
        
        # 均线
        df['ma5'] = close.rolling(5).mean()
        df['ma10'] = close.rolling(10).mean()
        df['ma20'] = close.rolling(20).mean()
        
        # MACD
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        df['dif'] = exp1 - exp2
        df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
        df['macd'] = (df['dif'] - df['dea']) * 2
        
        # RSI
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 布林带
        df['bb_middle'] = close.rolling(20).mean()
        std = close.rolling(20).std()
        df['bb_upper'] = df['bb_middle'] + 2 * std
        df['bb_lower'] = df['bb_middle'] - 2 * std
        
        # 波动率
        df['volatility'] = df['pct_chg'].rolling(20).std()
        
        return df
    except: return df

# ===================== 核心数据获取 (强逻辑版) =====================

def get_clean_market_data(ts_code, days=90):
    """获取行情 + 换手率"""
    pro = get_tushare_pro()
    if not pro: return {"错误": "Token无效"}
    
    try:
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        
        df = pd.DataFrame()
        turnover = "N/A"
        
        # 1. 获取基础行情
        if ts_code.endswith('.HK'):
            try:
                df = pro.hk_daily(ts_code=ts_code, start_date=start, end_date=end)
                # 尝试补全港股换手率
                try:
                    # 扩大范围找最近的一个指标
                    ind_start = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
                    df_ind = pro.hk_indicator(ts_code=ts_code, start_date=ind_start)
                    if not df_ind.empty:
                        last_ind = df_ind.sort_values('trade_date', ascending=False).iloc[0]
                        if pd.notna(last_ind.get('turnover_rate')):
                            turnover = f"{last_ind['turnover_rate']}%"
                except: pass
            except Exception as e: return {"错误": f"港股接口错: {e}"}
        else:
            df = pro.daily(ts_code=ts_code, start_date=start, end_date=end)
            
        if df.empty: return {"错误": "暂无行情数据"}
        
        # 2. 计算指标
        df = get_enhanced_technical_indicators(df)
        latest = df.iloc[-1]
        
        # A股换手率回填
        if not ts_code.endswith('.HK'):
            if pd.notna(latest.get('turnover_rate')): turnover = f"{latest['turnover_rate']}%"

        return {
            "收盘价": f"{latest['close']}",
            "涨跌幅": f"{latest['pct_chg']:.2f}%",
            "成交量": f"{latest['vol']/10000:.2f}万手",
            "换手率": turnover,
            "5日均线": f"{latest['ma5']:.2f}" if pd.notna(latest['ma5']) else "-",
            "10日均线": f"{latest['ma10']:.2f}" if pd.notna(latest['ma10']) else "-",
            "20日均线": f"{latest['ma20']:.2f}" if pd.notna(latest['ma20']) else "-",
            "MACD": f"{latest['macd']:.4f}" if pd.notna(latest['macd']) else "-",
            "RSI": f"{latest['rsi']:.2f}" if pd.notna(latest['rsi']) else "-",
            "布林上轨": f"{latest['bb_upper']:.2f}" if pd.notna(latest['bb_upper']) else "-",
            "布林中轨": f"{latest['bb_middle']:.2f}" if pd.notna(latest['bb_middle']) else "-",
            "布林下轨": f"{latest['bb_lower']:.2f}" if pd.notna(latest['bb_lower']) else "-",
            "波动率": f"{latest['volatility']:.4f}" if pd.notna(latest['volatility']) else "-",
        }
    except Exception as e: return {"错误": str(e)}

def get_clean_fundamental_data(ts_code, daily_data=None):
    """基本面获取 (死磕版)"""
    pro = get_tushare_pro()
    if not pro: return {"错误": "Token无效"}
    
    pe, pb, mv, industry = "-", "-", "-", "未知"
    
    try:
        # === A股 ===
        if not ts_code.endswith('.HK'):
            # 行业
            basic = pro.stock_basic(ts_code=ts_code, fields='name,industry')
            if not basic.empty: industry = basic.iloc[0]['industry']
            # 估值
            try:
                db = pro.daily_basic(ts_code=ts_code, trade_date=datetime.now().strftime('%Y%m%d'))
                if db.empty: # 找不到今天找昨天
                    db = pro.daily_basic(ts_code=ts_code, trade_date=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'))
                if not db.empty:
                    r = db.iloc[0]
                    pe = f"{r['pe_ttm']:.2f}"
                    pb = f"{r['pb']:.2f}"
                    mv = f"{r['total_mv']/10000:.2f}亿"
            except: pass
            
        # === 港股 (重点修复) ===
        else:
            # 1. 行业：hk_basic 通常没有 industry，我们尝试获取一下，如果没有就显示"港股"
            try:
                basic = pro.hk_basic(ts_code=ts_code)
                if not basic.empty:
                    # 如果字段里真有 industry 就用，没有就算了
                    industry = basic.iloc[0].get('industry', '港股主板')
            except: pass

            # 2. 估值：死磕 hk_indicator
            # 循环往前找 60 天的数据！直到找到为止
            try:
                end = datetime.now().strftime('%Y%m%d')
                start = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')
                
                # 不指定 fields，全量拉取，避免字段名写错
                df_ind = pro.hk_indicator(ts_code=ts_code, start_date=start, end_date=end)
                
                if not df_ind.empty:
                    # 按日期倒序，取第一行
                    r = df_ind.sort_values('trade_date', ascending=False).iloc[0]
                    
                    # 调试：只要有数据就填进去
                    if pd.notna(r.get('pe_ttm')): pe = f"{r['pe_ttm']:.2f}"
                    if pd.notna(r.get('pb')): pb = f"{r['pb']:.2f}"
                    # 港股市值字段可能是 mkt_cap
                    if pd.notna(r.get('mkt_cap')): mv = f"{r['mkt_cap']/100000000:.2f}亿"
                else:
                    # 如果 hk_indicator 真的空了，返回一个提示
                    pe = "Tushare无数据"
            except Exception as e:
                print(f"港股估值获取报错: {e}")
                
    except Exception as e:
        return {"错误": str(e)}

    return {
        "PE(TTM)": pe,
        "PB": pb,
        "总市值": mv,
        "所属行业": industry,
        "备注": "数据来源:Tushare Pro"
    }

def get_market_environment_data(ts_code):
    """市场环境 (强制兜底版)"""
    pro = get_tushare_pro()
    
    change = "0.00%"
    sentiment = "中性"
    index_name = "未知指数"
    
    try:
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=10)).strftime('%Y%m%d')
        
        df = pd.DataFrame()
        
        # 1. 优先尝试获取 沪深300 (399300.SZ) - 保证绝对能拿到数据
        # 无论查什么股票，先拿一个能用的指数垫底
        try:
            df_safe = pro.index_daily(ts_code='399300.SZ', start_date=start, end_date=end)
            if not df_safe.empty:
                r = df_safe.sort_values('trade_date', ascending=False).iloc[0]
                change = f"{r['pct_chg']:.2f}%"
                index_name = "沪深300(参考)"
        except: pass

        # 2. 如果是港股，尝试覆盖为 恒生指数
        if ts_code.endswith('.HK'):
            try:
                # 恒指代码 HSI
                df_hk = pro.index_daily(ts_code='HSI', start_date=start, end_date=end)
                if not df_hk.empty:
                    r = df_hk.sort_values('trade_date', ascending=False).iloc[0]
                    change = f"{r['pct_chg']:.2f}%"
                    index_name = "恒生指数"
            except: pass
        
        # 计算情绪
        try:
            chg_val = float(change.replace('%', ''))
            if chg_val > 1: sentiment = "乐观"
            elif chg_val < -1: sentiment = "悲观"
        except: pass
            
    except: pass
    
    return {
        "市场指数涨跌幅": f"{change} [{index_name}]",
        "市场情绪": sentiment,
        "资金流向": "暂缺"
    }
