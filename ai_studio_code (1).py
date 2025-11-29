import os
import streamlit as st
from openai import OpenAI
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

def get_config_value(key):
    """优先从 Streamlit Secrets 获取，否则从环境变量"""
    if hasattr(st, "secrets") and key in st.secrets:
        return st.secrets[key]
    return os.getenv(key, "")

# 获取配置
ARK_API_KEY = get_config_value("ARK_API_KEY")
ARK_MODEL_ENDPOINT = get_config_value("ARK_MODEL_ENDPOINT") 
ARK_API_URL = "https://ark.cn-beijing.volces.com/api/v3"

def call_deepseek_api(prompt):
    """调用 DeepSeek"""
    if not ARK_API_KEY or not ARK_MODEL_ENDPOINT:
        return "❌ 错误: 未配置 API Key 或 Endpoint ID，请在 Streamlit Secrets 中配置。"

    try:
        client = OpenAI(base_url=ARK_API_URL, api_key=ARK_API_KEY)
        
        completion = client.chat.completions.create(
            model=ARK_MODEL_ENDPOINT,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=4000
        )
        return completion.choices[0].message.content
    except Exception as e:
        return f"API调用失败: {str(e)}"

def generate_analysis_prompt(stock_code, stock_name, predict_cycle, daily_data, fundamental_data, market_data):
    """生成 Prompt"""
    
    def fmt(d):
        return {k: str(v) for k, v in d.items()}
    
    daily = fmt(daily_data)
    fund = fmt(fundamental_data)
    mkt = fmt(market_data)
    
    prompt = f"""
你是一名资深的量化分析师，请基于以下 Tushare 数据进行深度分析。

## 📊 基本信息
- **股票**：{stock_name} ({stock_code})
- **预测周期**：{predict_cycle}
- **日期**：{datetime.now().strftime('%Y-%m-%d')}

## 📈 数据概览
### 1. 技术面
- 收盘价：{daily.get('收盘价')} (涨跌幅 {daily.get('涨跌幅')})
- 均线系统：MA5 {daily.get('5日均线')}, MA20 {daily.get('20日均线')}
- 指标状态：MACD {daily.get('MACD')}, RSI {daily.get('RSI')}
- 布林带位置：{daily.get('布林上轨')} / {daily.get('布林下轨')}
- 波动率：{daily.get('波动率')}

### 2. 基本面
- 估值：PE(TTM) {fund.get('PE(TTM)')}, PB {fund.get('PB')}
- 行业：{fund.get('所属行业')}
- 市值：{fund.get('总市值')}

### 3. 市场环境
- 市场表现：{mkt.get('市场指数涨跌幅')}
- 情绪判定：{mkt.get('市场情绪')}

## 📋 分析指令
请输出一份结构清晰的预测报告：
1. **方向预测**：明确看多、看空还是震荡，并给出置信度（高/中/低）。
2. **技术解读**：结合 MACD、RSI 和均线形态分析当前趋势。
3. **基本面评估**：当前估值在行业中的水平（若数据可用）。
4. **操作建议**：针对{predict_cycle}周期的具体操作思路。
5. **风险提示**：至少 2 点风险。

注意：如果是港股数据（代码以 .HK 结尾），请考虑港股市场的特殊性（无涨跌停限制、T+0等）。
"""
    return prompt