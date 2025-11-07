import json
import os
from datetime import datetime

class DataManager:
    def __init__(self):
        self.data_dir = "data"
        self.system_file = os.path.join(self.data_dir, "system_status.json")
        self.trades_file = os.path.join(self.data_dir, "trades.json")
        self.performance_file = os.path.join(self.data_dir, "performance.json")
        self.ai_analysis_file = os.path.join(self.data_dir, "ai_analysis_history.json")
        
        # 确保数据目录存在
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
        # 初始化数据文件
        self._init_files()
    
    def _init_files(self):
        """初始化数据文件"""
        if not os.path.exists(self.system_file):
            self._save_json(self.system_file, {
                "status": "stopped",
                "last_update": datetime.now().isoformat(),
                "account_info": {},
                "btc_info": {},
                "position": {},
                "ai_signal": {}
            })
        
        if not os.path.exists(self.trades_file):
            self._save_json(self.trades_file, [])
        
        if not os.path.exists(self.performance_file):
            self._save_json(self.performance_file, {
                "total_trades": 0,
                "winning_trades": 0,
                "total_pnl": 0,
                "daily_pnl": {},
                "monthly_pnl": {}
            })
        
        if not os.path.exists(self.ai_analysis_file):
            self._save_json(self.ai_analysis_file, [])
    
    def _save_json(self, filepath, data):
        """保存JSON数据"""
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存数据失败 {filepath}: {e}")
    
    def _load_json(self, filepath):
        """加载JSON数据"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    
    def update_system_status(self, status, account_info=None, btc_info=None, position=None, ai_signal=None):
        """更新系统状态"""
        data = {
            "status": status,
            "last_update": datetime.now().isoformat(),
            "account_info": account_info or {},
            "btc_info": btc_info or {},
            "position": position or {},
            "ai_signal": ai_signal or {}
        }
        self._save_json(self.system_file, data)
    
    def save_trade_record(self, trade_record):
        """保存交易记录"""
        trades = self._load_json(self.trades_file)
        if not isinstance(trades, list):
            trades = []
        
        # 添加交易记录
        trades.append(trade_record)
        
        # 只保留最近100条记录
        if len(trades) > 100:
            trades = trades[-100:]
        
        self._save_json(self.trades_file, trades)
        
        # 更新绩效数据
        self._update_performance(trade_record)
    
    def _update_performance(self, trade_record):
        """更新绩效数据"""
        performance = self._load_json(self.performance_file)
        
        # 更新基础统计
        performance["total_trades"] = performance.get("total_trades", 0) + 1
        
        pnl = trade_record.get("pnl", 0)
        if pnl > 0:
            performance["winning_trades"] = performance.get("winning_trades", 0) + 1
        
        performance["total_pnl"] = performance.get("total_pnl", 0) + pnl
        
        # 更新每日绩效
        today = datetime.now().strftime("%Y-%m-%d")
        daily_pnl = performance.get("daily_pnl", {})
        daily_pnl[today] = daily_pnl.get(today, 0) + pnl
        performance["daily_pnl"] = daily_pnl
        
        # 更新月度绩效
        month = datetime.now().strftime("%Y-%m")
        monthly_pnl = performance.get("monthly_pnl", {})
        monthly_pnl[month] = monthly_pnl.get(month, 0) + pnl
        performance["monthly_pnl"] = monthly_pnl
        
        self._save_json(self.performance_file, performance)
    
    def get_system_status(self):
        """获取系统状态"""
        return self._load_json(self.system_file)
    
    def get_trade_history(self):
        """获取交易历史"""
        return self._load_json(self.trades_file)
    
    def get_performance(self):
        """获取绩效数据"""
        return self._load_json(self.performance_file)
    
    def save_ai_analysis_record(self, analysis_record):
        """保存AI分析记录"""
        analysis_history = self._load_json(self.ai_analysis_file)
        if not isinstance(analysis_history, list):
            analysis_history = []
        
        # 添加时间戳
        analysis_record['timestamp'] = datetime.now().isoformat()
        
        # 添加分析记录
        analysis_history.append(analysis_record)
        
        # 只保留最近50条记录
        if len(analysis_history) > 50:
            analysis_history = analysis_history[-50:]
        
        self._save_json(self.ai_analysis_file, analysis_history)
    
    def get_ai_analysis_history(self):
        """获取AI分析历史记录"""
        return self._load_json(self.ai_analysis_file)

# 全局数据管理器实例
data_manager = DataManager()

# 兼容性函数
def update_system_status(status, account_info=None, btc_info=None, position=None, ai_signal=None):
    data_manager.update_system_status(status, account_info, btc_info, position, ai_signal)

def save_trade_record(trade_record):
    data_manager.save_trade_record(trade_record)

def save_ai_analysis_record(analysis_record):
    data_manager.save_ai_analysis_record(analysis_record)