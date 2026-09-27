# Server Performance Monitor 

[Читать на русском](README_RU.md)

A Python script designed to analyze and report performance statistics across multiple Linux hosts.

The script connects via SSH, gathers key system metrics, and delivers a formatted report directly to a Telegram bot.

This project was built as an expanded solution for the [Server Performance Stats](https://roadmap.sh/projects/server-stats) project on roadmap.sh. While the original requirement specified a local bash script, this project implements a scalable Python wrapper with real-time alerting and multi-host support.

### Collected Metrics
* OS Version
* Server System Time
* CPU Usage & Load Average
* Memory Usage (RAM: Used / Free / %)
* Disk Storage (Used / Free / %)
* System Uptime
* Logged-in Users Count
* Failed SSH Login Attempts (last 24 hours)
* Status of running Docker containers
* Top 5 Processes by CPU Usage
* Top 5 Processes by Memory Usage

### Prerequisites
* Target servers running Linux
* Python 3.7+ (**Zero external dependencies**)
* Configured SSH key-based authentication (`~/.ssh/config`)
* Telegram Bot Token & Chat ID

### Usage Guide

#### 1. Clone the Repository
```
git clone https://github.com/Whoami-775/Server-Performance-Stats.git
cd Server-Performance-Stats
```

#### 2. SSH Setup for Passwordless Access

Ensure your public key is added to the target servers (`~/.ssh/authorized_keys`) and host aliases are defined in your local `~/.ssh/config`:

```
Host au-main
    HostName 192.168.122.41
    User root

```

#### 3. Telegram Bot Preparation

1. Create a bot via [@BotFather](https://t.me/BotFather?utm_source=gemini) and save the provided **Token**.
2. Find your profile **Chat ID** using [@Getmyid_bot](https://t.me/Getmyid_bot?utm_source=gemini).

#### 4. Running the Script

No external `pip` dependencies are required (built using standard Python modules: `urllib`, `json`, `subprocess`).

Pass your credentials via environment variables and run the script:

```
export TELEGRAM_BOT_TOKEN="your_bot_token"
export TELEGRAM_CHAT_ID="your_chat_id"
python3 monitor_servers.py

```

#### 5. Automated Execution via Cron

To receive hourly performance reports, add a scheduled task to `cron`:

```
crontab -e

```

Add the following cron task line:

```
0 * * * * export TELEGRAM_BOT_TOKEN="your_token" TELEGRAM_CHAT_ID="your_id"; /usr/bin/python3 /path/to/Server-Performance-Stats/monitor_servers.py > /dev/null 2>&1

```




Based on the Server Performance Stats project from [roadmap.sh](https://roadmap.sh/projects/server-stats?utm_source=gemini).

