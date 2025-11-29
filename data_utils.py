import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
import os
import re
import streamlit as st

def get_tushare_pro():
    """获取 Tushare Pro 接口客户端"""
    try:
        if hasattr(st, 'secrets') and 'TUSHARE_TOKEN' in st.secrets:
            token = st.secrets['TUSHARE_TOKEN']
        else:
            token = os.getenv("TUSHARE_TOKEN", "")
        
        if not token:
            return None
            
        ts.set_token(token)
        return ts.pro_api()
    except Exception as e:
        print(f"Tushare Token 初始化失败: {e}")
        return None

def get_enhanced_technical_indicators(df):
    """计算全套技术指标"""
    try:
        # Tushare 返回按日期降序，计算指标须按升序
        df = df.sort_values('trade_date').reset_index(drop=True)
        close = df['close']
        
        # 1. 均线系统
        df['ma5'] = close.rolling(window=5).mean()
        df['ma10'] = close.rolling(window=10).mean()
        df['ma20'] = close.rolling(window=20).mean()
        
        # 2. MACD (12, 26, 9)
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        df['dif'] = exp1 - exp2
        df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
        df['macd'] = (df['dif'] - df['dea']) * 2
        
        # 3. RSI (14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 4. 布林带 (20, 2)
        df['bb_middle'] = close.rolling(window=20).mean()
        bb_std = close.rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + 2 * bb_std
        df['bb_lower'] = df['bb_middle'] - 2 * bb_std
        
        # 5. 波动率 (20日)
        df['volatility'] = df['pct_chg'].rolling(window=20).std()
        
        return df
    except Exception as e:
        print(f"指标计算微小错误 (可忽略): {e}")
        return df

def validate_stock_code(code):
    """验证输入并自动推断后缀"""
    clean_code = re.sub(r'[^\d]', '', str(code))
    
    # 港股 (5位)
    if len(clean_code) == 5:
        return True, clean_code + ".HK"
    
    # A股 (6位)
    if len(clean_code) == 6:
        if clean_code.startswith('6'): suffix = ".SH"
        elif clean_code.startswith(('0', '3')): suffix = ".SZ"
        elif clean_code.startswith(('8', '4')): suffix = ".BJ"
        else: return False, "无法识别的A股前缀"
        return True, clean_code + suffix
    
    return False, "请输入5位(港股)或6位(A股)代码"

def get_stock_name_by_code(ts_code):
    """获取股票名称"""
    pro = get_tushare_pro()
    if not pro: return "Tushare未连接"
    try:
        if ts_code.endswith('.HK'):
            df = pro.hk_basic(ts_code=ts_code)
        else:
            df = pro.stock_basic(ts_code=ts_code)
            
        if not df.empty:
            return df.iloc[0]['name']
    except: pass
    return "未知股票"

def search_stocks(keyword):
    """搜索股票 (A股 + 港股)"""
    pro = get_tushare_pro()
    if not pro: return []
    results = []
    try:
        # A股搜索
        df_a = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name')
        if not df_a.empty:
            mask = df_a["name"].str.contains(keyword, na=False) | df_a["symbol"].str.contains(keyword, na=False)
            results.extend([{"代码": r['ts_code'], "名称": r['name'], "类型": "A股"} for _, r in df_a[mask].head(5).iterrows()])
        
        # 港股搜索 (5000积分权限可用)
        try:
            df_hk = pro.hk_basic(list_status='L', fields='ts_code,name')
            if not df_hk.empty:
                mask_hk = df_hk["name"].str.contains(keyword, na=False) | df_hk["ts_code"].str.contains(keyword, na=False)
                results.extend([{"代码": r['ts_code'], "名称": r['name'], "类型": "港股"} for _, r in df_hk[mask_hk].head(5).iterrows()])
        except: pass
            
        return results[:10]
    except: return []

def get_clean_market_data(ts_code, days=90):
    """获取行情数据 (VIP版：包含港股换手率)"""
    pro = get_tushare_pro()
    if not pro: return {"错误": "Token无效"}
    
    try:
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        
        df = pd.DataFrame()
        turnover = "N/A" # 默认换手率
        
        if ts_code.endswith('.HK'):
            # === 港股逻辑 (5000积分版) ===
            try:
                # 1. 获取基础行情 (hk_daily)
                df = pro.hk_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
                
                # 2. 额外获取换手率 (hk_indicator) - 这就是5000积分的特权
                # 只取最近几天的 indicator 看看能不能匹配上
                try:
                    df_ind = pro.hk_indicator(ts_code=ts_code, start_date=(datetime.now() - timedelta(days=5)).strftime('%Y%m%d'))
                    if not df_ind.empty:
                        # 倒序取最新的
                        latest_ind = df_ind.sort_values('trade_date', ascending=False).iloc[0]
                        # 港股换手率字段可能是 turnover_rate
                        if 'turnover_rate' in latest_ind:
                             turnover = f"{latest_ind['turnover_rate']}%"
                except Exception as e:
                    print(f"港股Indicator获取失败: {e}")
                    
            except Exception as e:
                return {"错误": f"港股接口异常: {e}"}
        else:
            # === A股逻辑 ===
            df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            # A股换手率直接在 daily 里
        
        if df.empty:
            return {"错误": "未获取到历史数据 (可能停牌)"}
        
        # 计算技术指标
        df = get_enhanced_technical_indicators(df)
        latest = df.iloc[-1]
        
        # 如果是A股，直接用里面的 turnover_rate
        if not ts_code.endswith('.HK'):
            turnover = f"{latest.get('turnover_rate', 'N/A')}%"

        return {
            "收盘价": f"{latest['close']}",
            "涨跌幅": f"{latest['pct_chg']:.2f}%",
            "成交量": f"{latest['vol']/10000:.2f}万手",
            "换手率": turnover, # 这里的 turnover 现在应该有值了
            "5日均线": f"{latest['ma5']:.2f}" if pd.notna(latest['ma5']) else "N/A",
            "10日均线": f"{latest['ma10']:.2f}" if pd.notna(latest['ma10']) else "N/A",
            "20日均线": f"{latest['ma20']:.2f}" if pd.notna(latest['ma20']) else "N/A",
            "MACD": f"{latest['macd']:.4f}" if pd.notna(latest['macd']) else "N/A",
            "RSI": f"{latest['rsi']:.2f}" if pd.notna(latest['rsi']) else "N/A",
            "布林上轨": f"{latest['bb_upper']:.2f}" if pd.notna(latest['bb_upper']) else "N/A",
            "布林中轨": f"{latest['bb_middle']:.2f}" if pd.notna(latest['bb_middle']) else "N/A",
            "布林下轨": f"{latest['bb_lower']:.2f}" if pd.notna(latest['bb_lower']) else "N/A",
            "波动率": f"{latest['volatility']:.4f}" if pd.notna(latest['volatility']) else "N/A",
        }
    except Exception as e:
        return {"错误": f"行情获取异常: {str(e)}"}

def get_clean_fundamental_data(ts_code, daily_data=None):
    """获取基本面数据 (VIP版：解锁港股PE/PB/市值)"""
    pro = get_tushare_pro()
    if not pro: return {"错误": "Token无效"}
    
    try:
        pe, pb, mv, industry = "N/A", "N/A", "N/A", "未知"
        
        if ts_code.endswith('.HK'):
            # === 港股基本面 (5000积分特权) ===
            
            # 1. 行业信息 (hk_basic 有 industry 字段，但不一定有值)
            try:
                basic = pro.hk_basic(ts_code=ts_code)
                if not basic.empty:
                    industry = basic.iloc[0].get('industry', '港股')
            except: pass

            # 2. 估值数据 (核心：使用 hk_indicator)
            try:
                # 尝试获取最近3天的指标数据，防止今天的数据还没出
                df_ind = pro.hk_indicator(ts_code=ts_code, 
                                        start_date=(datetime.now() - timedelta(days=3)).strftime('%Y%m%d'),
                                        fields='pe_ttm,pb,mkt_cap') # mkt_cap 是总市值
                
                if not df_ind.empty:
                    # 取最新的一条
                    r = df_ind.sort_values('trade_date', ascending=False).iloc[0]
                    
                    if pd.notna(r['pe_ttm']): pe = f"{r['pe_ttm']:.2f}"
                    if pd.notna(r['pb']): pb = f"{r['pb']:.2f}"
                    # 港股市值单位通常是港币，Tushare返回单位视接口文档，通常是直接数值
                    if pd.notna(r['mkt_cap']): 
                        # mkt_cap 在 hk_indicator 里单位通常是 元，转换成亿
                        mv = f"{r['mkt_cap']/100000000:.2f}亿"
            except Exception as e:
                print(f"港股估值获取失败: {e}")

        else:
            # === A股基本面 (保持不变) ===
            basic = pro.stock_basic(ts_code=ts_code, fields='name,industry')
            if not basic.empty: industry = basic.iloc[0]['industry']
            
            try:
                db = pro.daily_basic(ts_code=ts_code, trade_date=datetime.now().strftime('%Y%m%d'))
                if db.empty: db = pro.daily_basic(ts_code=ts_code, trade_date=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'))
                if not db.empty:
                    r = db.iloc[0]
                    pe = f"{r['pe_ttm']:.2f}" if pd.notna(r['pe_ttm']) else "N/A"
                    pb = f"{r['pb']:.2f}" if pd.notna(r['pb']) else "N/A"
                    mv = f"{r['total_mv']/10000:.2f}亿" if pd.notna(r['total_mv']) else "N/A"
            except: pass

        return {
            "PE(TTM)": pe,
            "PB": pb,
            "总市值": mv,
            "所属行业": industry,
            "备注": "港股数据(VIP源)" if ts_code.endswith('.HK') else "A股数据"
        }
    except Exception as e:
        return {"错误": f"基本面异常: {str(e)}"}

def get_market_environment_data(ts_code):
    """获取大盘数据"""
    pro = get_tushare_pro()
    try:
        index_code = 'HSI' if ts_code.endswith('.HK') else '399300.SZ'
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
        
        # 指数接口
        df = pd.DataFrame()
        try:
            df = pro.index_daily(ts_code=index_code, start_date=start, end_date=end)
            if df.empty and ts_code.endswith('.HK'):
                 # 恒指代码可能是 990001 (Tushare内部编码不一) 或者 ^HSI
                 # 如果失败，暂时用沪深300兜底
                 df = pro.index_daily(ts_code='399300.SZ', start_date=start, end_date=end)
        except:
             df = pro.index_daily(ts_code='399300.SZ', start_date=start, end_date=end)
             
        if not df.empty:
            change = df.iloc[0]['pct_chg']
            sentiment = "乐观" if change > 1 else ("悲观" if change < -1 else "中性")
            return {"市场指数涨跌幅": f"{change:.2f}%", "市场情绪": sentiment}
            
    except: pass
    return {"市场指数涨跌幅": "N/A", "市场情绪": "未知"}
