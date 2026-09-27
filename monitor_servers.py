from __future__ import annotations
import concurrent.futures
import datetime
import html
import json
import os
import subprocess
import urllib.request

# Переменные окружения без хардкода секретов
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Список серверов из ~/.ssh/config
# При кол-ве серверов учитывайте, что Telegram API имеет жесткое ограничение: не более 4096 символов в одном сообщении.
HOSTS = [
    "i-main",
    "i-app2",
    "i-app3",
    "i-sand",
    "i-app4",

]

# Bash-скрипт сбора телеметрии для Linux-серверов
REMOTE_SCRIPT = r"""
# 1. ОС и системное время
SERVER_TIME=$(date "+%d.%m.%Y %H:%M:%S")
OS=$(lsb_release -ds 2>/dev/null || cat /etc/*release 2>/dev/null | head -n1 || uname -om)

# 2. CPU и Load Average
CPU=$(top -bn1 | grep 'Cpu(s)' | awk '{print 100 - $8}' || echo "0")
LOAD=$(uptime | awk -F'load average:' '{ print $2 }' | xargs)

# 3. Оперативная память (RAM)
MEM_TOTAL=$(free -m | awk 'NR==2{print $2}')
MEM_USED=$(free -m | awk 'NR==2{print $3}')
MEM_FREE=$(free -m | awk 'NR==2{print $4}')
MEM_PCT=$(awk -v u="$MEM_USED" -v t="$MEM_TOTAL" 'BEGIN { if(t>0) printf "%.1f", (u/t)*100; else print 0 }')

# 4. Диск (корень /)
DISK_TOTAL=$(df -h / | awk 'NR==2{print $2}')
DISK_USED=$(df -h / | awk 'NR==2{print $3}')
DISK_FREE=$(df -h / | awk 'NR==2{print $4}')
DISK_PCT=$(df -h / | awk 'NR==2{print $5}')

# 5. Аптайм
UPTIME=$(uptime -p | sed 's/up //' 2>/dev/null || uptime)

# 6. Сессии и неуспешные попытки входа SSH за 24 часа
USERS=$(who | wc -l | xargs)
FAILED_SSH=$(journalctl _SYSTEMD_UNIT=ssh.service --since "24 hours ago" 2>/dev/null | grep -i "failed" | wc -l || grep -i "failed" /var/log/auth.log 2>/dev/null | wc -l || echo "0")

# 7. Docker
if command -v docker >/dev/null 2>&1; then
    DOCKER_RUNNING=$(docker ps -q 2>/dev/null | wc -l)
    DOCKER_TOTAL=$(docker ps -a -q 2>/dev/null | wc -l)
    DOCKER_STATUS="${DOCKER_RUNNING}/${DOCKER_TOTAL} запущены"
else
    DOCKER_STATUS="Не установлен"
fi

# 8. Топ-5 процессов по CPU
TOP_CPU=$(ps -eo comm,%cpu --sort=-%cpu | head -n 6 | tail -n 5 | awk '{print $1" ("$2"%)"}' | paste -sd ";" -)

# 9. Топ-5 процессов по RAM
TOP_RAM=$(ps -eo comm,%mem --sort=-%mem | head -n 6 | tail -n 5 | awk '{print $1" ("$2"%)"}' | paste -sd ";" -)

# Генерация ответа в формате JSON
cat <<EOF
{
    "OS": "${OS}",
    "SERVER_TIME": "${SERVER_TIME}",
    "CPU": "${CPU}%",
    "LOAD": "${LOAD}",
    "RAM_TOTAL": "${MEM_TOTAL}",
    "RAM_USED": "${MEM_USED}",
    "RAM_FREE": "${MEM_FREE}",
    "RAM_PCT": "${MEM_PCT}",
    "DISK_TOTAL": "${DISK_TOTAL}",
    "DISK_USED": "${DISK_USED}",
    "DISK_FREE": "${DISK_FREE}",
    "DISK_PCT": "${DISK_PCT}",
    "UPTIME": "${UPTIME}",
    "USERS": "${USERS}",
    "FAILED_SSH": "${FAILED_SSH}",
    "DOCKER": "${DOCKER_STATUS}",
    "TOP_CPU": "${TOP_CPU}",
    "TOP_RAM": "${TOP_RAM}"
}
EOF
"""


def check_server(host: str) -> tuple[str, bool, dict | str]:
    """Подключается по SSH и забирает метрики из Linux-сервера."""
    try:
        result = subprocess.run(
            [
                "ssh",
                "-o",
                "ConnectTimeout=5",
                "-o",
                "BatchMode=yes",
                host,
                "bash",
                "-s",
            ],
            input=REMOTE_SCRIPT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout.strip())
                return host, True, data
            except json.JSONDecodeError:
                return (
                    host,
                    False,
                    "Ошибка парсинга JSON (проверьте SSH ответ)",
                )
        else:
            return host, False, result.stderr.strip() or "SSH Connection Error"
    except subprocess.TimeoutExpired:
        return host, False, "Таймаут подключения (5 сек)"
    except Exception as e:
        return host, False, str(e)


def format_report_html(results: list[tuple[str, bool, dict | str]]) -> str:
    """Формирует безопасный отформатированный HTML-отчет."""
    now_header = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    lines = [
        f"📊 <b>Сводка по тестовым стендам</b> (<code>{now_header}</code>)\n"
    ]

    for host, success, data in results:
        safe_host = html.escape(host)

        if success and isinstance(data, dict):
            try:
                disk_pct_num = float(
                    data.get("DISK_PCT", "0").replace("%", "")
                )
            except ValueError:
                disk_pct_num = 0.0

            try:
                ram_pct_num = float(data.get("RAM_PCT", "0"))
            except ValueError:
                ram_pct_num = 0.0

            status_icon = (
                "🔴"
                if disk_pct_num >= 90 or ram_pct_num >= 95
                else "⚠️"
                if disk_pct_num >= 80 or ram_pct_num >= 85
                else "🟢"
            )

            lines.append(f"{status_icon} <b>отчет о {safe_host}</b>:")
            lines.append(
                f"  • <b>ОС:</b> <code>{html.escape(data.get('OS', 'N/A'))}</code>"
            )
            lines.append(
                f"  • <b>Время на сервере:</b> <code>{html.escape(data.get('SERVER_TIME', 'N/A'))}</code>"
            )
            lines.append(
                f"  • <b>CPU:</b> <code>{html.escape(data.get('CPU', 'N/A'))}</code> | <b>LA:</b> <code>{html.escape(data.get('LOAD', 'N/A'))}</code>"
            )
            lines.append(
                f"  • <b>ОЗУ:</b> <code>{html.escape(data.get('RAM_USED', '0'))}MB занято, {html.escape(data.get('RAM_FREE', '0'))}MB свободно</code> (Всего: <code>{html.escape(data.get('RAM_TOTAL', '0'))}MB</code> — <code>{data.get('RAM_PCT', '0')}%</code>)"
            )
            lines.append(
                f"  • <b>Диск:</b> <code>{html.escape(data.get('DISK_FREE', 'N/A'))} свободно</code> (Всего: <code>{html.escape(data.get('DISK_TOTAL', 'N/A'))}</code>, Занято: <code>{html.escape(data.get('DISK_USED', 'N/A'))}</code> — <code>{html.escape(data.get('DISK_PCT', 'N/A'))}</code>)"
            )
            lines.append(
                f"  • <b>Аптайм:</b> <code>{html.escape(data.get('UPTIME', 'N/A'))}</code>"
            )
            lines.append(
                f"  • <b>Авторизованные пользователи:</b> <code>{html.escape(data.get('USERS', '0'))}</code>"
            )
            lines.append(
                f"  • <b>Неудачные попытки входа (24ч):</b> <code>{html.escape(data.get('FAILED_SSH', '0'))}</code>"
            )
            lines.append(
                f"  • <b>Docker:</b> <code>{html.escape(data.get('DOCKER', 'N/A'))}</code>"
            )

            lines.append("\n🔥 <b>5 процессов с наибольшей загрузкой ЦП:</b>")
            top_cpu_items = data.get("TOP_CPU", "").split(";")
            for item in top_cpu_items:
                if item:
                    lines.append(f"  └ <code>{html.escape(item)}</code>")

            lines.append(
                "\n💾 <b>5 процессов с самым высоким потреблением памяти:</b>"
            )
            top_ram_items = data.get("TOP_RAM", "").split(";")
            for item in top_ram_items:
                if item:
                    lines.append(f"  └ <code>{html.escape(item)}</code>")

            lines.append("")
        else:
            lines.append(f"🔴 <b>отчет о {safe_host}</b>:")
            lines.append(f"  • ⚠️ <code>{html.escape(str(data))}</code>\n")

    return "\n".join(lines)


def send_telegram_message(token: str, chat_id: str, text: str) -> bool:
    """Отправляет отформатированное сообщение в Telegram API."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            return response.status == 200
    except Exception as e:
        print(f"Ошибка при отправке в Telegram: {e}")
        return False


def main():
    if not BOT_TOKEN or not CHAT_ID:
        print(
            "ОШИБКА: Задайте переменные окружения TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID."
        )
        return

    print(f"Запуск параллельного сбора данных с {len(HOSTS)} серверов...")
    results = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(HOSTS)
    ) as executor:
        futures = {
            executor.submit(check_server, host): host for host in HOSTS
        }
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())

    results.sort(key=lambda x: HOSTS.index(x[0]))
    report = format_report_html(results)

    print("\nСформированный отчет:\n")
    print(report)

    if send_telegram_message(BOT_TOKEN, CHAT_ID, report):
        print("\n✅ Отчет успешно передан в Telegram!")
    else:
        print("\n❌ Ошибка отправки отчета.")


if __name__ == "__main__":
    main()