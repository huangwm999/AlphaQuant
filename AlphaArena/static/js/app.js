// OKX BTC交易机器人 - 工具函数库

// 简化元素创建
window.h = React.createElement;

// ==================== 常量定义 ====================
const CONSTANTS = {
    REFRESH_INTERVAL: 5000,
    CONTRACTS_MIN: 0.01,
    CONTRACTS_MAX: 100,
    CONTRACTS_DEFAULT: 0.01,
    DAYS_MIN: 1,
    DAYS_MAX: 300,
    BACKTEST_DAYS_DEFAULT: 3
};

// ==================== 工具函数 ====================

// 时间格式化函数
window.formatDateTime = (format = 'YYYY-MM-DDTHH:mm') => {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    const day = String(now.getDate()).padStart(2, '0');
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    
    return format
        .replace('YYYY', year)
        .replace('MM', month)
        .replace('DD', day)
        .replace('HH', hours)
        .replace('mm', minutes);
};

// 创建标签文本控件（label + 文字）
window.createLabel = (text) => 
    h('span', { className: 'control-label' }, text);

// 创建数字输入控件组（label + InputNumber）
window.createNumberInput = (label, value, onChange, options = {}) => {
    const { min = 1, max = 300, step = 1, precision = 0 } = options;
    return h('div', { className: 'control-group' },
        window.createLabel(label),
        h(antd.InputNumber, {
            min, max, step, precision,
            size: 'small',
            value,
            onChange: (v) => {
                const nv = Number(v) || min;
                if (nv < min || nv > max) return;
                onChange(nv);
            },
            className: 'input-sm'
        })
    );
};

// ==================== UI组件生成器 ====================

// 指标配置（统一管理所有技术指标）
const indicatorConfigs = [
    { id: 'price', label: '价格曲线', defaultChecked: true },
    { id: 'sma5', label: 'SMA5', defaultChecked: false },
    { id: 'sma20', label: 'SMA20', defaultChecked: false },
    { id: 'sma50', label: 'SMA50', defaultChecked: false },
    { id: 'bollinger', label: '布林带通道', defaultChecked: true },
    { id: 'macd', label: 'MACD线', defaultChecked: false },
    { id: 'macd_signal', label: 'MACD信号线', defaultChecked: true },
    { id: 'macd_histogram', label: 'MACD柱状图', defaultChecked: true },
    { id: 'rsi', label: 'RSI', defaultChecked: false },
    { id: 'scores', label: 'Score评分', defaultChecked: false },
    { id: 'decisions', label: '交易决策', defaultChecked: true }
];

// 生成指标选择器控件
window.createIndicatorControls = (dataAttr, onChangeHandler) => {
    return h('div', { className: 'indicator-controls' },
        ...indicatorConfigs.map(({ id, label, defaultChecked }) =>
            h('label', { key: id },
                h('input', {
                    type: 'checkbox',
                    defaultChecked,
                    onChange: onChangeHandler,
                    [`data-${dataAttr}`]: id
                }),
                label
            )
        )
    );
};

// 手动交易通用函数
window.executeTrade = async (signal, contracts, onSuccess) => {
    const actionText = signal === 'BUY' ? '买入' : '卖出';
    const confirmed = await new Promise(resolve => {
        antd.Modal.confirm({
            title: `确认手动${actionText}`,
            content: `确定要${actionText} ${contracts} 张 (${(contracts * 0.01).toFixed(4)} BTC) 吗？`,
            okText: `确认${actionText}`,
            cancelText: '取消',
            onOk: () => resolve(true),
            onCancel: () => resolve(false)
        });
    });
    
    if (!confirmed) return;
    
    try {
        const res = await fetch('/api/manual-trade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ signal, contracts })
        });
        const result = await res.json();
        
        if (res.ok) {
            antd.message.success(`${actionText}成功：${contracts} 张`);
            onSuccess && onSuccess();
        } else {
            antd.message.error(`${actionText}失败: ${result.error || '未知错误'}`);
        }
    } catch (err) {
        antd.message.error(`${actionText}失败: ${err.message}`);
    }
};

// 回测图表更新函数
window.updateBacktestChart = (backtestData) => {
    if (!backtestData) return;
    const selected = Array.from(
        document.querySelectorAll('input[data-indicator-bt]')
    )
    .filter(cb => cb.checked)
    .map(cb => cb.dataset.indicatorBt);
    
    window.initTechnicalChart && window.initTechnicalChart(backtestData.chart, selected, 'backtestTechnicalChart');
};





// ==================== 图表配置常量 ====================

// 颜色配置
const CHART_COLORS = {
    price: '#1890ff',
    sma5: '#52c41a',
    sma20: '#faad14',
    sma50: '#f5222d',
    bollinger: '#722ed1',
    bollingerMiddle: '#13c2c2',
    macd: '#52c41a',
    macdSignal: '#f5222d',
    rsi: '#eb2f96',
    score: '#a0d911',
    buySignal: '#52c41a',
    sellSignal: '#f5222d',
    holdSignal: '#d9d9d9'
};

// 基础图表配置（price和dailyPnl）
const BASE_CHART_CONFIGS = {
    price: {
        type: 'line',
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: {
                    beginAtZero: false,
                    ticks: { callback: v => `$${v.toLocaleString()}` }
                }
            },
            plugins: { legend: { display: false } }
        }
    },
    dailyPnl: {
        type: 'bar',
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { font: { size: 9 }, maxTicksLimit: 4 }
                }
            }
        }
    }
};

// 指标数据集配置映射
const INDICATOR_DATASET_CONFIGS = {
    // 价格线
    price: (data) => ({
        label: 'BTC价格',
        data: data.klines.map(k => k.close),
        borderColor: CHART_COLORS.price,
        backgroundColor: 'rgba(24, 144, 255, 0.1)',
        yAxisID: 'y-price',
        tension: 0.1
    }),
    // 移动平均线
    sma5: (data) => ({
        label: 'SMA5',
        data: data.indicators.sma5,
        borderColor: CHART_COLORS.sma5,
        backgroundColor: 'transparent',
        yAxisID: 'y-price',
        borderWidth: 1
    }),
    sma20: (data) => ({
        label: 'SMA20',
        data: data.indicators.sma20,
        borderColor: CHART_COLORS.sma20,
        backgroundColor: 'transparent',
        yAxisID: 'y-price',
        borderWidth: 1
    }),
    sma50: (data) => ({
        label: 'SMA50',
        data: data.indicators.sma50,
        borderColor: CHART_COLORS.sma50,
        backgroundColor: 'transparent',
        yAxisID: 'y-price',
        borderWidth: 1
    }),
    // MACD
    macd: (data) => ({
        label: 'MACD',
        data: data.indicators.macd,
        borderColor: CHART_COLORS.macd,
        backgroundColor: 'transparent',
        yAxisID: 'y-macd',
        borderWidth: 2
    }),
    macd_signal: (data) => ({
        label: 'MACD信号',
        data: data.indicators.macd_signal,
        borderColor: CHART_COLORS.macdSignal,
        backgroundColor: 'transparent',
        yAxisID: 'y-macd',
        borderWidth: 1
    }),
    // RSI
    rsi: (data) => ({
        label: 'RSI',
        data: data.indicators.rsi,
        borderColor: CHART_COLORS.rsi,
        backgroundColor: 'rgba(235, 47, 150, 0.2)',
        yAxisID: 'y-rsi',
        borderWidth: 2,
        fill: true
    }),
    // Score评分
    scores: (data) => ({
        label: 'Score评分',
        data: data.indicators.scores,
        borderColor: CHART_COLORS.score,
        backgroundColor: 'rgba(160, 217, 17, 0.2)',
        yAxisID: 'y-score',
        borderWidth: 2,
        fill: true
    })
};

// Y轴配置映射
const Y_AXIS_CONFIGS = {
    'y-price': {
        type: 'linear',
        position: 'left',
        grid: { color: '#f0f0f0' },
        ticks: { callback: v => `$${v.toLocaleString()}` }
    },
    'y-macd': {
        type: 'linear',
        position: 'right',
        grid: { display: false },
        ticks: { font: { size: 10 } }
    },
    'y-macd-histogram': {
        type: 'linear',
        position: 'right',
        grid: { display: false },
        ticks: { font: { size: 10 }, callback: v => v.toFixed(1) }
    },
    'y-rsi': {
        type: 'linear',
        position: 'right',
        min: 0,
        max: 100,
        grid: { display: false },
        ticks: { font: { size: 10 } }
    },
    'y-score': {
        type: 'linear',
        position: 'right',
        min: -100,
        max: 100,
        grid: { display: false },
        ticks: { font: { size: 10 }, callback: v => `S${v}` }
    },
    'y-decision': {
        type: 'linear',
        position: 'right',
        min: -1.5,
        max: 1.5,
        grid: { display: true, color: 'rgba(0,0,0,0.1)', drawOnChartArea: false },
        ticks: {
            font: { size: 10 },
            stepSize: 1,
            callback: v => {
                if (v === 1) return '🟢买入';
                if (v === -1) return '🔴卖出';
                if (v === 0) return '持有';
                return '';
            }
        }
    }
};

// ==================== 工具函数 ====================

// 销毁已存在的图表实例
const destroyChart = (chartId) => {
    if (window[chartId]?.destroy) {
        try { window[chartId].destroy(); } catch (e) {}
    }
};

// ==================== 图表渲染函数 ====================
// 表格格式化函数
const getSignalTag = signal => h(antd.Tag, { color: { BUY: 'success', SELL: 'error', HOLD: 'warning' }[signal] || 'default', size: 'small' }, signal || 'HOLD');
const formatTime = ts => ts ? ts.split(' ')[1] : '--';
const formatPrice = p => p ? `$${p.toLocaleString()}` : '--';
const formatPnl = pnl => !pnl ? '--' : h(antd.Tag, { color: pnl >= 0 ? 'red' : 'green' }, `${pnl.toFixed(2)} USDT`);
const formatFee = (fee, record) => {
    if (fee !== undefined && fee !== null) return `${fee.toFixed(6)} USDT`;
    if (record.price && record.amount) {
        const calculatedFee = record.price * record.amount * 0.01 * 0.0005;
        return `${calculatedFee.toFixed(6)} USDT`;
    }
    return '--';
};

// 表格列配置
const tradeColumns = [
    { title: '时间', dataIndex: 'timestamp', width: 120, render: formatTime },
    { title: '信号', dataIndex: 'signal', width: 80, render: getSignalTag },
    { title: '价格', dataIndex: 'price', width: 120, render: formatPrice },
    { title: '手续费', dataIndex: 'fee', width: 100, render: formatFee },
    { title: '盈亏', dataIndex: 'pnl', width: 100, render: formatPnl }
];

const analysisColumns = [
    { title: '时间', dataIndex: 'timestamp', width: 70, render: text => text ? moment(text).format('HH:mm') : '--' },
    { title: '信号', dataIndex: 'signal', width: 50, render: getSignalTag },
    { title: '信心', dataIndex: 'confidence', width: 50, render: conf => h(antd.Tag, { color: { HIGH: 'success', MEDIUM: 'warning', LOW: 'error' }[conf] || 'default', size: 'small' }, conf || '--') },
    { title: '价格', dataIndex: 'btc_price', width: 70, render: price => price ? `$${Math.round(price).toLocaleString()}` : '--' }
];

// 通用图表初始化函数（简化版）
function initChart(chartId, data, type = 'line') {
    const ctx = document.getElementById(chartId);
    if (!ctx) return;
    
    destroyChart(chartId);
    
    const config = BASE_CHART_CONFIGS[type];
    if (!config) return;
    
    const chartData = type === 'price' 
        ? { labels: data.labels, datasets: [{ 
            data: data.prices, 
            borderColor: CHART_COLORS.price, 
            backgroundColor: 'rgba(24, 144, 255, 0.1)', 
            tension: 0.1, 
            fill: true 
        }] }
        : { labels: Object.keys(data), datasets: [{ 
            data: Object.values(data), 
            backgroundColor: Object.values(data).map(v => v >= 0 ? CHART_COLORS.sellSignal : CHART_COLORS.buySignal), 
            borderWidth: 0 
        }] };
    
    window[chartId] = new Chart(ctx, {
        type: config.type,
        data: chartData,
        options: config.options
    });
}

// 价格图表初始化函数 - 根据数据范围自动选择时间格式
window.initPriceChart = (trades) => {
    if (!trades?.length) return;
    
    // 检查数据跨度是否超过1天
    const firstTime = moment(trades[0].timestamp);
    const lastTime = moment(trades[trades.length - 1].timestamp);
    const daysDiff = lastTime.diff(firstTime, 'days');
    
    // 如果跨越多天，显示"月-日 时:分"，否则只显示"时:分"
    const format = daysDiff > 0 ? 'MM-DD HH:mm' : 'HH:mm';
    
    initChart('priceChart', { 
        labels: trades.map(t => moment(t.timestamp).format(format)), 
        prices: trades.map(t => t.price) 
    }, 'price');
};

// 初始化图表的包装函数
window.initDailyPnlChart = (dailyPnl) => dailyPnl && Object.keys(dailyPnl).length > 0 && initChart('dailyPnlChart', dailyPnl, 'dailyPnl');

// 技术图表初始化函数
window.initTechnicalChart = (data, selectedIndicators = [], chartId = 'technicalChart') => {
    const ctx = document.getElementById(chartId);
    if (!ctx || !data) {
        console.warn('技术图表初始化失败: 缺少canvas元素或数据');
        return;
    }
    
    // 验证数据完整性
    if (!data.labels || !data.indicators) {
        console.warn('技术图表数据不完整:', data);
        return;
    }
    
    // 计算横向滚动所需的容器宽度（每根K线给定像素宽度）
    const scrollEl = document.getElementById(`${chartId}-scroll`);
    const innerEl = document.getElementById(`${chartId}-inner`);
    // 仅为存在滚动容器的回测图设置动态宽度（技术指标分析已还原不滚动）
    if (scrollEl && innerEl && chartId === 'backtestTechnicalChart') {
        const pxPerBar = 13; // 降低每个数据点像素宽度，与技术指标图保持一致的紧凑度
        const labelsCount = Array.isArray(data.labels) ? data.labels.length : (data.klines ? data.klines.length : 0);
        const minWidth = scrollEl.clientWidth || 600;
        const targetWidth = Math.max(minWidth, labelsCount * pxPerBar);
        innerEl.style.width = `${targetWidth}px`;
    }

    destroyChart(chartId);
    
    const datasets = [];
    
    // 使用配置驱动生成基础指标dataset
    selectedIndicators.forEach(indicator => {
        const configFn = INDICATOR_DATASET_CONFIGS[indicator];
        if (configFn) {
            datasets.push(configFn(data));
        }
    });
    
    // 布林带 - 需要特殊处理（上中下三轨）
    if (selectedIndicators.includes('bollinger')) {
        const currentDatasetLength = datasets.length;
        datasets.push(
            {
                label: 'BB下轨',
                data: data.indicators.bb_lower,
                borderColor: CHART_COLORS.bollinger,
                backgroundColor: 'transparent',
                yAxisID: 'y-price',
                borderWidth: 1,
                pointRadius: 0,
                fill: false
            },
            {
                label: 'BB上轨',
                data: data.indicators.bb_upper,
                borderColor: CHART_COLORS.bollinger,
                backgroundColor: 'rgba(114, 46, 209, 0.1)',
                yAxisID: 'y-price',
                borderWidth: 1,
                pointRadius: 0,
                fill: currentDatasetLength,
                tension: 0.1
            },
            {
                label: 'BB中轨',
                data: data.indicators.bb_middle,
                borderColor: CHART_COLORS.bollingerMiddle,
                backgroundColor: 'transparent',
                yAxisID: 'y-price',
                borderWidth: 1.5,
                borderDash: [5, 5],
                pointRadius: 0,
                fill: false
            }
        );
    }
    
    // MACD柱状图 - 需要特殊处理（柱状图+颜色映射）
    if (selectedIndicators.includes('macd_histogram')) {
        const histogramData = data.indicators.macd_histogram || [];
        datasets.push({
            label: 'MACD柱状图',
            data: histogramData,
            type: 'bar',
            yAxisID: 'y-macd-histogram',
            backgroundColor: histogramData.map(v => v >= 0 ? 'rgba(82, 196, 26, 0.8)' : 'rgba(245, 34, 45, 0.8)'),
            borderColor: histogramData.map(v => v >= 0 ? CHART_COLORS.buySignal : CHART_COLORS.sellSignal),
            borderWidth: 1,
            barThickness: 'flex'
        });
    }
    
    // 交易决策柱状图 - 需要特殊处理（数据标准化+颜色映射）
    if (selectedIndicators.includes('decisions')) {
        const decisions = data.indicators.decisions || [];
        const labelCount = data.labels ? data.labels.length : 0;
        const normalizedDecisions = Array(labelCount).fill(0).map((_, i) => decisions[i] !== undefined ? decisions[i] : 0);
        
        console.log(`决策数据初始化: 标签数量=${labelCount}, 决策数据数量=${decisions.length}, 标准化后=${normalizedDecisions.length}`);
        
        datasets.push({
            label: '交易决策',
            data: normalizedDecisions,
            type: 'bar',
            yAxisID: 'y-decision',
            backgroundColor: normalizedDecisions.map(d => 
                d === 1 ? 'rgba(82, 196, 26, 0.8)' : d === -1 ? 'rgba(245, 34, 45, 0.8)' : 'rgba(217, 217, 217, 0.4)'
            ),
            borderColor: normalizedDecisions.map(d => 
                d === 1 ? CHART_COLORS.buySignal : d === -1 ? CHART_COLORS.sellSignal : CHART_COLORS.holdSignal
            ),
            borderWidth: 1,
            barThickness: 'flex',
            maxBarThickness: 15,
            categoryPercentage: 0.8,
            barPercentage: 0.9
        });
    }
    
    // 配置Y轴 - 使用配置映射
    const scales = { x: { grid: { color: '#f0f0f0' } } };
    
    // 根据选中的指标动态添加Y轴
    const axisMapping = {
        'y-price': ['price', 'sma5', 'sma20', 'sma50', 'bollinger'],
        'y-macd': ['macd', 'macd_signal'],
        'y-macd-histogram': ['macd_histogram'],
        'y-rsi': ['rsi'],
        'y-score': ['scores'],
        'y-decision': ['decisions']
    };
    
    Object.entries(axisMapping).forEach(([axisId, indicators]) => {
        if (selectedIndicators.some(i => indicators.includes(i))) {
            scales[axisId] = Y_AXIS_CONFIGS[axisId];
        }
    });
    
    window[chartId] = new Chart(ctx, {
        type: 'line',  // 主要类型保持为线图
        data: { labels: data.labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales,
            plugins: {
                legend: { 
                    display: true,
                    position: 'top',
                    labels: { boxWidth: 12, font: { size: 11 } }
                },
                tooltip: {
                    mode: 'index',
                    intersect: false
                }
            },
            interaction: {
                mode: 'nearest',
                axis: 'x',
                intersect: false
            }
        }
    });
};

// 回测图表渲染：价格+决策柱状 / 权益曲线
window.initBacktestCharts = (bt) => {
    if (!bt) return;
    // 兼容旧调用：现在统一使用技术图渲染器
    const checkboxes = document.querySelectorAll('input[data-indicator-bt]');
    const selected = Array.from(checkboxes).filter(cb => cb.checked).map(cb => cb.dataset.indicatorBt);
    if (bt.chart) {
        window.initTechnicalChart(bt.chart, selected, 'backtestTechnicalChart');
    }
};