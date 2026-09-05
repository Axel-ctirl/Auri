# Minecraft Paper Plugin (Java)

Server-side plugins for Paper and Spigot: commands, listeners, persistent data and plugin.yml wiring.

Triggers: paper, spigot, bukkit, plugin.yml, minecraft plugin, papermc

You are helping with a **Paper** plugin. Paper is a fork of Spigot, which is a
fork of Bukkit, so most Bukkit APIs still apply and Paper adds its own.

State the target version before writing code. The API changed meaningfully
across 1.13 (flattening), 1.17 (Java 16, no more NMS remapping shortcuts),
1.19.3 and 1.20.5 (item components). If the user has not said, ask once or state
the version you are assuming.

Conventions to follow:

- Main class extends `JavaPlugin`, registered in `plugin.yml` as `main:`.
  Commands and permissions are declared in `plugin.yml` too, not invented at
  runtime.
- Use the Adventure API for text: `Component.text(...)`, `player.sendMessage(Component)`.
  Legacy `ChatColor` and `§` codes are deprecated on modern Paper.
- Register listeners with `getServer().getPluginManager().registerEvents(listener, this)`
  in `onEnable`. Cancel events with `event.setCancelled(true)`, and check
  `event.isCancelled()` before acting on a lower-priority handler.
- Never block the main thread. File and network work goes on
  `Bukkit.getScheduler().runTaskAsynchronously`, and anything touching the world
  or entities must come back to the main thread with `runTask`.
- Persist per-entity and per-item state with `PersistentDataContainer` and a
  `NamespacedKey` owned by the plugin. Do not parse display names to store data.
- Guard every command with a permission node and a `sender instanceof Player`
  check when the command needs a player.

Include the `plugin.yml` whenever you add a command, a permission or a listener
that needs registering. A plugin that compiles but is not registered is the most
common failure here.

Prefer Gradle with the `paper-api` dependency at `provided`/`compileOnly` scope,
and note the Java toolchain version the target server needs.
