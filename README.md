# VcObserver

Small plug in code to monitor how much time members pass in VCs.


> [!IMPORTANT]  
> Command names and strings are in **French**.

<img width="423" alt="image" src="https://github.com/user-attachments/assets/9255d7ef-b0c4-47da-afe8-2ffdf4f02e7d" />

## How to add

1. Copy `src/vc_observer.py` into your project.
2. Import the `VcObserver` class from the file.
3. Make sure you have logging initialised.
4. Call the class and pass `bot`, `tree`, `filepath` and optionally `guild_ids`.
5. **Call `tree.sync()` after having called `VcOberver()`, else commands won't sync.**

## Behaviour

When a user `Connects`, `Disconnects`, `Switches (from VC A to VC B)` the bot adds his elapsed time in the VC into the JSON file.
This means if the bot gets killed while members are inside VCs, their elapsed time in VC will not be counted.
