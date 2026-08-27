"""
ДАШБОРД ЛИДОВ И КЛИЕНТОВ
Отдельное Flask приложение для просмотра базы клиентов.
Запускается отдельно: python dashboard_app.py
Слушает на http://localhost:8080
"""

from flask import Flask, render_template_string, jsonify
import sqlite3
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Подключение к БД
DB_PATH = "leads.db"

def get_db_connection():
    """Открывает соединение с БД"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def format_date(date_str):
    """Форматирует дату красиво"""
    if not date_str:
        return "—"
    try:
        dt = datetime.fromisoformat(date_str)
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return date_str


# HTML ШАБЛОН ДАШБОРДА (синий + золото)
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Дашборд Лидов</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #0a1428 0%, #1a2a4a 100%);
            color: #e0e0e0;
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .header {
            background: linear-gradient(135deg, #1a3a52 0%, #0f2a3a 100%);
            border: 2px solid #d4af37;
            border-radius: 10px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(212, 175, 55, 0.2);
        }
        
        .header h1 {
            color: #d4af37;
            font-size: 2.5em;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.5);
        }
        
        .header p {
            color: #b0b0b0;
            font-size: 1em;
        }
        
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: linear-gradient(135deg, #1a3a52 0%, #162f42 100%);
            border: 1px solid #d4af37;
            border-radius: 8px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(212, 175, 55, 0.1);
        }
        
        .stat-number {
            font-size: 2.5em;
            color: #d4af37;
            font-weight: bold;
            margin: 10px 0;
        }
        
        .stat-label {
            color: #b0b0b0;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .filters {
            background: linear-gradient(135deg, #1a3a52 0%, #162f42 100%);
            border: 1px solid #d4af37;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 30px;
            display: flex;
            gap: 15px;
            flex-wrap: wrap;
            align-items: center;
        }
        
        .filter-btn {
            background: transparent;
            border: 2px solid #d4af37;
            color: #d4af37;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
            transition: all 0.3s;
        }
        
        .filter-btn:hover,
        .filter-btn.active {
            background: #d4af37;
            color: #0a1428;
        }
        
        .table-container {
            background: linear-gradient(135deg, #1a3a52 0%, #162f42 100%);
            border: 1px solid #d4af37;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(212, 175, 55, 0.15);
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        thead {
            background: linear-gradient(135deg, #0f2a3a 0%, #081820 100%);
            border-bottom: 2px solid #d4af37;
        }
        
        th {
            padding: 15px;
            text-align: left;
            color: #d4af37;
            font-weight: bold;
            text-transform: uppercase;
            font-size: 0.9em;
            letter-spacing: 1px;
        }
        
        td {
            padding: 15px;
            border-bottom: 1px solid #3a5a7a;
        }
        
        tr:hover {
            background: rgba(212, 175, 55, 0.05);
        }
        
        .badge {
            display: inline-block;
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: bold;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .badge-целевой {
            background: #2d5a3d;
            color: #5eff6d;
            border: 1px solid #5eff6d;
        }
        
        .badge-теплый {
            background: #5a4a2d;
            color: #ffd966;
            border: 1px solid #ffd966;
        }
        
        .badge-левый {
            background: #5a2d2d;
            color: #ff6b6b;
            border: 1px solid #ff6b6b;
        }
        
        .badge-неизвестный {
            background: #3a4a5a;
            color: #90c0e8;
            border: 1px solid #90c0e8;
        }
        
        .summary-popup {
            max-height: 200px;
            overflow-y: auto;
            background: #081820;
            padding: 10px;
            border-radius: 5px;
            font-size: 0.9em;
            color: #c0c0c0;
            border-left: 3px solid #d4af37;
        }
        
        .no-data {
            text-align: center;
            padding: 40px;
            color: #808080;
            font-size: 1.1em;
        }
        
        .footer {
            text-align: center;
            padding: 20px;
            color: #606060;
            font-size: 0.9em;
            margin-top: 30px;
        }
        
        @media (max-width: 768px) {
            .header h1 {
                font-size: 1.8em;
            }
            
            .stats {
                grid-template-columns: 1fr 1fr;
            }
            
            table {
                font-size: 0.9em;
            }
            
            th, td {
                padding: 10px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Дашборд Лидов AI-Консультанта</h1>
            <p>Все клиенты и их взаимодействие с ботом в реальном времени</p>
        </div>
        
        <div class="stats">
            <div class="stat-card">
                <div class="stat-label">Всего лидов</div>
                <div class="stat-number" id="total-leads">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Целевые клиенты</div>
                <div class="stat-number" id="целевые" style="color: #5eff6d;">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Теплые контакты</div>
                <div class="stat-number" id="теплые" style="color: #ffd966;">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Левые</div>
                <div class="stat-number" id="левые" style="color: #ff6b6b;">0</div>
            </div>
        </div>
        
        <div class="filters">
            <span style="color: #d4af37; font-weight: bold;">Фильтр:</span>
            <button class="filter-btn active" onclick="filterTable('all')">Все</button>
            <button class="filter-btn" onclick="filterTable('целевой')">Целевые</button>
            <button class="filter-btn" onclick="filterTable('теплый')">Теплые</button>
            <button class="filter-btn" onclick="filterTable('левый')">Левые</button>
            <button class="filter-btn" onclick="location.reload()" style="margin-left: auto;">🔄 Обновить</button>
        </div>
        
        <div class="table-container">
            <table id="leads-table">
                <thead>
                    <tr>
                        <th>👤 Имя</th>
                        <th>📱 Юзернейм</th>
                        <th>💬 Первый запрос</th>
                        <th>📌 Резюме</th>
                        <th>🏷️ Тип</th>
                        <th>📅 Дата</th>
                    </tr>
                </thead>
                <tbody id="leads-body">
                    <tr><td colspan="6" class="no-data">Загружаю данные...</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="footer">
            <p>🔄 Дашборд обновляется автоматически каждые 30 секунд</p>
        </div>
    </div>
    
    <script>
        const REFRESH_INTERVAL = 30000; // 30 сек
        
        async function loadData() {
            try {
                const response = await fetch('/api/leads');
                const data = await response.json();
                renderTable(data);
                updateStats(data);
            } catch (error) {
                console.error('Ошибка загрузки:', error);
            }
        }
        
        function renderTable(leads) {
            const tbody = document.getElementById('leads-body');
            
            if (!leads || leads.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" class="no-data">Пока нет лидов</td></tr>';
                return;
            }
            
            tbody.innerHTML = leads.map(lead => `
                <tr data-type="${lead.type}">
                    <td><strong>${lead.full_name}</strong></td>
                    <td>@${lead.username}</td>
                    <td>${lead.first_message.substring(0, 50)}...</td>
                    <td>
                        ${lead.summary ? `<div class="summary-popup">${lead.summary}</div>` : '<em style="color: #606060;">нет резюме</em>'}
                    </td>
                    <td>
                        <span class="badge badge-${lead.type}">
                            ${lead.type}
                        </span>
                    </td>
                    <td>${lead.created_at}</td>
                </tr>
            `).join('');
        }
        
        function updateStats(leads) {
            const types = {целевой: 0, теплый: 0, левый: 0};
            
            leads.forEach(lead => {
                if (types.hasOwnProperty(lead.type)) {
                    types[lead.type]++;
                }
            });
            
            document.getElementById('total-leads').textContent = leads.length;
            document.getElementById('целевые').textContent = types['целевой'];
            document.getElementById('теплые').textContent = types['теплый'];
            document.getElementById('левые').textContent = types['левый'];
        }
        
        function filterTable(type) {
            const rows = document.querySelectorAll('#leads-body tr');
            const buttons = document.querySelectorAll('.filter-btn');
            
            buttons.forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            rows.forEach(row => {
                if (type === 'all' || row.dataset.type === type) {
                    row.style.display = '';
                } else {
                    row.style.display = 'none';
                }
            });
        }
        
        // Загрузить данные при загрузке страницы
        loadData();
        
        // Автообновление
        setInterval(loadData, REFRESH_INTERVAL);
    </script>
</body>
</html>
"""


@app.route('/')
def index():
    """Главная страница дашборда"""
    return render_template_string(DASHBOARD_HTML)


@app.route('/api/leads')
def api_leads():
    """API для получения всех лидов с резюме и классификацией"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Получаем лиды с классификацией и резюме
        cursor.execute("""
            SELECT 
                l.id,
                l.user_id,
                l.username,
                l.full_name,
                l.first_message,
                l.created_at,
                COALESCE(uc.classification, 'неизвестный') as classification,
                us.summary
            FROM leads l
            LEFT JOIN user_classification uc ON l.user_id = uc.user_id AND uc.platform = 'telegram'
            LEFT JOIN user_summary us ON l.user_id = us.user_id AND us.platform = 'telegram'
            ORDER BY l.created_at DESC
            LIMIT 1000
        """)
        
        leads = []
        for row in cursor.fetchall():
            leads.append({
                'id': row[0],
                'user_id': row[1],
                'username': row[2],
                'full_name': row[3],
                'first_message': row[4],
                'created_at': format_date(row[5]),
                'type': row[6],
                'summary': row[7]
            })
        
        conn.close()
        return jsonify(leads)
    
    except Exception as e:
        logger.error(f"❌ Ошибка при получении лидов: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/stats')
def api_stats():
    """API для получения статистики"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Общее кол-во лидов
        cursor.execute("SELECT COUNT(*) FROM leads")
        total = cursor.fetchone()[0]
        
        # По типам
        cursor.execute("""
            SELECT classification, COUNT(*) 
            FROM user_classification 
            WHERE platform = 'telegram'
            GROUP BY classification
        """)
        
        types = {}
        for row in cursor.fetchall():
            types[row[0]] = row[1]
        
        conn.close()
        
        return jsonify({
            'total': total,
            'целевой': types.get('целевой', 0),
            'теплый': types.get('теплый', 0),
            'левый': types.get('левый', 0),
            'неизвестный': types.get('неизвестный', 0)
        })
    
    except Exception as e:
        logger.error(f"❌ Ошибка при получении статистики: {e}")
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    logger.info("🎨 Дашборд запущен на http://localhost:8080")
    app.run(host='0.0.0.0', port=8080, debug=False)
