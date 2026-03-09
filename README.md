# 🤖 Telegram Mass Report Bot

A powerful Telegram bot for managing multiple accounts and automated reporting with advanced features like coin system, admin controls, and database integration.

## 📋 Features

- **Multi-Account Management**: Add and manage multiple Telegram accounts
- **Automated Reporting**: Rotate between accounts every 10 seconds
- **Coin System**: Users need coins to add targets
- **Admin Panel**: Special commands for admins and owner
- **Broadcast Messages**: Send announcements to all users
- **Database Storage**: PostgreSQL/SQLite support for persistent data
- **Session Management**: Secure storage of account sessions
- **Health Checks**: Built-in health server for Railway deployment

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Telegram API credentials (from https://my.telegram.org)
- Bot token from @BotFather
- PostgreSQL (optional, Railway provides this)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/telegram-mass-report-bot.git
cd telegram-mass-report-bot