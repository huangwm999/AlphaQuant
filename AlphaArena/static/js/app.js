// OKX BTC交易机器人 - 工具函数库

// 简化元素创建
window.h = React.createElement;





// 格式化函数
const getSignalTag = signal => h(antd.Tag, { color: { BUY: 'success', SELL: 'error', HOLD: 'warning' }[signal] || 'default', size: 'small' }, signal || 'HOLD');
const formatTime = timestamp => timestamp ? timestamp.split(' ')[1] : '--';
const formatPrice = price => price ? `$${price.toLocaleString()}` : '--';
const formatPnl = pnl => !pnl ? '--' : h(antd.Tag, { color: pnl >= 0 ? 'red' : 'green' }, `${pnl.toFixed(2)} USDT`);

// 表格列配置
const tradeColumns = [
    { title: '时间', dataIndex: 'timestamp', width: 120, render: formatTime },
    { title: '信号', dataIndex: 'signal', width: 80, render: getSignalTag },
    { title: '价格', dataIndex: 'price', width: 120, render: formatPrice },
    { title: '手续费', dataIndex: 'fee', width: 100, render: (fee, record) => {
        // 如果记录中有fee字段，直接使用
        if (fee !== undefined && fee !== null) {
            return `${fee.toFixed(6)} USDT`;
        }
        // 否则根据价格和数量计算手续费 (0.05%费率)
        if (record.price && record.amount) {
            const contractSize = 0.01; // BTC合约大小
            const tradeValue = record.price * record.amount * contractSize;
            const calculatedFee = tradeValue * 0.0005; // 0.05%
            return `${calculatedFee.toFixed(6)} USDT`;
        }
        return '--';
    }},
    { title: '盈亏', dataIndex: 'pnl', width: 100, render: formatPnl }
];

const analysisColumns = [
    { title: '时间', dataIndex: 'timestamp', width: 70, render: text => text ? moment(text).format('HH:mm') : '--' },
    { title: '信号', dataIndex: 'signal', width: 50, render: getSignalTag },
    { title: '信心', dataIndex: 'confidence', width: 50, render: conf => h(antd.Tag, { color: { HIGH: 'success', MEDIUM: 'warning', LOW: 'error' }[conf] || 'default', size: 'small' }, conf || '--') },
    { title: '价格', dataIndex: 'btc_price', width: 70, render: price => price ? `$${Math.round(price).toLocaleString()}` : '--' }
];

// 通用图表初始化函数
function initChart(chartId, data, type = 'line') {
    const ctx = document.getElementById(chartId);
    if (!ctx) return;
    
    if (window[chartId]?.destroy) try { window[chartId].destroy(); } catch (e) {}
    
    const configs = {
        price: { type: 'line', data: { labels: data.labels, datasets: [{ data: data.prices, borderColor: '#1890ff', backgroundColor: 'rgba(24, 144, 255, 0.1)', tension: 0.1, fill: true }] }, options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: false, ticks: { callback: v => `$${v.toLocaleString()}` } } }, plugins: { legend: { display: false } } } },
        dailyPnl: { type: 'bar', data: { labels: Object.keys(data).map(d => d), datasets: [{ data: Object.values(data), backgroundColor: Object.values(data).map(v => v >= 0 ? '#f5222d' : '#52c41a'), borderWidth: 0 }] }, options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { font: { size: 9 }, maxTicksLimit: 4 } } } } }
    };
    
    window[chartId] = new Chart(ctx, configs[type] || configs.price);
}

// 价格图表初始化函数
window.initPriceChart = (trades) => trades?.length && initChart('priceChart', { labels: trades.map(t => moment(t.timestamp).format('HH:mm')), prices: trades.map(t => t.price) }, 'price');

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
    if (scrollEl && innerEl) {
        const pxPerBar = 10; // 每个数据点的最小像素宽度
        const labelsCount = Array.isArray(data.labels) ? data.labels.length : (data.klines ? data.klines.length : 0);
        const minWidth = scrollEl.clientWidth || 600;
        const targetWidth = Math.max(minWidth, labelsCount * pxPerBar);
        innerEl.style.width = `${targetWidth}px`;
    }

    if (window[chartId]?.destroy) try { window[chartId].destroy(); } catch (e) {}
    
    const datasets = [];
    
    // K线数据转换为折线图（收盘价）
    if (selectedIndicators.includes('price')) {
        datasets.push({
            label: 'BTC价格',
            data: data.klines.map(k => k.close),
            borderColor: '#1890ff',
            backgroundColor: 'rgba(24, 144, 255, 0.1)',
            yAxisID: 'y-price',
            tension: 0.1
        });
    }
    
    // 移动平均线
    if (selectedIndicators.includes('sma5')) {
        datasets.push({
            label: 'SMA5',
            data: data.indicators.sma5,
            borderColor: '#52c41a',
            backgroundColor: 'transparent',
            yAxisID: 'y-price',
            borderWidth: 1
        });
    }
    
    if (selectedIndicators.includes('sma20')) {
        datasets.push({
            label: 'SMA20',
            data: data.indicators.sma20,
            borderColor: '#faad14',
            backgroundColor: 'transparent',
            yAxisID: 'y-price',
            borderWidth: 1
        });
    }
    
    if (selectedIndicators.includes('sma50')) {
        datasets.push({
            label: 'SMA50',
            data: data.indicators.sma50,
            borderColor: '#f5222d',
            backgroundColor: 'transparent',
            yAxisID: 'y-price',
            borderWidth: 1
        });
    }
    
    // 布林带 - 带填充模式
    if (selectedIndicators.includes('bollinger')) {
        const currentDatasetLength = datasets.length;
        
        // 下轨（作为填充的起点）
        datasets.push({
            label: 'BB下轨',
            data: data.indicators.bb_lower,
            borderColor: '#722ed1',
            backgroundColor: 'transparent',
            yAxisID: 'y-price',
            borderWidth: 1,
            pointRadius: 0,
            fill: false
        });
        
        // 上轨（填充到下轨）
        datasets.push({
            label: 'BB上轨',
            data: data.indicators.bb_upper,
            borderColor: '#722ed1',
            backgroundColor: 'rgba(114, 46, 209, 0.1)', // 淡紫色填充
            yAxisID: 'y-price',
            borderWidth: 1,
            pointRadius: 0,
            fill: currentDatasetLength, // 填充到下轨的索引位置
            tension: 0.1
        });
        
        // 中轨（独立显示，不参与填充）
        datasets.push({
            label: 'BB中轨',
            data: data.indicators.bb_middle,
            borderColor: '#13c2c2',
            backgroundColor: 'transparent',
            yAxisID: 'y-price',
            borderWidth: 1.5,
            borderDash: [5, 5], // 虚线样式
            pointRadius: 0,
            fill: false
        });
    }
    
    // MACD线
    if (selectedIndicators.includes('macd')) {
        datasets.push({
            label: 'MACD',
            data: data.indicators.macd,
            borderColor: '#52c41a',
            backgroundColor: 'transparent',
            yAxisID: 'y-macd',
            borderWidth: 2
        });
    }
    
    // MACD信号线
    if (selectedIndicators.includes('macd_signal')) {
        datasets.push({
            label: 'MACD信号',
            data: data.indicators.macd_signal,
            borderColor: '#f5222d',
            backgroundColor: 'transparent',
            yAxisID: 'y-macd',
            borderWidth: 1
        });
    }
    
    // RSI
    if (selectedIndicators.includes('rsi')) {
        datasets.push({
            label: 'RSI',
            data: data.indicators.rsi,
            borderColor: '#eb2f96',
            backgroundColor: 'rgba(235, 47, 150, 0.2)',
            yAxisID: 'y-rsi',
            borderWidth: 2,
            fill: true
        });
    }
    
    // Score评分 - 使用独立Y轴
    if (selectedIndicators.includes('scores')) {
        datasets.push({
            label: 'Score评分',
            data: data.indicators.scores,
            borderColor: '#a0d911',
            backgroundColor: 'rgba(160, 217, 17, 0.2)',
            yAxisID: 'y-score',
            borderWidth: 2,
            fill: true
        });
    }
    
    // 交易决策曲线 - 新增（增强初始化）
    if (selectedIndicators.includes('decisions')) {
        // 确保决策数据存在且长度正确
        const decisions = data.indicators.decisions || [];
        const labelCount = data.labels ? data.labels.length : 0;
        
        // 如果决策数据长度与标签不匹配，用0填充
        const normalizedDecisions = [];
        for (let i = 0; i < labelCount; i++) {
            normalizedDecisions.push(decisions[i] !== undefined ? decisions[i] : 0);
        }
        
        console.log(`决策数据初始化: 标签数量=${labelCount}, 决策数据数量=${decisions.length}, 标准化后=${normalizedDecisions.length}`);
        
        datasets.push({
            label: '交易决策',
            data: normalizedDecisions,
            type: 'bar',  // 改为柱状图
            yAxisID: 'y-decision',
            backgroundColor: normalizedDecisions.map(d => 
                d === 1 ? 'rgba(82, 196, 26, 0.8)' :   // 买入 - 绿色
                d === -1 ? 'rgba(245, 34, 45, 0.8)' :  // 卖出 - 红色  
                'rgba(217, 217, 217, 0.4)'             // 持有 - 浅灰色
            ),
            borderColor: normalizedDecisions.map(d => 
                d === 1 ? '#52c41a' :   // 买入 - 绿色边框
                d === -1 ? '#f5222d' :  // 卖出 - 红色边框
                '#d9d9d9'               // 持有 - 灰色边框
            ),
            borderWidth: 1,
            barThickness: 'flex',  // 自动调整柱子宽度
            maxBarThickness: 15,   // 最大柱子宽度
            categoryPercentage: 0.8,  // 柱子组宽度占类别宽度的比例
            barPercentage: 0.9        // 单个柱子宽度占柱子组宽度的比例
        });
    }
    
    // 配置Y轴
    const scales = {
        x: { grid: { color: '#f0f0f0' } }
    };
    
    // 价格轴（主轴）
    if (selectedIndicators.some(i => ['price', 'sma5', 'sma20', 'sma50', 'bollinger'].includes(i))) {
        scales['y-price'] = {
            type: 'linear',
            position: 'left',
            grid: { color: '#f0f0f0' },
            ticks: { callback: v => `$${v.toLocaleString()}` }
        };
    }
    
    // MACD轴
    if (selectedIndicators.includes('macd') || selectedIndicators.includes('macd_signal')) {
        scales['y-macd'] = {
            type: 'linear',
            position: 'right',
            grid: { display: false },
            ticks: { font: { size: 10 } }
        };
    }
    
    // RSI轴
    if (selectedIndicators.includes('rsi')) {
        scales['y-rsi'] = {
            type: 'linear',
            position: 'right',
            min: 0,
            max: 100,
            grid: { display: false },
            ticks: { font: { size: 10 } }
        };
    }
    
    // Score轴
    if (selectedIndicators.includes('scores')) {
        scales['y-score'] = {
            type: 'linear',
            position: 'right',
            min: -100,
            max: 100,
            grid: { display: false },
            ticks: { 
                font: { size: 10 },
                callback: v => `S${v}`  // 前缀S表示Score
            }
        };
    }
    
    // 决策轴 - 柱状图优化
    if (selectedIndicators.includes('decisions')) {
        scales['y-decision'] = {
            type: 'linear',
            position: 'right',
            min: -1.5,
            max: 1.5,
            grid: { 
                display: true,
                color: 'rgba(0,0,0,0.1)',
                drawOnChartArea: false  // 只在决策轴区域显示网格
            },
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
        };
    }
    
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