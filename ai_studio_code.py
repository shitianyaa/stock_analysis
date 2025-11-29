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
    """计算技术指标"""
    try:
        # Tushare 返回按日期降序，计算指标须按升序
        df = df.sort_values('trade_date').reset_index(drop=True)
        close = df['close']
        
        # 基础均线
        df['ma5'] = close.rolling(window=5).mean()
        df['ma10'] = close.rolling(window=10).mean()
        df['ma20'] = close.rolling(window=20).mean()
        
        # MACD (12, 26, 9)
        exp1 = close.ewm(span=12, adjust=False).mean()
        exp2 = close.ewm(span=26, adjust=False).mean()
        df['dif'] = exp1 - exp2
        df['dea'] = df['dif'].ewm(span=9, adjust=False).mean()
        df['macd'] = (df['dif'] - df['dea']) * 2
        
        # RSI (14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 布林带 (20, 2)
        df['bb_middle'] = close.rolling(window=20).mean()
        bb_std = close.rolling(window=20).std()
        df['bb_upper'] = df['bb_middle'] + 2 * bb_std
        df['bb_lower'] = df['bb_middle'] - 2 * bb_std
        
        # 波动率
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
        # 判断是港股还是A股
        if ts_code.endswith('.HK'):
            df = pro.hk_basic(ts_code=ts_code)
        else:
            df = pro.stock_basic(ts_code=ts_code)
            
        if not df.empty:
            return df.iloc[0]['name']
    except Exception:
        pass
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
        
        # 港股搜索 (需要积分权限)
        try:
            df_hk = pro.hk_basic(list_status='L', fields='ts_code,name')
            if not df_hk.empty:
                mask_hk = df_hk["name"].str.contains(keyword, na=False) | df_hk["ts_code"].str.contains(keyword, na=False)
                results.extend([{"代码": r['ts_code'], "名称": r['name'], "类型": "港股"} for _, r in df_hk[mask_hk].head(5).iterrows()])
        except:
            pass # 没权限则跳过港股搜索
            
        return results[:10]
    except Exception as e:
        return []

def get_clean_market_data(ts_code, days=90):
    """获取行情数据 (兼容A股/港股)"""
    pro = get_tushare_pro()
    if not pro: return {"错误": "Token无效"}
    
    try:
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')
        
        df = pd.DataFrame()
        
        # === 核心修改：区分市场接口 ===
        if ts_code.endswith('.HK'):
            try:
                # 港股接口 (需2000积分)
                df = pro.hk_daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            except Exception as e:
                return {"错误": f"港股权限不足或接口异常: {e}"}
        else:
            # A股接口
            df = pro.daily(ts_code=ts_code, start_date=start_date, end_date=end_date)
            
        if df.empty:
            return {"错误": "未获取到历史数据 (可能停牌或权限不足)"}
        
        # 计算指标
        df = get_enhanced_technical_indicators(df)
        latest = df.iloc[-1]
        
        return {
            "收盘价": f"{latest['close']}",
            "涨跌幅": f"{latest['pct_chg']:.2f}%",
            "成交量": f"{latest['vol']/10000:.2f}万手",
            "换手率": f"{latest.get('turnover_rate', 'N/A')}",
            "5日均线": f"{latest['ma5']:.2f}" if pd.notna(latest['ma5']) else "N/A",
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
    """获取基本面数据 (兼容A股/港股)"""
    pro = get_tushare_pro()
    if not pro: return {"错误": "Token无效"}
    
    try:
        info = {}
        pe = "N/A"
        pb = "N/A"
        mv = "N/A"
        industry = "未知"
        
        # === 核心修改：区分市场 ===
        if ts_code.endswith('.HK'):
            # 港股基本面
            try:
                basic = pro.hk_basic(ts_code=ts_code)
                if not basic.empty:
                    info = basic.iloc[0]
                    industry = info.get('industry', '未知')
                    # 港股 PE/PB 很多时候不在 basic 里，简单处理
                    pe = info.get('pe', 'N/A') 
            except:
                industry = "港股(需权限)"
        else:
            # A股基本面
            basic = pro.stock_basic(ts_code=ts_code, fields='name,industry,area')
            if not basic.empty:
                industry = basic.iloc[0]['industry']
            
            # 每日指标
            try:
                db = pro.daily_basic(ts_code=ts_code, trade_date=datetime.now().strftime('%Y%m%d'))
                if db.empty: # 尝试前一天
                    db = pro.daily_basic(ts_code=ts_code, trade_date=(datetime.now() - timedelta(days=1)).strftime('%Y%m%d'))
                
                if not db.empty:
                    row = db.iloc[0]
                    pe = f"{row['pe_ttm']:.2f}" if pd.notna(row['pe_ttm']) else "N/A"
                    pb = f"{row['pb']:.2f}" if pd.notna(row['pb']) else "N/A"
                    mv = f"{row['total_mv']/10000:.2f}亿" if pd.notna(row['total_mv']) else "N/A"
            except:
                pass

        return {
            "PE(TTM)": pe,
            "PB": pb,
            "总市值": mv,
            "所属行业": industry,
            "备注": "港股数据需Tushare 2000+积分" if ts_code.endswith('.HK') else "A股数据"
        }
    except Exception as e:
        return {"错误": f"基本面异常: {str(e)}"}

def get_market_environment_data(ts_code):
    """获取大盘数据"""
    pro = get_tushare_pro()
    if not pro: return {"错误": "Token无效"}
    
    try:
        # 默认取沪深300
        index_code = '399300.SZ' 
        # 如果是港股，取恒生指数
        if ts_code.endswith('.HK'):
            index_code = 'HSI' # Tushare 恒指代码可能不同，常用 HSI
        
        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
        
        # 指数接口
        try:
            df = pro.index_daily(ts_code=index_code, start_date=start, end_date=end)
            if df.empty:
                # 如果恒指拿不到，退回沪深300作为参考
                df = pro.index_daily(ts_code='399300.SZ', start_date=start, end_date=end)
            
            latest = df.iloc[0] # 倒序
            change = latest['pct_chg']
            
            sentiment = "中性"
            if change > 1: sentiment = "乐观"
            elif change < -1: sentiment = "悲观"
            
            return {
                "市场指数涨跌幅": f"{change:.2f}%",
                "市场情绪": sentiment,
                "资金流向": "暂缺"
            }
        except:
            return {"市场指数涨跌幅": "N/A", "市场情绪": "未知"}
            
    except Exception as e:
        return {"错误": str(e)}