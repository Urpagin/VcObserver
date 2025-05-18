# VcObserver

A lightweight plugin to monitor how much time members spend in voice channels.

> \[!IMPORTANT]
> Command names and strings are in **French**.

<img width="423" alt="image" src="https://github.com/user-attachments/assets/9255d7ef-b0c4-47da-afe8-2ffdf4f02e7d" />

## Compatibility

Compatible with bots using `discord.py`.

Ensure the following intents are enabled:

* `voice_states`
* `members`


## Installation

1. Copy `src/vc_observer.py` into your project.
2. Import the `VcObserver` class.
3. Ensure logging is initialized in your bot.
4. Instantiate the class with the following parameters: `bot`, `tree`, `filepath`, and optionally `guild_ids`.
5. **Call `tree.sync()` *after* initializing `VcObserver()`; otherwise, commands will not sync.**

## Behavior

When a user connects, disconnects, or switches between voice channels, the bot logs their time spent in the previous channel to a JSON file.

> [!TIP]
> If the bot is stopped or crashes while users are in voice channels, their ongoing session time will **not** be recorded.
