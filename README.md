# Discord Self-Bot

Auto Queue Joiner with Multi-Queue Support, Monitoring & Webhook Alerts

> ⚠️ **Disclaimer:** Self-bots violate Discord's Terms of Service. This guide is purely educational.
> Use responsibly and at your own risk. Automating user accounts can result in permanent bans.

Refer to the full development guide in the documentation files. The project is structured for low-end VPS usage.

---

## Running & Testing Offline

You don't need to connect to a real Discord account while developing or testing logic. The repository
includes several small scripts and commands that exercise the configuration, keyword matching, and
webhook logic without logging in.

### 1. Prepare your environment

```powershell
cd "c:\Users\user\Downloads\New folder\discord-selfbot"
python -m venv venv            # create a virtualenv
.\venv\Scripts\activate      # activate on Windows
pip install -r requirements.txt
```

> You can skip setting a real token in `config.json` when running the dry‑run scripts below.

### 2. Dry‑run configuration

```powershell
python -c "
from bot.config_manager import config
config.load()
print('Queues:', list(config.queues.keys()))
print('Config OK')
"
```

This ensures the JSON parser and default merge logic work.

### 3. Test webhook sending

Fill `global_webhook_url` in `config.json` with a **dummy** Discord webhook URL
(or leave blank to skip actual HTTP traffic). Then run:

```powershell
python test_webhook.py
```

`test_webhook.py` is already included in the guide; it creates a `WebhookNotifier` and posts a test
embed.

### 4. Exercising keyword logic

The `test_keywords.py` script (see guide) simulates incoming messages and prints which queues
would match open/close/join keywords. Run it with:

```powershell
python test_keywords.py
```

No network connection is required; the script just loads `config.json` and inspects strings.

### 5. Running the full bot (offline)

You may also start `main.py` with a **blank token**; the startup will fail early but you can
observe config loading and logging behavior. For a more complete offline run, temporarily
patch `main.py` to skip `bot.start()` and instead create a `SelfBot` instance and manually call
its `on_message` handler with fake message objects.

> This is useful when writing unit tests; the real Discord gateway is never contacted.

### 6. Creating additional tests

- Write simple Python files importing modules from `bot/`.
- Use `asyncio.run()` to exercise async methods such as `queue_mgr.join_queue()` with mocked
  channel objects.
- Use `mypy` or `pytest` if you want formal test suites.

---

## Downloading & Running the Bot

Follow these steps to obtain the code, prepare the environment, and start the self-bot.

1. **Get the source code**
   * If you have this folder locally already, simply move it to your working directory.  
   * Otherwise, download the zip archive or clone the repository from wherever it is hosted. For
     example:
     ```powershell
     # clone from GitHub (replace URL with the actual repo)
     git clone https://github.com/yourname/discord-selfbot.git
     cd discord-selfbot
     ```

2. **Create a Python virtual environment**
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate            # on Windows
   # OR on Unix/macOS: source venv/bin/activate
   ```

3. **Install dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Configure the bot**
   * Open `config.json` in a text editor.
   * Fill in the following fields:
     - `token`: your Discord **user** token (not a bot token).
     - `owner_id`: your Discord user ID as a string.
     - `command_channels`: list of channel IDs where you will issue commands.
     - `global_webhook_url`: optional webhook for alerts.
     - `queues`: define one or more queue entries as shown in the example.
   * If you just want to test offline, you can leave `token` empty and skip webhook values.

5. **Start the bot**
   ```powershell
   python main.py
   ```
   The first run will log in to Discord using your token and print status to `bot.log`.

6. **Using the bot**
   * Send prefix commands (`!join`, `!addqueue`, etc.) via DM to your user account or in
     one of the configured `command_channels`.
   * Monitor queue states by adding channels to watch with `!monitor <channel_id> <queue>`.
   * To auto-join, either mention your account and include a keyword, or use `!join` manually.
   * Check `bot.log` for debugging information and webhook send status.

7. **Stopping & restarting**
   * Press `Ctrl+C` in the terminal to gracefully shut the bot (it closes webhooks, logs, etc.).
   * Restart with the same `python main.py` command; config changes persist in `config.json`.

8. **Deploying to a VPS (optional)**
   Refer to the original development guide in the repository for a sample systemd unit file
   and resource‑limiting tips if you wish to run the bot on a remote Linux server.

---

Detailed usage, deployment options, and VPN instructions are contained in the development guide
that lives alongside the source files.
